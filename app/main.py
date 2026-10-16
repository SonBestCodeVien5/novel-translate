"""Local, explicitly operated fake translation review interface."""
import base64
import binascii
import os
import secrets
import shlex
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from app.core import DomainError, Store

MAX_FILE = 1024 * 1024
MAX_BODY = 5 * 1024 * 1024
MAX_BULK_BODY = 32 * 1024 * 1024
MAX_BACKUP_UPLOAD = 64 * 1024 * 1024
MAX_BACKUP_BODY = 65 * 1024 * 1024
MAX_EPUB_BODY = 65 * 1024 * 1024
HERE = Path(__file__).parent


class LocalBoundary:
    """Bound bytes before multipart parsing, including requests without length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('latin1')
        try:
            parsed_host = urlsplit('http://' + host)
            valid_host = parsed_host.hostname in {'localhost', '127.0.0.1', '::1'} and not parsed_host.username and not parsed_host.password
            valid_host = valid_host and parsed_host.path == '' and parsed_host.query == '' and parsed_host.fragment == ''
            parsed_host.port
        except ValueError:
            valid_host = False
        if not valid_host:
            return await PlainTextResponse('Host không được phép.', 403)(scope, receive, send)
        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = headers.get(b'origin')
            if (origin and origin.decode('latin1') != f"{scope['scheme']}://{host}") or headers.get(b'sec-fetch-site') == b'cross-site':
                return await PlainTextResponse('Yêu cầu khác nguồn bị chặn.', 403)(scope, receive, send)
        body_limit = MAX_BULK_BODY if scope['method'] == 'POST' and scope.get('path', '').endswith('/results/bulk') else (MAX_BACKUP_BODY if scope['method'] == 'POST' and scope.get('path') == '/backups/restore' else (MAX_EPUB_BODY if scope['method'] == 'POST' and scope.get('path') == '/books/epub' else MAX_BODY))
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > body_limit:
                return await PlainTextResponse('Tệp hoặc biểu mẫu vượt giới hạn cho phép.', 413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        replayed = False
        async def bounded_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)


def create_app(data_dir: Path | None = None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(data_dir or Path(os.environ.get('NOVEL_DATA_DIR', 'data')))
        app.state.csrf = secrets.token_urlsafe(32)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(LocalBoundary)
    app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')
    templates = Jinja2Templates(directory=HERE / 'templates')

    def page(request, name, **context):
        return templates.TemplateResponse(request=request, name=name, context={'csrf': app.state.csrf, **context}, headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; script-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'", 'X-Content-Type-Options': 'nosniff'})

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        response = page(request, 'error.html', message=str(exc))
        response.status_code = exc.status_code
        return response

    async def form(request, max_files=1, max_part_size=MAX_BODY):
        data = await request.form(max_files=max_files, max_fields=1000, max_part_size=max_part_size)
        token = data.get('csrf', '')
        if not isinstance(token, str) or not secrets.compare_digest(token, app.state.csrf):
            await data.close()
            raise DomainError('Biểu mẫu hết hạn hoặc thiếu mã CSRF. Tải lại trang.', 403)
        return data

    async def upload(data, limit=MAX_FILE):
        item = data.get('file')
        if not isinstance(item, UploadFile):
            raise DomainError('Hãy chọn một tệp.')
        try:
            raw = await item.read(limit + 1)
        finally:
            await item.close()
        if len(raw) > limit:
            raise DomainError('Tệp vượt giới hạn cho phép.', 413)
        return raw

    @app.get('/backups')
    async def backups_page(request: Request):
        return page(request, 'backups.html', restored_path=None, startup_command=None,
                    backup_limit_mb=MAX_BACKUP_UPLOAD // (1024 * 1024))

    @app.post('/backups/create')
    async def create_backup_route(request: Request):
        from app.backups import create_backup
        data = await form(request)
        temp_dir = tempfile.mkdtemp(prefix='novel-backup-download-')
        output = Path(temp_dir) / f'novel-translate-{uuid.uuid4().hex}.zip'
        try:
            await run_in_threadpool(create_backup, app.state.store.data_dir, output)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return FileResponse(output, media_type='application/zip', filename='novel-translate-backup.zip',
                            background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True))

    @app.post('/backups/restore')
    async def restore_backup_route(request: Request):
        from app.backups import restore_backup
        data = await form(request, max_part_size=MAX_BACKUP_UPLOAD)
        raw = await upload(data, MAX_BACKUP_UPLOAD)
        current = Path(app.state.store.data_dir).resolve()
        name = current.name or 'library'
        target = current.with_name(f'{name}-restored-{uuid.uuid4().hex[:12]}')
        descriptor, temporary = tempfile.mkstemp(prefix='novel-backup-upload-', suffix='.zip')
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            await run_in_threadpool(restore_backup, Path(temporary), target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        command = 'NOVEL_DATA_DIR=' + shlex.quote(str(target)) + ' .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
        return page(request, 'backups.html', restored_path=str(target), startup_command=command,
                    backup_limit_mb=MAX_BACKUP_UPLOAD // (1024 * 1024))

    @app.get('/')
    async def index(request: Request):
        return page(request, 'index.html', books=app.state.store.list_books())

    @app.post('/books/epub')
    async def import_epub(request: Request):
        data = await form(request)
        from app.epub import MAX_RAW
        raw = await upload(data, MAX_RAW)
        title = str(data.get('title', '')).strip() or None
        book_id = await run_in_threadpool(app.state.store.import_epub, raw, title)
        return RedirectResponse(f'/books/{book_id}', 303)

    @app.post('/preview')
    async def preview(request: Request):
        data = await form(request)
        raw = await upload(data)
        title = str(data.get('title', '')).strip()
        chapters = app.state.store.preview_txt(raw, title, split_headings='split_headings' in data)
        if len(chapters) > 250:
            raise DomainError('Quá 250 chương; bỏ chọn tách heading để nhập một chương.')
        return page(request, 'preview.html', title=title, raw=base64.b64encode(raw).decode(), chapters=chapters)

    @app.post('/books')
    async def confirm(request: Request):
        data = await form(request)
        try:
            raw = base64.b64decode(str(data.get('raw', '')), validate=True)
            count = int(str(data.get('count', '')))
            if not 1 <= count <= 250 or not raw or len(raw) > MAX_FILE:
                raise ValueError
            chapters = [{'title': str(data[f'title_{i}']), 'text': str(data[f'text_{i}']).replace('\r\n', '\n').replace('\r', '\n')} for i in range(count)]
        except (ValueError, KeyError, binascii.Error):
            raise DomainError('Dữ liệu xem trước không hợp lệ.')
        book_id = app.state.store.import_txt(raw, str(data.get('title', '')), chapters)
        return RedirectResponse(f'/books/{book_id}', 303)

    @app.get('/books/{book_id}')
    async def book(request: Request, book_id: str):
        data = app.state.store.get_book(book_id)
        data['real_jobs'] = app.state.store.list_real_jobs(book_id)
        return page(request, 'book.html', book=data)

    @app.get('/books/{book_id}/glossary')
    async def glossary(request: Request, book_id: str):
        return page(request, 'glossary.html', book=app.state.store.get_book(book_id),
                    glossary=app.state.store.get_glossary(book_id))

    def glossary_form(data):
        return {'term': str(data.get('term', '')), 'translation': str(data.get('translation', '')),
                'aliases': [line for line in str(data.get('aliases', '')).splitlines() if line],
                'notes': str(data.get('notes', ''))}

    @app.post('/books/{book_id}/glossary')
    async def add_glossary_entry(request: Request, book_id: str):
        data = await form(request)
        current = app.state.store.get_glossary(book_id)
        entries = current['entries'] + [glossary_form(data)]
        try:
            revision = int(str(data.get('revision', '')))
        except ValueError:
            raise DomainError('Revision không hợp lệ.')
        app.state.store.save_glossary(book_id, entries, revision)
        return RedirectResponse(f'/books/{book_id}/glossary', 303)

    @app.post('/books/{book_id}/glossary/{entry_index}')
    async def edit_glossary_entry(request: Request, book_id: str, entry_index: int):
        data = await form(request)
        current = app.state.store.get_glossary(book_id)
        try:
            revision = int(str(data.get('revision', '')))
        except ValueError:
            raise DomainError('Revision không hợp lệ.')
        if revision != current['revision']:
            raise DomainError('Glossary đã được thay đổi ở tab khác. Tải lại trang trước khi lưu.', 409)
        if not 0 <= entry_index < len(current['entries']):
            raise DomainError('Glossary entry not found.', 404)
        entries = current['entries'][:]
        if data.get('action') == 'remove':
            entries.pop(entry_index)
        else:
            entries[entry_index] = glossary_form(data)
        app.state.store.save_glossary(book_id, entries, revision)
        return RedirectResponse(f'/books/{book_id}/glossary', 303)

    @app.post('/books/{book_id}/jobs')
    async def job(request: Request, book_id: str):
        await form(request)
        app.state.store.create_job(book_id)
        return RedirectResponse(f'/books/{book_id}', 303)

    @app.post('/books/{book_id}/jobs/{job_id}/run')
    async def run(request: Request, book_id: str, job_id: str):
        await form(request)
        if app.state.store._job_book(job_id) != book_id:
            raise DomainError('Job not found for this book.', 404)
        app.state.store.run_fake(job_id, limit=1)
        return RedirectResponse(f'/books/{book_id}', 303)

    @app.get('/jobs/{job_id}/manifest')
    async def manifest(job_id: str):
        from app.bundles import canonical_bytes
        return Response(canonical_bytes(app.state.store.get_manifest(job_id)), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="manifest.json"'})

    @app.post('/results')
    async def result(request: Request):
        data = await form(request)
        status = app.state.store.import_result(await upload(data))
        return page(request, 'error.html', message=f'Kết quả: {status}. Dữ liệu đã được kiểm tra.', success=True)

    @app.post('/books/{book_id}/chunks/{chunk_id}')
    async def save(request: Request, book_id: str, chunk_id: str):
        data = await form(request)
        if app.state.store.chunk_book(chunk_id) != book_id:
            raise DomainError('Chunk not found for this book.', 404)
        try:
            revision = int(str(data.get('revision', '')))
        except ValueError:
            raise DomainError('Revision không hợp lệ.')
        app.state.store.save_revision(chunk_id, str(data.get('text', '')), revision, str(data.get('base_result_hash', '')) or None)
        return RedirectResponse(f'/books/{book_id}#chunk-{chunk_id}', 303)

    @app.post('/books/{book_id}/real-jobs')
    async def create_real_job(request: Request, book_id: str):
        await form(request)
        app.state.store.get_book(book_id)
        from app.real_bundles import QWEN35, MODELS, default_snapshot, load_tokenizer
        try:
            tokenizer, commit = await run_in_threadpool(load_tokenizer, QWEN35, MODELS[QWEN35])
        except ImportError as exc:
            raise DomainError('Thiếu tokenizer. Cài extra .[tokenizer] rồi thử lại.') from exc
        except Exception as exc:
            raise DomainError('Không tải được tokenizer Qwen3.5. Hãy kiểm tra kết nối rồi thử lại.') from exc
        snap = default_snapshot(QWEN35, commit, tokenizer.chat_template)
        job_id = await run_in_threadpool(app.state.store.create_real_job, book_id, tokenizer, snap)
        return RedirectResponse(f'/books/{book_id}/real-jobs/{job_id}', 303)

    @app.get('/translate-notebook')
    async def translate_notebook():
        path = HERE.parent / 'notebooks' / 'translate.ipynb'
        if not path.is_file():
            raise DomainError('Notebook dịch batch chưa được tạo.', 404)
        return Response(path.read_bytes(), media_type='application/x-ipynb+json',
                        headers={'Content-Disposition': 'attachment; filename="translate.ipynb"'})

    def own_real_job(book_id, job_id):
        if app.state.store.real_job_book(job_id) != book_id:
            raise DomainError('Real job not found for this book.', 404)

    @app.get('/books/{book_id}/real-jobs/{job_id}')
    async def real_review(request: Request, book_id: str, job_id: str):
        own_real_job(book_id, job_id)
        job = app.state.store.get_real_job(job_id)
        chapters = sorted({item['chunk']['chapter_ordinal'] for item in job['chunks']})
        try:
            chapter = int(request.query_params.get('chapter', chapters[0]))
        except ValueError:
            raise DomainError('Chapter ordinal không hợp lệ.')
        if chapter not in chapters:
            raise DomainError('Chapter ordinal không tồn tại.', 404)
        review_filter = request.query_params.get('filter', 'all')
        if review_filter not in {'all', 'pending', 'unreviewed', 'approved'}:
            raise DomainError('Bộ lọc review không hợp lệ.')
        def matches(item):
            result, revision = item['result'], item['revision']
            approved = bool(result and revision and revision['approved'] and not item['stale'])
            return (review_filter == 'all' or
                    review_filter == 'pending' and result is None or
                    review_filter == 'unreviewed' and result is not None and not approved or
                    review_filter == 'approved' and approved)
        job['chunks'] = [item for item in job['chunks'] if item['chunk']['chapter_ordinal'] == chapter and matches(item)]
        return page(request, 'real_job.html', book=app.state.store.get_book(book_id),
                    glossary=app.state.store.get_glossary(book_id), job=job, chapters=chapters,
                    chapter=chapter, review_filter=review_filter,
                    previous_chapter=chapters[chapters.index(chapter) - 1] if chapter != chapters[0] else None,
                    next_chapter=chapters[chapters.index(chapter) + 1] if chapter != chapters[-1] else None)

    @app.get('/books/{book_id}/real-jobs/{job_id}/manifest')
    async def real_manifest(book_id: str, job_id: str):
        own_real_job(book_id, job_id)
        from app.real_bundles import canonical_bytes
        return Response(canonical_bytes(app.state.store.get_real_manifest(job_id)), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="manifest.json"'})

    @app.post('/books/{book_id}/real-jobs/{job_id}/results')
    async def real_result(request: Request, book_id: str, job_id: str):
        data = await form(request)
        own_real_job(book_id, job_id)
        raw = await upload(data)
        from app.bundles import load_json
        try:
            payload = load_json(raw)
            if payload.get('job_id') != job_id:
                raise DomainError('Result belongs to a different job.')
        except AttributeError:
            raise DomainError('Invalid real result JSON.')
        status = app.state.store.import_real_result(raw)
        return page(request, 'error.html', message=f'Kết quả: {status}. Dữ liệu đã được kiểm tra.', success=True)

    @app.post('/books/{book_id}/real-jobs/{job_id}/results/bulk')
    async def real_results_bulk(request: Request, book_id: str, job_id: str):
        from app.bulk_results import MAX_FILE as BULK_FILE, check_upload_total, inspect_zip
        from app.bundles import load_json
        data = await form(request, max_files=100, max_part_size=MAX_BULK_BODY)
        uploads = [item for _, item in data.multi_items() if isinstance(item, UploadFile)]
        files = []
        try:
            own_real_job(book_id, job_id)
            if len(uploads) > 100:
                raise DomainError('Tối đa 100 tệp mỗi lần upload.', 413)
            if len(uploads) == 1 and (uploads[0].filename or '').lower().endswith('.zip'):
                archive = await uploads[0].read(MAX_BULK_BODY + 1)
                if len(archive) > MAX_BULK_BODY:
                    raise DomainError('ZIP vượt giới hạn 32 MiB.', 413)
                files = inspect_zip(archive)
            else:
                if any((item.filename or '').lower().endswith('.zip') for item in uploads):
                    raise DomainError('Không thể trộn ZIP với các file result riêng.')
                files = [(item.filename or 'result.json', await item.read(BULK_FILE + 1)) for item in uploads]
                check_upload_total(files)
            check_upload_total(files)
            report = []
            for filename, raw in files:
                try:
                    if len(raw) > BULK_FILE:
                        raise DomainError('JSON vượt giới hạn 1 MiB.', 413)
                    payload = load_json(raw)
                    if not isinstance(payload, dict) or payload.get('job_id') != job_id:
                        raise DomainError('Result thuộc job khác hoặc thiếu job_id.')
                    status = app.state.store.import_real_result(raw)
                    report.append({'filename': filename, 'status': status})
                except DomainError as exc:
                    report.append({'filename': filename, 'status': 'rejected', 'message': str(exc)})
            return page(request, 'result_import.html', book=app.state.store.get_book(book_id), job_id=job_id,
                        report=report, imported=sum(x['status'] == 'imported' for x in report),
                        duplicates=sum(x['status'] == 'duplicate' for x in report),
                        rejected=sum(x['status'] == 'rejected' for x in report))
        finally:
            for item in uploads:
                await item.close()

    @app.post('/books/{book_id}/real-jobs/{job_id}/chunks/{chunk_id}')
    async def save_real(request: Request, book_id: str, job_id: str, chunk_id: str):
        data = await form(request)
        own_real_job(book_id, job_id)
        try:
            revision = int(str(data.get('revision', '')))
        except ValueError:
            raise DomainError('Revision không hợp lệ.')
        approve = data.get('approved') == 'true'
        app.state.store.save_real_revision(job_id, chunk_id, str(data.get('text', '')), revision,
                                           str(data.get('base_result_hash', '')) or None, approve)
        try:
            chapter = int(str(data.get('chapter', '')))
        except ValueError:
            chapter = 0
        review_filter = str(data.get('filter', 'all'))
        if review_filter not in {'all', 'pending', 'unreviewed', 'approved'}:
            review_filter = 'all'
        chapters = {chunk['chapter_ordinal'] for chunk in app.state.store.get_real_manifest(job_id)['chunks']}
        if chapter not in chapters:
            chapter = min(chapters) if chapters else 0
        return RedirectResponse(f'/books/{book_id}/real-jobs/{job_id}?chapter={chapter}&filter={review_filter}#chunk-{chunk_id}', 303)

    @app.get('/books/{book_id}/real-jobs/{job_id}/export')
    async def export_real(book_id: str, job_id: str, draft: bool = False):
        own_real_job(book_id, job_id)
        content = app.state.store.export_real_txt(job_id, draft=draft)
        suffix = '-draft' if draft else ''
        return Response(content, media_type='text/plain; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{job_id}{suffix}.txt"'})

    @app.get('/books/{book_id}/real-jobs/{job_id}/export.epub')
    async def export_real_epub(book_id: str, job_id: str):
        own_real_job(book_id, job_id)
        content = await run_in_threadpool(app.state.store.export_real_epub, job_id)
        return Response(content, media_type='application/epub+zip',
                        headers={'Content-Disposition': f'attachment; filename="{job_id}.epub"'})

    @app.get('/books/{book_id}/export')
    async def export(book_id: str, draft: bool = False):
        text = app.state.store.export_txt(book_id, draft=draft)
        return Response(text, media_type='text/plain; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="book{"-draft" if draft else ""}.txt"'})

    return app


app = create_app()
