import io
import re
import zipfile
from html import unescape

from fastapi.testclient import TestClient

from app.main import create_app


def epub(padding=b''):
    items = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'book.opf': b'<package xmlns="http://www.idpf.org/2007/opf"><metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Fixture title</dc:title></metadata><manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>',
        'c.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter</h1><p>Small fixture.</p></body></html>',
    }
    if padding:
        items['unused.bin'] = padding
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in items.items(): archive.writestr(name, raw)
    return out.getvalue()


def fields(response):
    return {k: unescape(v) for k, v in re.findall(r'name="([^"]+)" value="([^"]*)"', response.text)}


def test_epub_form_import_metadata_large_raw_and_idempotency(tmp_path):
    raw = epub(b'x' * (1024 * 1024 + 100))
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        home = client.get('/')
        assert 'Nhập EPUB' in home.text and 'accept=".epub,application/epub+zip"' in home.text
        token = fields(home)['csrf']
        response = client.post('/books/epub', data={'csrf': token}, files={'file': ('fixture.epub', raw)}, follow_redirects=False)
        assert response.status_code == 303
        book_url = response.headers['location']
        assert 'Fixture title' in client.get(book_url).text
        assert client.post('/books/epub', data={'csrf': token}, files={'file': ('fixture.epub', raw)}, follow_redirects=False).headers['location'] == book_url
        assert len(client.app.state.store.list_books()) == 1
        invalid = client.post('/books/epub', data={'csrf': token}, files={'file': ('bad.epub', b'bad')})
        assert invalid.status_code == 400 and len(client.app.state.store.list_books()) == 1
        too_large_txt = client.post('/preview', data={'csrf': token, 'title': 'large'}, files={'file': ('large.txt', b'x' * (1024 * 1024 + 1))})
        assert too_large_txt.status_code == 413
