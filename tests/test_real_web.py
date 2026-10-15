import copy
import re
from html import unescape

from fastapi.testclient import TestClient

from app.bundles import digest, now
from app.main import create_app
from app.real_bundles import MODELS, QWEN35, default_snapshot, make_result, provenance


class TinyTokenizer:
    chat_template = 'tiny-chat-template-v1'

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        assert kwargs == {'enable_thinking': False}
        return [ord(char) for char in ''.join(message['content'] for message in messages)]


def fields(response):
    return {name: unescape(value) for name, value in re.findall(r'name="([^\"]+)" value="([^\"]*)"', response.text)}


def test_real_job_import_review_approval_and_scoped_exports(tmp_path, monkeypatch):
    from app import real_bundles

    monkeypatch.setattr(real_bundles, 'load_tokenizer', lambda model, revision: (TinyTokenizer(), revision))
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1') as client:
        token = fields(client.get('/'))['csrf']

        def add_book(title, source):
            preview = client.post('/preview', data={'csrf': token, 'title': title},
                                  files={'file': ('book.txt', source.encode())})
            data = fields(preview)
            data['text_0'] = source
            return client.post('/books', data=data)

        book, other = add_book('<script>Title</script>', 'Source <script>alert(1)</script>.'), add_book('Other', 'Other source.')
        book_url = book.url.path
        other_url = other.url.path
        book_page = client.get(book_url)
        assert '&lt;script&gt;Title&lt;/script&gt;' in book_page.text
        assert '<script>alert(1)</script>' not in book_page.text
        assert 'Tạo job Qwen3.5' in book_page.text
        assert client.post(book.url.path + '/real-jobs', data={}).status_code == 403

        created = client.post(book_url + '/real-jobs', data={'csrf': token}, follow_redirects=False)
        assert created.status_code == 303
        review_url = created.headers['location']
        job_id = review_url.rsplit('/', 1)[-1]
        assert client.get(other_url + f'/real-jobs/{job_id}').status_code == 404
        manifest_response = client.get(review_url + '/manifest')
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()
        assert manifest['snapshot']['model_id'] == QWEN35
        assert client.get('/translate-notebook').status_code == 200
        initial = client.get(review_url)
        assert 'Lưu bản sửa' in initial.text and 'Lưu và duyệt' in initial.text
        chunk = manifest['chunks'][0]
        chunk_url = review_url + '/chunks/' + chunk['chunk_id']
        assert client.post(review_url + '/chunks/not-this-jobs-chunk',
                           data={'csrf': token, 'revision': '0', 'base_result_hash': '',
                                 'text': 'Unrelated chunk edit.', 'approved': 'false'}).status_code == 404
        assert client.post(other_url + f'/real-jobs/{job_id}/chunks/{chunk["chunk_id"]}',
                           data={'csrf': token}).status_code == 404

        def save_form(page, text, approved):
            action = re.search(r'<form method="post" action="([^"]+/chunks/[^"]+)"', page.text)[1]
            data = fields(page)
            data.update(text=text, approved=approved, csrf=token)
            return client.post(action, data=data, follow_redirects=False)

        assert save_form(initial, 'Manual before result.', 'false').status_code == 303
        stamp = now()
        result = make_result(manifest, chunk,
                             {'translated_text': 'Machine result.', 'output_tokens': 3, 'finish_reason': 'eos',
                              'provenance': provenance(manifest)}, stamp, stamp)
        raw = real_bundles.canonical_bytes(result)
        upload_url = review_url + '/results'
        assert client.post(upload_url, data={'csrf': token}, files={'file': ('result.json', raw)}).status_code == 200
        assert client.post(upload_url, data={'csrf': token}, files={'file': ('result.json', raw)}).status_code == 200
        conflict = copy.deepcopy(result)
        conflict['translated_text'] = 'Conflicting output.'
        conflict['checksum'] = digest({key: value for key, value in conflict.items() if key != 'checksum'})
        assert client.post(upload_url, data={'csrf': token}, files={'file': ('result.json', real_bundles.canonical_bytes(conflict))}).status_code == 409
        invalid = copy.deepcopy(result)
        invalid['checksum'] = '0' * 64
        assert client.post(upload_url, data={'csrf': token}, files={'file': ('result.json', real_bundles.canonical_bytes(invalid))}).status_code == 400
        other_job = client.post(book_url + '/real-jobs', data={'csrf': token}, follow_redirects=False).headers['location']
        assert client.post(other_job + '/results', data={'csrf': token},
                           files={'file': ('result.json', raw)}).status_code == 400

        current = client.get(review_url)
        assert 'Manual before result.' in current.text
        assert save_form(current, 'Approved translation.', 'true').status_code == 303
        old_tab = fields(current)
        action = re.search(r'<form method="post" action="([^"]+/chunks/[^"]+)"', current.text)[1]
        old_tab.update(text='Lost concurrent edit.', approved='false', csrf=token)
        assert client.post(action, data=old_tab).status_code == 409
        approved = client.get(review_url)
        assert 'Approved translation.' in client.get(review_url + '/export').text
        assert save_form(approved, 'Edited again, needs review.', 'false').status_code == 303
        assert client.get(review_url + '/export').status_code == 400
        draft = client.get(review_url + '/export?draft=true')
        assert draft.status_code == 200 and 'UNREVIEWED CHUNK' in draft.text
        pending = client.get(review_url)
        assert save_form(pending, 'Final approved translation.', 'true').status_code == 303
        official = client.get(review_url + '/export')
        assert official.status_code == 200 and 'Final approved translation.' in official.text
