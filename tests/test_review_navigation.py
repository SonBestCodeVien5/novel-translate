import re
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
        job_url = client.post(f'/books/{book}/real-jobs', data={'csrf': token}, follow_redirects=False).headers['location']
        manifest = client.get(job_url + '/manifest').json()
        assert len(manifest['chunks']) == 2
        default = client.get(job_url)
        assert 'Chương 1 · chunk 1' in default.text and 'Chương 2 · chunk 1' not in default.text
        assert '0/2 checkpoint' in default.text
        first = manifest['chunks'][0]
        stamp = now()
        result = make_result(manifest, first, {'translated_text': 'First', 'output_tokens': 1,
            'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
        client.post(job_url + '/results', data={'csrf': token}, files={'file': ('r.json', real_bundles.canonical_bytes(result))})
        assert 'chunk 1' in client.get(job_url + '?chapter=0&filter=unreviewed').text
        assert 'chunk 1' not in client.get(job_url + '?chapter=0&filter=pending').text
        assert 'chunk 1' not in client.get(job_url + '?chapter=0&filter=approved').text
        page = client.get(job_url + '?chapter=1&filter=pending')
        assert 'Chương 2 · chunk 1' in page.text and 'Chương 1 · chunk 1' not in page.text
        action = re.search(r'<form method="post" action="([^"]+/chunks/[^"]+)', page.text)[1]
        data = fields(page) | {'csrf': token, 'text': 'Second edit', 'approved': 'false'}
        saved = client.post(action, data=data, follow_redirects=False)
        assert saved.headers['location'].endswith('?chapter=1&filter=pending#chunk-' + manifest['chunks'][1]['chunk_id'])
        assert client.get(job_url + '?chapter=invalid').status_code == 400
