"""Local, explicitly operated fake translation review interface."""
import base64
import binascii
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from app.core import DomainError, Store

MAX_FILE = 1024 * 1024
MAX_BODY = 5 * 1024 * 1024
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
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > MAX_BODY:
                return await PlainTextResponse('Tệp hoặc biểu mẫu quá lớn (tối đa 5 MiB).', 413)(scope, receive, send)
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

    async def form(request):
        data = await request.form(max_files=1, max_fields=1000, max_part_size=MAX_BODY)
        token = data.get('csrf', '')
        if not isinstance(token, str) or not secrets.compare_digest(token, app.state.csrf):
            raise DomainError('Biểu mẫu hết hạn hoặc thiếu mã CSRF. Tải lại trang.', 403)
        return data

    async def upload(data):
        item = data.get('file')
        if not isinstance(item, UploadFile):
            raise DomainError('Hãy chọn một tệp.')
        raw = await item.read(MAX_FILE + 1)
        await item.close()
        if len(raw) > MAX_FILE:
            raise DomainError('Tệp vượt giới hạn 1 MiB.', 413)
        return raw

    @app.get('/')
    async def index(request: Request):
        return page(request, 'index.html', books=app.state.store.list_books())

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
        return page(request, 'book.html', book=app.state.store.get_book(book_id))

    @app.post('/books/{book_id}/jobs')
    async def job(request: Request, book_id: str):
        await form(request)
        app.state.store.create_job(book_id)
        return RedirectResponse(f'/books/{book_id}', 303)

    @app.post('/books/{book_id}/jobs/{job_id}/run')
    async def run(request: Request, book_id: str, job_id: str):
        await form(request)
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
        try:
            revision = int(str(data.get('revision', '')))
        except ValueError:
            raise DomainError('Revision không hợp lệ.')
        app.state.store.save_revision(chunk_id, str(data.get('text', '')), revision, str(data.get('base_result_hash', '')) or None)
        return RedirectResponse(f'/books/{book_id}#chunk-{chunk_id}', 303)

    @app.get('/books/{book_id}/export')
    async def export(book_id: str, draft: bool = False):
        text = app.state.store.export_txt(book_id, draft=draft)
        return Response(text, media_type='text/plain; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="book{"-draft" if draft else ""}.txt"'})

    return app


app = create_app()
