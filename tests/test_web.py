import asyncio
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app.main import MAX_BODY, MAX_FILE, LocalBoundary, create_app


def test_boundary_replays_body_once_then_preserves_disconnect():
    messages = iter([
        {'type': 'http.request', 'body': b'first ', 'more_body': True},
        {'type': 'http.request', 'body': b'second', 'more_body': False},
        {'type': 'http.disconnect'},
    ])

    async def receive():
        return next(messages)

    async def downstream(scope, receive, send):
        assert await receive() == {'type': 'http.request', 'body': b'first second', 'more_body': False}
        assert await receive() == {'type': 'http.disconnect'}

    scope = {'type': 'http', 'method': 'GET', 'scheme': 'http', 'headers': [(b'host', b'127.0.0.1')]}
    asyncio.run(LocalBoundary(downstream)(scope, receive, None))


def fields(response):
    return {name: unescape(value) for name, value in re.findall(r'name="([^"]+)" value="([^"]*)"', response.text)}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        yield client


def import_book(client):
    token = fields(client.get('/'))['csrf']
    preview = client.post('/preview', data={'csrf': token, 'title': '<script>title</script>'}, files={'file': ('book.txt', b'An invented tiny story. <script>alert(1)</script>')})
    assert preview.status_code == 200
    data = fields(preview)
    data['text_0'] = 'An invented tiny story. <script>alert(1)</script>'
    response = client.post('/books', data=data)
    assert response.status_code == 200, response.text
    return response, token


def test_full_review_flow_and_conflict(client):
    book, token = import_book(client)
    url = book.url.path
    assert '&lt;script&gt;' in book.text and '<script>' not in book.text
    assert client.get(url + '/export').status_code == 400
    assert client.get(url + '/export?draft=true').status_code == 200
    book = client.post(url + '/jobs', data={'csrf': token})
    run_url = re.search(r'action="([^"]+/run)"', book.text)[1]
    manifest_url = re.search(r'href="(/jobs/[^"]+/manifest)"', book.text)[1]
    assert client.get(manifest_url).json()['schema_version'] == 1
    book = client.post(run_url, data={'csrf': token})
    assert '1/1 chunk' in book.text
    edit_url = re.search(r'action="([^"]+/chunks/[^"]+)"', book.text)[1]
    edit = fields(book)
    edit['text'] = 'Bản sửa thử nghiệm.'
    assert client.post(edit_url, data=edit).status_code == 200
    assert client.post(edit_url, data=edit).status_code == 409
    assert 'Bản sửa thử nghiệm.' in client.get(url + '/export').text
    assert client.post(run_url, data={'csrf': token}).status_code == 200
    assert 'Bản sửa thử nghiệm.' in client.get(url + '/export').text


def test_csrf_origin_host_and_upload_bounds(client):
    token = fields(client.get('/'))['csrf']
    assert client.post('/preview', data={'title': 'x'}).status_code == 403
    assert client.post('/preview', headers={'origin': 'https://evil.example'}, data={'csrf': token}).status_code == 403
    assert client.post('/preview', headers={'sec-fetch-site': 'cross-site'}, data={'csrf': token}).status_code == 403
    assert client.get('/', headers={'host': 'evil.example'}).status_code == 403
    assert client.post('/preview', data={'csrf': token}, files={'file': ('large.txt', b'x' * (MAX_FILE + 1))}).status_code == 413
    def streamed():
        for _ in range(6):
            yield b'x' * (MAX_BODY // 5)
    assert client.post('/preview', content=streamed()).status_code == 413


def test_bad_preview_order_and_rejected_result(client):
    token = fields(client.get('/'))['csrf']
    preview = client.post('/preview', data={'csrf': token, 'title': 'Test'}, files={'file': ('book.txt', b'A small story.')})
    data = fields(preview)
    data.update(text_0='Changed source.')
    assert client.post('/books', data=data).status_code == 400
    response = client.post('/results', data={'csrf': token}, files={'file': ('result.json', b'<script>invalid</script>')})
    assert response.status_code == 400
    assert '<script>' not in response.text


def test_browser_newlines_and_result_upload(client):
    from app.bundles import canonical_bytes, fake_result
    token = fields(client.get('/'))['csrf']
    preview = client.post('/preview', data={'csrf': token, 'title': 'Newlines'}, files={'file': ('book.txt', b'First line.\nSecond line.\n')})
    data = fields(preview)
    data['text_0'] = 'First line.\r\nSecond line.\r\n'
    book = client.post('/books', data=data)
    assert book.status_code == 200
    book = client.post(book.url.path + '/jobs', data={'csrf': token})
    manifest_url = re.search(r'href="(/jobs/[^"]+/manifest)"', book.text)[1]
    manifest = client.get(manifest_url).json()
    edit_url = re.search(r'action="([^"]+/chunks/[^"]+)"', book.text)[1]
    edit = fields(book)
    edit['text'] = 'Bản sửa trước khi nhận kết quả.'
    assert client.post(edit_url, data=edit).status_code == 200
    raw = canonical_bytes(fake_result(manifest, manifest['chunks'][0]))
    for expected in ('imported', 'duplicate'):
        response = client.post('/results', data={'csrf': token}, files={'file': ('result.json', raw)})
        assert response.status_code == 200
        assert expected in response.text

    review = client.get(book.url.path)
    assert 'Bản sửa tay dựa trên kết quả máy trước đó' in review.text
    assert 'Bản sửa trước khi nhận kết quả.' in review.text
    assert 'Bản sửa trước khi nhận kết quả.' in client.get(book.url.path + '/export').text
