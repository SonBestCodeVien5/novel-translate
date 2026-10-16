import copy
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app import real_bundles
from app.bundles import canonical_bytes, digest, now
from app.core import DomainError, Store
from app.main import create_app


class TinyTokenizer:
    chat_template = 'tiny-chat-template-v1'

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        return [ord(char) for char in ''.join(message['content'] for message in messages)]


def entry(term='Dragon', translation='Long', aliases=None, notes=''):
    return {'term': term, 'translation': translation, 'aliases': aliases or [], 'notes': notes}


@pytest.mark.parametrize('value', [
    {'revision': True, 'entries': []}, {'revision': -1, 'entries': []},
    {'revision': 0, 'entries': [entry()]}, {'revision': 1, 'entries': 'bad'},
    {'revision': 1, 'entries': [dict(entry(), other='x')]},
    {'revision': 1, 'entries': [entry(term='') ]},
    {'revision': 1, 'entries': [entry(translation=3)]},
    {'revision': 1, 'entries': [entry(aliases=[''])]},
    {'revision': 1, 'entries': [entry(aliases=['x' * 201])]},
    {'revision': 1, 'entries': [entry(aliases=list('abcdefghijk'))]},
    {'revision': 1, 'entries': [entry(notes='x' * 1001)]},
    {'revision': 1, 'entries': [entry(term='a\x00')]},
    {'revision': 1, 'entries': [entry(term='a\ud800')]},
    {'revision': 1, 'entries': [entry(), entry(term='dragon')]},
    {'revision': 1, 'entries': [entry(aliases=['DRAGON'])]},
    {'revision': 1, 'entries': [entry() for _ in range(101)]},
])
def test_glossary_validation_rejects_bad_data(value):
    with pytest.raises(DomainError):
        real_bundles.validate_glossary(value)


def test_glossary_store_revision_conflict_restart_and_snapshot_isolation(tmp_path):
    store = Store(tmp_path)
    raw = b'Chapter 1\nA tiny source.'
    book = store.import_txt(raw, 'Book', store.preview_txt(raw, 'Book'))
    model = real_bundles.QWEN35
    snapshot = real_bundles.default_snapshot(model, real_bundles.MODELS[model], TinyTokenizer.chat_template)
    original = copy.deepcopy(snapshot)
    assert store.get_glossary(book) == {'revision': 0, 'entries': []}
    old_job = store.create_real_job(book, TinyTokenizer(), snapshot)
    old_bytes = (tmp_path / 'real-batches' / f'{old_job}.json').read_bytes()
    assert snapshot == original

    store.save_glossary(book, [entry()], 0)
    with pytest.raises(DomainError) as conflict:
        store.save_glossary(book, [entry('Other', 'Khác')], 0)
    assert conflict.value.status_code == 409
    store = Store(tmp_path)
    current = store.get_glossary(book)
    assert current == {'revision': 1, 'entries': [entry()]}
    new_job = store.create_real_job(book, TinyTokenizer(), snapshot)
    old_manifest, new_manifest = store.get_real_manifest(old_job), store.get_real_manifest(new_job)
    assert old_manifest['snapshot']['glossary'] == {'revision': 0, 'entries': []}
    assert new_manifest['snapshot']['glossary'] == current
    assert new_manifest['snapshot']['glossary_hash'] != old_manifest['snapshot']['glossary_hash']
    old_chunk, new_chunk = old_manifest['chunks'][0], new_manifest['chunks'][0]
    assert old_chunk['input_ids'] != new_chunk['input_ids']
    assert (tmp_path / 'real-batches' / f'{old_job}.json').read_bytes() == old_bytes


