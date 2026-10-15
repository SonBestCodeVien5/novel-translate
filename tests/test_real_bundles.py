import copy
import sys
import tempfile
import types
import uuid
from pathlib import Path

import pytest

from app import bundles
from app import real_bundles as real


class TinyTokenizer:
    chat_template = 'mock-template'

    def encode(self, text, add_special_tokens=False):
        return list(text)

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize and add_generation_prompt
        return list(range(1, sum(len(m['content']) for m in messages) + 1))


class MappingTokenizer(TinyTokenizer):
    def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
        assert kwargs == {'enable_thinking': False}
        return {'input_ids': super().apply_chat_template(messages, tokenize, add_generation_prompt)}


def batch(text='Héllo. ' + 'A long sentence; ' * 220 + '終わり！'):
    tok = TinyTokenizer()
    book_id, chapter_id = str(uuid.uuid4()), str(uuid.uuid4())
    book = {'id': book_id, 'source_language': 'en', 'target_language': 'vi', 'source_hash': bundles.text_hash(text)}
    chapters = [{'id': chapter_id, 'ordinal': 0, 'source_text': text}]
    snap = real.default_snapshot('Qwen/Qwen2.5-7B-Instruct', real.MODELS['Qwen/Qwen2.5-7B-Instruct'], tok.chat_template)
    return real.build_manifest(book, chapters, tok, snap)


def test_planner_reconstructs_unicode_and_freezes_measured_token_ids():
    manifest = batch()
    chunks = manifest['chunks']
    assert ''.join(c['source_text'] for c in chunks) == 'Héllo. ' + 'A long sentence; ' * 220 + '終わり！'
    assert [c['ordinal'] for c in chunks] == list(range(len(chunks)))
    assert all(c['input_tokens'] == len(c['input_ids']) <= 2048 for c in chunks)
    assert all(c['input_tokens'] + 2048 <= 4096 for c in chunks)


def test_planner_keeps_a_fitting_paragraph_whole_before_splitting_next_paragraph():
    first = 'A' * 500
    second = 'B' * 190 + '. ' + 'C' * 190 + '. ' + 'D' * 190 + '.'
    source = first + '\r\n \r\n' + second
    manifest = batch(source)
    assert manifest['chunks'][0]['source_text'] == first + '\r\n \r\n'
    assert ''.join(c['source_text'] for c in manifest['chunks']) == source


def test_planner_rejects_prompt_that_leaves_no_source_budget():
    class FullPrompt(TinyTokenizer):
        def apply_chat_template(self, *args, **kwargs): return [1] * 2049
    tok = FullPrompt()
    text = 'x'
    book = {'id': str(uuid.uuid4()), 'source_language': 'en', 'target_language': 'vi',
            'source_hash': bundles.text_hash(text)}
    chapters = [{'id': str(uuid.uuid4()), 'ordinal': 0, 'source_text': text}]
    snap = real.default_snapshot('Qwen/Qwen3-4B-Instruct-2507', real.MODELS['Qwen/Qwen3-4B-Instruct-2507'], tok.chat_template)
    with pytest.raises(real.DomainError):
        real.build_manifest(book, chapters, tok, snap)


@pytest.mark.parametrize('mutate', [
    lambda m: m.update(schema_version=True),
    lambda m: m['chunks'][0].update(input_tokens=True),
    lambda m: m['chunks'][0].update(source_hash='0' * 64),
    lambda m: m['snapshot']['quantization'].update(bnb_4bit_compute_dtype='float16'),
    lambda m: (m['snapshot']['glossary'].update(revision=False), m['snapshot'].update(glossary_hash=real.digest(m['snapshot']['glossary']))),
    lambda m: (m['snapshot']['parameters'].update(seed=True)),
    lambda m: (m['snapshot']['chunker'].update(source_tokens=768.0), m['snapshot'].update(chunker_hash=real.digest(m['snapshot']['chunker']))),
])
def test_manifest_rejects_malformed_schema_hashes_and_snapshot(mutate):
    manifest = batch()
    mutate(manifest)
    with pytest.raises(real.DomainError):
        real.validate_manifest(manifest)


