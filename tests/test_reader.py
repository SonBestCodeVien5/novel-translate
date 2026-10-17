import re
import socket

import pytest
from fastapi.testclient import TestClient

from app.bundles import now
from app.main import create_app
from app.real_bundles import canonical_bytes, make_result, provenance


class TinyTokenizer:
    chat_template = 'tiny'

    def encode(self, text, add_special_tokens=False):
        return list(text.encode())

    def apply_chat_template(self, messages, **kwargs):
        return list(''.join(message['content'] for message in messages).encode())


def setup_library(tmp_path, monkeypatch):
    from app import real_bundles

    monkeypatch.setattr(real_bundles, 'load_tokenizer', lambda model, revision: (TinyTokenizer(), revision))
    client = TestClient(create_app(tmp_path), base_url='http://127.0.0.1')
    client.__enter__()
    token = re.search(r'name="csrf" value="([^"]+)"', client.get('/').text)[1]
    store = client.app.state.store
    source_one = '<script>RAW ONE</script>\n'
    source_two = 'RAW TWO & <script>bad</script>. ' * 90
    book_id = store.import_txt(source_one.encode() + source_two.encode(), '<script>Book</script>', [
        {'title': 'One', 'text': source_one}, {'title': 'Two', 'text': source_two}])
    foreign_book = store.import_txt(b'Foreign source.', 'Foreign', [{'title': 'Foreign chapter', 'text': 'Foreign source.'}])

    def create_real_job(book):
        response = client.post(f'/books/{book}/real-jobs', data={'csrf': token}, follow_redirects=False)
        assert response.status_code == 303
        return response.headers['location'].rsplit('/', 1)[-1]

    job_id = create_real_job(book_id)
    newer_job_id = create_real_job(book_id)
    foreign_job_id = create_real_job(foreign_book)
    return client, token, store, book_id, job_id, newer_job_id, foreign_job_id


