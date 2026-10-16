import re
from html import unescape
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import Store
from app.main import create_app


def csrf(response):
    return unescape(re.search(r'name="csrf" value="([^"]+)"', response.text)[1])


def make_library(path):
    store = Store(path)
    raw = b'Chapter 1\n\nSynthetic recovery source.'
    book = store.import_txt(raw, 'Synthetic recovery', store.preview_txt(raw, 'Synthetic recovery'))
    return store, book


def test_backup_download_and_restore_to_sibling_keeps_running_library_unchanged(tmp_path):
    data_dir = tmp_path / 'current'
    store, book = make_library(data_dir)
    with TestClient(create_app(data_dir), base_url='http://127.0.0.1') as client:
        page = client.get('/backups')
        token = csrf(page)
        assert '64 MiB' in page.text and 'Khôi phục' in page.text
        download = client.post('/backups/create', data={'csrf': token})
        assert download.status_code == 200
        assert download.headers['content-type'] == 'application/zip'
        assert download.headers['content-disposition'].endswith('novel-translate-backup.zip"')
        assert b'backup-manifest.json' in download.content
        assert len(store.list_books()) == 1
        restored = client.post('/backups/restore', data={'csrf': token},
                               files={'file': ('backup.zip', download.content, 'application/zip')})
        assert restored.status_code == 200
        assert 'Thư viện đang chạy không đổi' in restored.text
        path = unescape(re.search(r'<code>([^<]+)</code>', restored.text)[1])
        recovered = Store(Path(path))
        assert len(recovered.list_books()) == 1
        assert recovered.list_books()[0]['id'] == book
        assert len(store.list_books()) == 1


def test_restore_rejects_bad_zip_and_csrf_without_mutating_current_library(tmp_path):
    data_dir = tmp_path / 'current'
    store, _ = make_library(data_dir)
    with TestClient(create_app(data_dir), base_url='http://127.0.0.1') as client:
        token = csrf(client.get('/backups'))
        forbidden = client.post('/backups/restore', data={'csrf': 'wrong'},
                                files={'file': ('bad.zip', b'bad', 'application/zip')})
        assert forbidden.status_code == 403
        rejected = client.post('/backups/restore', data={'csrf': token},
                               files={'file': ('bad.zip', b'bad', 'application/zip')})
        assert rejected.status_code == 400
        assert len(store.list_books()) == 1
        assert not list(tmp_path.glob('current-restored-*'))