def test_result_requires_exact_provenance_counts_and_checksum():
    manifest = batch('One sentence.')
    chunk = manifest['chunks'][0]
    stamp = bundles.now()
    generated = {'translated_text': 'Xin chào.', 'output_tokens': 3, 'finish_reason': 'eos',
                 'provenance': real.provenance(manifest)}
    result = real.make_result(manifest, chunk, generated, stamp, stamp)
    assert real.validate_result(result, manifest) is result
    for mutate in (lambda r: r['provenance'].update(model_revision='wrong'),
                   lambda r: r.update(input_tokens=True),
                   lambda r: r.update(output_tokens=0),
                   lambda r: r.update(finish_reason='max_tokens'),
                   lambda r: r.update(translated_text='')):
        corrupt = copy.deepcopy(result)
        mutate(corrupt)
        corrupt['checksum'] = real.digest({k: v for k, v in corrupt.items() if k != 'checksum'})
        with pytest.raises(real.DomainError):
            real.validate_result(corrupt, manifest)


def test_non_eos_generation_is_never_completed():
    manifest = batch('A sentence.')
    c = manifest['chunks'][0]
    stamp = bundles.now()
    with pytest.raises(real.DomainError):
        real.make_result(manifest, c, {'translated_text': 'partial', 'output_tokens': 4,
            'finish_reason': 'max_tokens', 'provenance': real.provenance(manifest)}, stamp, stamp)


def test_tokenizer_snapshot_uses_resolved_commit_without_init_kwargs(monkeypatch):
    revision = real.MODELS['Qwen/Qwen3-4B-Instruct-2507']
    calls = []
    tokenizer = types.SimpleNamespace(chat_template='template')
    hub = types.ModuleType('huggingface_hub')
    hub.snapshot_download = lambda *a, **kw: f'/cache/{revision}'
    transformers = types.ModuleType('transformers')
    transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda path, **kw: calls.append((path, kw)) or tokenizer)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', hub)
    monkeypatch.setitem(sys.modules, 'transformers', transformers)
    loaded, resolved = real.load_tokenizer('Qwen/Qwen3-4B-Instruct-2507', revision)
    assert loaded is tokenizer and resolved == revision and len(calls) == 1


def test_wrong_resolved_tokenizer_commit_fails_before_loading(monkeypatch):
    calls = []
    hub = types.ModuleType('huggingface_hub')
    hub.snapshot_download = lambda *a, **kw: '/cache/wrong-commit'
    transformers = types.ModuleType('transformers')
    transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **kw: calls.append(True))
    monkeypatch.setitem(sys.modules, 'huggingface_hub', hub)
    monkeypatch.setitem(sys.modules, 'transformers', transformers)
    with pytest.raises(real.DomainError):
        real.load_tokenizer('Qwen/Qwen3-4B-Instruct-2507', real.MODELS['Qwen/Qwen3-4B-Instruct-2507'])
    assert calls == []


def test_qwen35_profile_kwargs_and_mapping_ids(tmp_path, monkeypatch):
    import sys
    snap = real.default_snapshot(real.QWEN35, real.MODELS[real.QWEN35], 'mock-template')
    assert snap['parameters']['attention_implementation'] == 'sdpa'
    assert snap['chat_template_kwargs'] == {'enable_thinking': False}
    book = {'id': str(uuid.uuid4()), 'source_language': 'en', 'target_language': 'vi',
            'source_hash': bundles.text_hash('One sentence.')}
    manifest = real.build_manifest(book, [{'id': str(uuid.uuid4()), 'ordinal': 0,
        'source_text': 'One sentence.'}], MappingTokenizer(), snap)
    assert manifest['chunks'][0]['input_ids'] == real._token_ids(MappingTokenizer(), 'One sentence.', snap)
    corrupt = copy.deepcopy(manifest)
    corrupt['snapshot']['chat_template_kwargs']['enable_thinking'] = True
    corrupt['snapshot']['template_hash'] = real.text_hash(corrupt['snapshot']['template'])
    with pytest.raises(real.DomainError):
        real.validate_manifest(corrupt)