def test_glossary_change_preserves_old_result_and_manual_revision(tmp_path):
    store = Store(tmp_path)
    raw = b'Chapter 1\nA tiny source.'
    book = store.import_txt(raw, 'Book', store.preview_txt(raw, 'Book'))
    model = real_bundles.QWEN35
    snapshot = real_bundles.default_snapshot(model, real_bundles.MODELS[model], TinyTokenizer.chat_template)
    job = store.create_real_job(book, TinyTokenizer(), snapshot)
    manifest = store.get_real_manifest(job)
    chunk = manifest['chunks'][0]
    stamp = now()
    result = real_bundles.make_result(manifest, chunk, {
        'translated_text': 'Machine translation.', 'output_tokens': 2, 'finish_reason': 'eos',
        'provenance': real_bundles.provenance(manifest)}, stamp, stamp)
    store.import_real_result(canonical_bytes(result))
    store.save_real_revision(job, chunk['chunk_id'], 'Manual approved.', 0, result['checksum'], True)
    result_path = tmp_path / 'real-results' / job / (chunk['chunk_id'] + '.json')
    result_bytes = result_path.read_bytes()
    revision_before = store.get_real_job(job)['chunks'][0]['revision']
    store.save_glossary(book, [entry()], 0)
    assert store.get_real_job(job)['chunks'][0]['result']['translated_text'] == 'Machine translation.'
    assert store.get_real_job(job)['chunks'][0]['revision'] == revision_before
    assert store.export_real_txt(job).endswith('Manual approved.')
    assert result_path.read_bytes() == result_bytes


def test_glossary_over_budget_does_not_create_job_or_batch(tmp_path):
    store = Store(tmp_path)
    raw = b'Chapter 1\nA source.'
    book = store.import_txt(raw, 'Book', store.preview_txt(raw, 'Book'))
    terms = [entry(term=f'Term {i} ' + 'x' * 190, translation='y' * 200) for i in range(100)]
    store.save_glossary(book, terms, 0)
    model = real_bundles.QWEN35
    snapshot = real_bundles.default_snapshot(model, real_bundles.MODELS[model], TinyTokenizer.chat_template)
    with pytest.raises(DomainError):
        store.create_real_job(book, TinyTokenizer(), snapshot)
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM real_jobs').fetchone()[0] == 0
    assert list((tmp_path / 'real-batches').iterdir()) == []


def test_glossary_prompt_empty_compatibility_and_nonempty_content():
    model = real_bundles.QWEN35
    snap = real_bundles.default_snapshot(model, real_bundles.MODELS[model], TinyTokenizer.chat_template)
    source = 'A source.'
    assert real_bundles._messages(source, snap)[1]['content'] == snap['prompt']['user_prefix'] + snap['prompt']['glossary_prefix'] + source
    snap['glossary'] = {'revision': 1, 'entries': [entry()]}
    snap['glossary_hash'] = digest(snap['glossary'])
    assert canonical_bytes(snap['glossary']['entries']).decode() in real_bundles._messages(source, snap)[1]['content']


def test_glossary_ui_csrf_edit_remove_and_escaped_values(tmp_path, monkeypatch):
    monkeypatch.setattr(real_bundles, 'load_tokenizer', lambda model, revision: (TinyTokenizer(), revision))
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        token = unescape(re.search(r'name="csrf" value="([^"]+)"', client.get('/').text)[1])
        preview = client.post('/preview', data={'csrf': token, 'title': 'Book'},
                              files={'file': ('book.txt', b'Source.')})
        values = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', preview.text))
        values.update(csrf=token, text_0='Source.')
        book = client.post('/books', data=values, follow_redirects=False).headers['location']
        old_job = client.post(book + '/real-jobs', data={'csrf': token}, follow_redirects=False).headers['location']
        page = client.get(book + '/glossary')
        assert 'Thêm thuật ngữ' in page.text
        assert client.post(book + '/glossary', data={'term': 'x'}).status_code == 403
        response = client.post(book + '/glossary', data={'csrf': token, 'revision': '0',
            'term': '<script>x</script>', 'translation': 'y', 'aliases': 'z\nzz', 'notes': 'note'},
            follow_redirects=False)
        assert response.status_code == 303
        page = client.get(book + '/glossary')
        assert '<script>x</script>' not in page.text and '&lt;script&gt;x&lt;/script&gt;' in page.text
        assert 'value="1"' in page.text
        review = client.get(old_job)
        assert 'Glossary sách đã đổi' in review.text and 'tạo job mới' in review.text
        assert client.post(book + '/glossary/0', data={'csrf': token, 'revision': '0', 'action': 'remove'}).status_code == 409
        assert client.post(book + '/glossary/99', data={'csrf': token, 'revision': '0', 'action': 'remove'}).status_code == 409
        assert client.post(book + '/glossary/0', data={'csrf': token, 'revision': '1', 'action': 'remove'},
                           follow_redirects=False).status_code == 303
        assert 'Chưa có thuật ngữ.' in client.get(book + '/glossary').text
