import io
import re
import zipfile
import asyncio
from html import unescape

from fastapi.testclient import TestClient

from app.bulk_results import inspect_zip
from app.core import DomainError
from app.main import create_app
from app.main import LocalBoundary
from app.real_bundles import make_result, provenance


class TinyTokenizer:
    chat_template = 'tiny-template'
    def encode(self, text, add_special_tokens=False): return list(text.encode())
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        return list(''.join(m['content'] for m in messages).encode())


def fields(response):
    return {k: unescape(v) for k, v in re.findall(r'name="([^"]+)" value="([^"]*)"', response.text)}


def archive(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, raw in entries:
            z.writestr(name, raw)
    return out.getvalue()


def test_zip_preflight_rejects_entire_container_before_returning_results():
    good = b'{"ok": true}'
    for files in [[('one.json', good), ('../escape.json', good)],
                  [('one.json', good), ('one.json', good)], [('one.json', good), ('notes.txt', b'no')]]:
        try:
            inspect_zip(archive(files))
        except DomainError:
            pass
        else:
            raise AssertionError('unsafe or unsupported archive accepted')
    assert inspect_zip(archive([('manifest.json', b'{}'), ('run/one.json', good)])) == [('run/one.json', good)]


def test_bulk_body_limit_is_path_specific():
    async def exercise(path):
        seen = []
        async def downstream(scope, receive, send):
            seen.append(await receive())
        body = b'x' * (5 * 1024 * 1024 + 1)
        scope = {'type': 'http', 'method': 'POST', 'path': path, 'scheme': 'http',
                 'headers': [(b'host', b'127.0.0.1')]}
        sent = []
        async def receive(): return {'type': 'http.request', 'body': body, 'more_body': False}
        async def send(message): sent.append(message)
        await LocalBoundary(downstream)(scope, receive, send)
        return seen, sent
    bulk, _ = asyncio.run(exercise('/books/b/real-jobs/j/results/bulk'))
    epub_body, _ = asyncio.run(exercise('/books/epub'))
    ordinary, response = asyncio.run(exercise('/results'))
    assert len(bulk[0]['body']) == 5 * 1024 * 1024 + 1
    assert len(epub_body[0]['body']) == 5 * 1024 * 1024 + 1
    assert response[0]['status'] == 413 and ordinary == []


def test_bulk_import_duplicate_bad_items_late_edit_and_scoped_access(tmp_path, monkeypatch):
    from app import real_bundles
    from app.bundles import now
    monkeypatch.setattr(real_bundles, 'load_tokenizer', lambda model, revision: (TinyTokenizer(), revision))
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        token = fields(client.get('/'))['csrf']
        preview = client.post('/preview', data={'csrf': token, 'title': 'Book'}, files={'file': ('b.txt', b'source')})
        book_url = client.post('/books', data=fields(preview) | {'text_0': 'source'}).url.path
        other_preview = client.post('/preview', data={'csrf': token, 'title': 'Other'}, files={'file': ('o.txt', b'other')})
        other_url = client.post('/books', data=fields(other_preview) | {'text_0': 'other'}).url.path
        job_url = client.post(book_url + '/real-jobs', data={'csrf': token}, follow_redirects=False).headers['location']
        manifest = client.get(job_url + '/manifest').json()
        chunk = manifest['chunks'][0]
        stamp = now()
        result = make_result(manifest, chunk, {'translated_text': 'Machine', 'output_tokens': 1,
            'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
        raw = real_bundles.canonical_bytes(result)
        bulk = job_url + '/results/bulk'
        assert client.post(bulk, files=[('files', ('a.json', raw)), ('files', ('b.json', raw))]).status_code == 403
        response = client.post(bulk, data={'csrf': token}, files=[('files', ('a.json', raw)), ('files', ('b.json', raw)),
            ('files', ('bad.json', b'{bad')), ('files', ('wrong.json', b'{"job_id":"other"}')),
            ('files', ('oversized.json', b'x' * (1024 * 1024 + 1)))])
        assert response.status_code == 200
        assert '1 đã nhập · 1 trùng · 3 bị từ chối' in response.text
        assert all(name in response.text for name in ['bad.json', 'wrong.json', 'oversized.json'])
        job_id = job_url.rsplit('/', 1)[-1]
        assert client.post(other_url + f'/real-jobs/{job_id}/results/bulk', data={'csrf': token},
                           files={'files': ('a.json', raw)}).status_code == 404
        assert client.post(job_url + '/results', data={'csrf': token}, files={'file': ('a.json', raw)}).status_code == 200
        review = client.get(job_url)
        form = fields(review)
        action = re.search(r'<form method="post" action="([^"]+/chunks/[^"]+)', review.text)[1]
        form.update(text='Manual edit', approved='false', csrf=token)
        client.post(action, data=form)
        assert client.post(bulk, data={'csrf': token}, files={'files': ('a.json', raw)}).status_code == 200
        assert 'Manual edit' in client.get(job_url).text

        extra = make_result(manifest, chunk, {'translated_text': 'Other result', 'output_tokens': 1,
            'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
        unsafe = archive([('valid.json', real_bundles.canonical_bytes(extra)), ('../evil.json', raw)])
        before = client.get(job_url).text
        rejected = client.post(bulk, data={'csrf': token}, files={'files': ('results.zip', unsafe)})
        assert rejected.status_code == 400
        assert client.get(job_url).text == before
