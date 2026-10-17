import re
import sqlite3
from html import unescape

from fastapi.testclient import TestClient

from app.bundles import now
from app.main import create_app
from app.real_bundles import make_result, provenance


class TinyTokenizer:
    chat_template = 'tiny'
    def encode(self, text, add_special_tokens=False): return list(text.encode())
    def apply_chat_template(self, messages, **kwargs): return list(''.join(m['content'] for m in messages).encode())


def fields(response):
    return {k: unescape(v) for k, v in re.findall(r'name="([^"]+)" value="([^"]*)"', response.text)}


def test_chapter_filter_counts_and_save_return_state(tmp_path, monkeypatch):
    from app import real_bundles
    monkeypatch.setattr(real_bundles, 'load_tokenizer', lambda model, revision: (TinyTokenizer(), revision))
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        store = client.app.state.store
        book = store.import_txt(b'one\ntwo', 'Two chapters', [{'title': 'One', 'text': 'one\n'}, {'title': 'Two', 'text': 'two'}])
        token = fields(client.get('/'))['csrf']
        book_chapters = store.get_book(book)['chapters']
        chapter_ids = [chapter['id'] for chapter in book_chapters]
        chunk_ids = [chapter['chunks'][0]['id'] for chapter in book_chapters]
        get_book = store.get_book
        def scoped_book(book_id, chapter_ordinal=None):
            assert chapter_ordinal is not None
            return get_book(book_id, chapter_ordinal)
        monkeypatch.setattr(store, 'get_book', scoped_book)
        statements = []
        connect = sqlite3.connect
        def traced_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        monkeypatch.setattr(sqlite3, 'connect', traced_connect)
        book_page = client.get(f'/books/{book}')
        assert '1. One' in book_page.text and 'id="chunk-' + chunk_ids[0] + '"' in book_page.text
        assert 'id="chunk-' + chunk_ids[1] + '"' not in book_page.text
        assert 'value="1"' in book_page.text and 'Chương tiếp' in book_page.text
        assert not any('FROM chunks WHERE chapter_id=' in sql and chapter_ids[1] in sql for sql in statements)
        statements.clear()
        chapter_two_page = client.get(f'/books/{book}?chapter=1')
        assert 'id="chunk-' + chunk_ids[1] + '"' in chapter_two_page.text
        assert re.search(r'<option value="1" selected>', chapter_two_page.text)
        assert any('FROM chunks WHERE chapter_id=' in sql and chapter_ids[1] in sql for sql in statements)
        assert client.get(f'/books/{book}?chapter=x').status_code == 400
        assert client.get(f'/books/{book}?chapter=99').status_code == 404
        monkeypatch.setattr(store, 'get_book', get_book)
        monkeypatch.setattr(sqlite3, 'connect', connect)
        job_url = client.post(f'/books/{book}/real-jobs', data={'csrf': token}, follow_redirects=False).headers['location']
        manifest = client.get(job_url + '/manifest').json()
        assert len(manifest['chunks']) == 2
        assert [len(chapter['chunks']) for chapter in store.get_book(book)['chapters']] == [1, 1]
        full_job = store.get_real_job(manifest['job_id'])
        statements = []
        monkeypatch.setattr(sqlite3, 'connect', traced_connect)
        selected_book = store.get_book(book, 1)
        assert [len(chapter['chunks']) for chapter in selected_book['chapters']] == [0, 1]
        selected_job = store.get_real_job(manifest['job_id'], 1)
        monkeypatch.setattr(sqlite3, 'connect', connect)
        assert len(full_job['chunks']) == 2 and len(selected_job['chunks']) == 1
        assert (selected_job['completed'], selected_job['total']) == (0, 2)
        assert any('FROM chunks WHERE chapter_id=' in sql and selected_book['chapters'][1]['id'] in sql for sql in statements)
        assert not any('FROM chunks WHERE chapter_id=' in sql and selected_book['chapters'][0]['id'] in sql for sql in statements)
        assert any('FROM real_chunks c LEFT JOIN' in re.sub(r'\s+', ' ', sql) and
                   re.search(r'chapter_ordinal\s*=\s*1\b', sql) for sql in statements)
        monkeypatch.setattr(sqlite3, 'connect', connect)
        get_real_job = store.get_real_job
        def scoped_real_job(job_id, chapter_ordinal=None):
            assert chapter_ordinal is not None
            return get_real_job(job_id, chapter_ordinal)
        monkeypatch.setattr(store, 'get_real_job', scoped_real_job)
        statements.clear()
        monkeypatch.setattr(sqlite3, 'connect', traced_connect)
        default = client.get(job_url)
        monkeypatch.setattr(store, 'get_real_job', get_real_job)
        monkeypatch.setattr(sqlite3, 'connect', connect)
        assert 'Chương 1 · chunk 1' in default.text and 'Chương 2 · chunk 1' not in default.text
        assert '0/2 checkpoint' in default.text
        assert any('FROM real_chunks c LEFT JOIN' in re.sub(r'\s+', ' ', sql) and
                   re.search(r'chapter_ordinal\s*=\s*0\b', sql) for sql in statements)
        assert not any('FROM real_revisions' in sql and chunk_ids[1] in sql for sql in statements)
        assert not any('SELECT * FROM chunks' in sql or 'SELECT * FROM chapters' in sql for sql in statements)
        first = manifest['chunks'][0]
        stamp = now()
        result = make_result(manifest, first, {'translated_text': 'First', 'output_tokens': 1,
            'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
        client.post(job_url + '/results', data={'csrf': token}, files={'file': ('r.json', real_bundles.canonical_bytes(result))})
        assert 'chunk 1' in client.get(job_url + '?chapter=0&filter=unreviewed').text
        assert 'chunk 1' not in client.get(job_url + '?chapter=0&filter=pending').text
        assert 'chunk 1' not in client.get(job_url + '?chapter=0&filter=approved').text
        store.save_real_revision(manifest['job_id'], first['chunk_id'], 'Approved edit', 0, result['checksum'], True)
        with store._connect() as db:
            db.execute('UPDATE real_revisions SET base_result_hash=? WHERE job_id=? AND chunk_id=?',
                       ('changed-checksum', manifest['job_id'], first['chunk_id']))
        assert 'chunk 1' not in client.get(job_url + '?chapter=0&filter=approved').text
        stale_page = client.get(job_url + '?chapter=0&filter=unreviewed')
        assert 'chunk 1' in stale_page.text and 'Bản sửa đã cũ' in stale_page.text
        page = client.get(job_url + '?chapter=1&filter=pending')
        assert 'Chương 2 · chunk 1' in page.text and 'Chương 1 · chunk 1' not in page.text
        assert '2. Two' in page.text
        action = re.search(r'<form method="post" action="([^"]+/chunks/[^"]+)', page.text)[1]
        data = fields(page) | {'csrf': token, 'text': 'Second edit', 'approved': 'false'}
        data['chapter'] = '0'  # Redirect state comes from the addressed chunk, not this hidden field.
        saved = client.post(action, data=data, follow_redirects=False)
        assert saved.headers['location'].endswith('?chapter=1&filter=pending#chunk-' + manifest['chunks'][1]['chunk_id'])
        assert client.get(job_url + '?chapter=invalid').status_code == 400
        assert client.get(job_url + '?chapter=9').status_code == 404
        fake_job = store.create_job(book)
        store.run_fake(fake_job)
        store.run_fake(fake_job)
        fake_page = client.get(f'/books/{book}?chapter=1')
        fake_action = re.search(r'<form method="post" action="([^\"]+/chunks/[^\"]+)', fake_page.text)[1]
        fake_data = fields(fake_page) | {'csrf': token, 'text': 'P1 manual edit'}
        fake_saved = client.post(fake_action, data=fake_data, follow_redirects=False)
        assert fake_saved.headers['location'].endswith('?chapter=1#chunk-' + chunk_ids[1])
        saved_page = client.get(fake_saved.headers['location'])
        assert re.search(r'<option value="1" selected>', saved_page.text)