def add_result(store, job_id, manifest, chunk, translated_text):
    stamp = now()
    result = make_result(manifest, chunk, {
        'translated_text': translated_text, 'output_tokens': 1,
        'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
    store.import_real_result(canonical_bytes(result))
    return result


def test_raw_reader_uses_only_selected_local_chapter(tmp_path, monkeypatch):
    client, _, store, book_id, job_id, _, _ = setup_library(tmp_path, monkeypatch)
    no_job_book = store.import_txt(b'Raw without any job.', 'No job book', [
        {'title': 'Only chapter', 'text': 'Raw without any job.'}])
    jobs_before = store.list_real_jobs(no_job_book)
    with store._connect() as db:
        real_job_count = db.execute('SELECT COUNT(*) FROM real_jobs').fetchone()[0]
    calls = []
    get_raw_chapter = store.get_raw_chapter

    def selected_raw(book, ordinal):
        calls.append((book, ordinal))
        return get_raw_chapter(book, ordinal)

    def forbidden(*args, **kwargs):
        pytest.fail('raw reader hydrated translation/job state')

    monkeypatch.setattr(store, 'get_raw_chapter', selected_raw)
    monkeypatch.setattr(store, 'get_book', forbidden)
    monkeypatch.setattr(store, 'get_real_job', forbidden)
    monkeypatch.setattr(store, 'get_real_manifest', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    from app import colab_control, real_bundles
    monkeypatch.setattr(real_bundles, 'load_tokenizer', forbidden)
    monkeypatch.setattr(colab_control, 'available_sessions', forbidden)
    monkeypatch.setattr(colab_control, 'status_job', forbidden)

    default = client.get(f'/books/{no_job_book}/read')
    selected = client.get(f'/books/{book_id}/read?chapter=1&job_id={job_id}')
    empty_job_form = client.get(f'/books/{no_job_book}/read?chapter=0&mode=raw&job_id=')
    assert default.status_code == selected.status_code == empty_job_form.status_code == 200
    assert 'Raw without any job.' in default.text
    assert 'Raw without any job.' in empty_job_form.text
    assert 'RAW TWO &amp; &lt;script&gt;bad&lt;/script&gt;.' in selected.text
    assert '&lt;script&gt;Book&lt;/script&gt;' in selected.text and '<script>Book</script>' not in selected.text
    assert 'RAW ONE' not in selected.text
    assert calls == [(no_job_book, 0), (book_id, 1), (no_job_book, 0)]
    assert jobs_before == store.list_real_jobs(no_job_book) == []
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM real_jobs').fetchone()[0] == real_job_count
    client.__exit__(None, None, None)


def test_translated_reader_uses_explicit_job_and_current_revision(tmp_path, monkeypatch):
    client, _, store, book_id, job_id, newer_job_id, foreign_job_id = setup_library(tmp_path, monkeypatch)
    manifest = store.get_real_manifest(job_id)
    chapter_one = [item for item in manifest['chunks'] if item['chapter_ordinal'] == 1]
    stale_chunk = manifest['chunks'][0]
    empty_revision_chunk, missing_result_chunk = chapter_one[:2]

    store.save_real_revision(job_id, stale_chunk['chunk_id'], 'Manual first', 0, None, False)
    add_result(store, job_id, manifest, stale_chunk, 'MACHINE FIRST')
    empty_result = add_result(store, job_id, manifest, empty_revision_chunk, 'MACHINE MUST NOT WIN')
    with store._connect() as db:
        db.execute('''INSERT INTO real_revisions
            (job_id,chunk_id,revision,edited_text,base_result_hash,approved,created_at)
            VALUES (?,?,?,?,?,?,?)''',
                   (job_id, empty_revision_chunk['chunk_id'], 1, '', empty_result['checksum'], 0, now()))
    store.save_real_revision(job_id, missing_result_chunk['chunk_id'], 'Manual without result', 0, None, False)
    approved_result = add_result(store, job_id, manifest, chapter_one[2], 'Approved machine result')
    store.save_real_revision(job_id, chapter_one[2]['chunk_id'], 'Approved before reader', 0,
                             approved_result['checksum'], True)
    p1_job_id = store.create_job(book_id)

    before = {}
    with store._connect() as db:
        for table in ('real_revisions', 'real_results'):
            before[table] = [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1,2,3')]
    base = f'/books/{book_id}/read'
    assert client.get(base + '?mode=translated').status_code == 400
    assert client.get(base + f'?mode=translated&job_id={p1_job_id}').status_code == 404
    assert client.get(base + f'?mode=translated&job_id={foreign_job_id}').status_code == 404
    assert client.get(base + f'?mode=translated&job_id=missing').status_code == 404

    calls = []
    get_real_job = store.get_real_job

    def selected_real_job(selected_job, ordinal=None):
        calls.append((selected_job, ordinal))
        return get_real_job(selected_job, ordinal)

    monkeypatch.setattr(store, 'get_real_job', selected_real_job)
    translated = client.get(base + f'?mode=translated&job_id={job_id}')
    assert translated.status_code == 200
    assert 'Manual first' in translated.text and 'Bản sửa đã cũ' in translated.text
    assert 'MACHINE FIRST' not in translated.text
    assert f'/books/{book_id}/real-jobs/{job_id}?chapter=0&amp;filter=all#chunk-{stale_chunk["chunk_id"]}' in translated.text
    assert newer_job_id in translated.text and job_id in translated.text
    assert 'Real job v2' in translated.text

    bilingual = client.get(base + f'?chapter=1&mode=bilingual&job_id={job_id}')
    assert bilingual.status_code == 200
    assert 'RAW TWO &amp; &lt;script&gt;bad&lt;/script&gt;.' in bilingual.text
    empty_article = re.search(rf'<article id="chunk-{empty_revision_chunk["chunk_id"]}">(.*?)</article>',
                              bilingual.text, re.S)[1]
    assert 'MACHINE MUST NOT WIN' not in empty_article and '<pre></pre>' in empty_article
    missing_article = re.search(rf'<article id="chunk-{missing_result_chunk["chunk_id"]}">(.*?)</article>',
                                bilingual.text, re.S)[1]
    assert 'Chưa có result hoàn tất' in missing_article
    assert 'Manual without result' in missing_article
    assert 'Bản dịch chưa được duyệt hiện hành' in bilingual.text
    assert calls[:2] == [(job_id, 0), (job_id, 1)]

    review = client.get(f'/books/{book_id}/real-jobs/{job_id}?chapter=1')
    assert f'/books/{book_id}/read?chapter=1&amp;mode=translated&amp;job_id={job_id}' in review.text
    book_page = client.get(f'/books/{book_id}?chapter=1')
    assert f'/books/{book_id}/read?chapter=1' in book_page.text
    with store._connect() as db:
        after = {table: [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1,2,3')]
                 for table in ('real_revisions', 'real_results')}
    assert after == before
    client.__exit__(None, None, None)


def test_reader_rejects_invalid_mode_chapter_and_job(tmp_path, monkeypatch):
    client, _, _, book_id, job_id, _, _ = setup_library(tmp_path, monkeypatch)
    base = f'/books/{book_id}/read'
    assert client.get(base + '?mode=combined').status_code == 400
    assert client.get(base + '?chapter=nope').status_code == 400
    assert client.get(base + '?chapter=9').status_code == 404
    assert client.get(f'/books/missing/read').status_code == 404
    assert client.get(base + f'?job_id={job_id}&mode=raw').status_code == 200
    assert client.get(base + '?job_id=').status_code == 200
    assert client.get(base + '?mode=translated&job_id=').status_code == 400
    client.__exit__(None, None, None)
