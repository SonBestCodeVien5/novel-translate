import copy
import contextlib
import sys
import types
import uuid
from pathlib import Path

import pytest

from app import bundles
from app import real_bundles as real
from app.real_runner import huggingface_generate, main, run_manifest


class Tokenizer:
    chat_template = 'template'
    def encode(self, text, add_special_tokens=False): return list(text)
    def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
        return list(range(1, sum(len(m['content']) for m in messages) + 1))


def manifest(model_id='Qwen/Qwen3-4B-Instruct-2507'):
    text = 'abc ' * 900
    book = {'id': str(uuid.uuid4()), 'source_language': 'en', 'target_language': 'vi',
            'source_hash': bundles.text_hash(text)}
    chapters = [{'id': str(uuid.uuid4()), 'ordinal': 0, 'source_text': text}]
    snap = real.default_snapshot(model_id, real.MODELS[model_id], 'template')
    return real.build_manifest(book, chapters, Tokenizer(), snap)


def generated(m):
    return {'translated_text': 'Bản dịch.', 'output_tokens': 5, 'finish_reason': 'eos',
            'provenance': real.provenance(m)}


def test_interrupt_then_resume_only_generates_missing_chunks(tmp_path):
    m = manifest()
    calls = []
    def interrupted(batch, chunk):
        calls.append(chunk['chunk_id'])
        if len(calls) == 2:
            raise RuntimeError('simulated interruption')
        return generated(batch)
    with pytest.raises(RuntimeError):
        run_manifest(m, tmp_path, interrupted)
    assert len(list(tmp_path.glob('*.json'))) == 2  # manifest plus one completed checkpoint
    calls.clear()
    assert run_manifest(m, tmp_path, lambda b, c: calls.append(c['chunk_id']) or generated(b)) == {'completed': len(m['chunks']), 'total': len(m['chunks'])}
    assert len(calls) == len(m['chunks']) - 1
    assert run_manifest(m, tmp_path, lambda *_: pytest.fail('completed batch called generator'))['completed'] == len(m['chunks'])


def test_limit_stops_after_new_checkpoint_and_resume_keeps_existing_bytes(tmp_path):
    m = manifest()
    calls = []
    first = run_manifest(m, tmp_path, lambda b, c: calls.append(c['chunk_id']) or generated(b), limit=1)
    assert first == {'completed': 1, 'total': len(m['chunks'])}
    assert len(calls) == 1
    chunk_path = tmp_path / (calls[0] + '.json')
    saved = chunk_path.read_bytes()
    next_calls = []
    second = run_manifest(m, tmp_path, lambda b, c: next_calls.append(c['chunk_id']) or generated(b), limit=1)
    assert second == {'completed': 2, 'total': len(m['chunks'])}
    assert len(next_calls) == 1 and next_calls[0] != calls[0]
    assert chunk_path.read_bytes() == saved
    for invalid in (0, -1, True):
        with pytest.raises(real.DomainError):
            run_manifest(m, tmp_path, lambda *_: pytest.fail('invalid limit ran'), limit=invalid)


@pytest.mark.parametrize('bad_file', ['partial', 'corrupt', 'mismatch'])
def test_bad_checkpoint_stops_before_generation(tmp_path, bad_file):
    m = manifest()
    run_manifest(m, tmp_path, lambda b, c: generated(b))
    checkpoint = tmp_path / (m['chunks'][0]['chunk_id'] + '.json')
    if bad_file == 'partial':
        checkpoint.write_text('{"schema_version":2', encoding='utf-8')
    elif bad_file == 'corrupt':
        value = bundles.load_json(checkpoint.read_bytes()); value['translated_text'] = 'tampered'
        checkpoint.write_bytes(real.canonical_bytes(value))
    else:
        other = manifest()
        value = bundles.load_json(checkpoint.read_bytes()); value['manifest_hash'] = real.digest(other)
        value['checksum'] = real.digest({k: v for k, v in value.items() if k != 'checksum'})
        checkpoint.write_bytes(real.canonical_bytes(value))
    called = []
    with pytest.raises(real.DomainError):
        run_manifest(m, tmp_path, lambda *_: called.append(True))
    assert called == []


def test_manifest_directory_mismatch_stops_before_generation(tmp_path):
    first, second = manifest(), manifest()
    run_manifest(first, tmp_path, lambda b, c: generated(b))
    called = []
    with pytest.raises(real.DomainError):
        run_manifest(second, tmp_path, lambda *_: called.append(True))
    assert called == []


def test_checkpoint_filename_must_match_result_chunk_before_generation(tmp_path):
    m = manifest()
    run_manifest(m, tmp_path, lambda b, c: generated(b))
    chunks = m['chunks']
    assert len(chunks) > 1
    first, second = chunks[:2]
    second_path = tmp_path / (second['chunk_id'] + '.json')
    value = bundles.load_json((tmp_path / (first['chunk_id'] + '.json')).read_bytes())
    second_path.write_bytes(real.canonical_bytes(value))
    called = []
    with pytest.raises(real.DomainError):
        run_manifest(m, tmp_path, lambda *_: called.append(True))
    assert called == []


def test_failure_diagnostics_keep_attempts_and_identity(tmp_path):
    m = manifest('Qwen/Qwen3-4B-Instruct-2507')
    chunk = m['chunks'][0]
    partial = {'translated_text': 'partial output', 'output_tokens': 9,
               'finish_reason': 'max_tokens', 'provenance': {}}
    for _ in range(2):
        with pytest.raises(real.DomainError):
            run_manifest(m, tmp_path, lambda *_: partial)
    failures = list((tmp_path / 'failed').glob('*.json'))
    assert len(failures) == 2
    for path in failures:
        diagnostic = bundles.load_json(path.read_bytes())
        assert diagnostic['job_id'] == m['job_id']
        assert diagnostic['manifest_hash'] == real.digest(m)
        assert diagnostic['expected_input_hash'] == chunk['expected_input_hash']
        assert diagnostic['finish_reason'] == 'max_tokens'


def test_cli_requires_output_under_mounted_drive(tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_bytes(real.canonical_bytes(manifest()))
    def exists(self): return str(self) == '/content'
    def is_dir(self): return False
    def resolve(self, *args, **kwargs): return self
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr('pathlib.Path.exists', exists)
        mp.setattr('pathlib.Path.is_dir', is_dir)
        mp.setattr('pathlib.Path.resolve', resolve)
        with pytest.raises(SystemExit):
            main([str(path), '/content/drive/MyDrive/out'])


def test_cli_allows_local_cuda_environment_outside_colab(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    path.write_bytes(real.canonical_bytes(manifest()))
    from app import real_runner
    called = []
    monkeypatch.setattr(Path, 'exists', lambda self: False)
    monkeypatch.setattr(real_runner, 'run_manifest', lambda *args, **kwargs: called.append((args, kwargs)))
    main([str(path), str(tmp_path / 'output')])
    assert len(called) == 1


class _Tensor:
    def __init__(self, values): self.values, self.shape = values, (1, len(values[0]))


class _Output:
    def __init__(self, values): self.values = values
    def __getitem__(self, key): return self.values[0][key[1]]


@contextlib.contextmanager
def _inference_mode(state):
    state['inference'] = True
    try: yield
    finally: state['inference'] = False


def _hf_mocks(monkeypatch, m, ids=None, tokenizer_commit=None, model_commit=None,
              available=True, eos_ids=(7, 99)):
    state = {'model_loads': 0, 'inference': False, 'device_map': None, 'quant': None, 'dtype': None}
    tokenizer = types.SimpleNamespace(chat_template='template', pad_token_id=0,
        apply_chat_template=lambda *a, **kw: list(ids if ids is not None else m['chunks'][0]['input_ids']),
        decode=lambda values, skip_special_tokens: 'mock translation', init_kwargs={})
    model = types.SimpleNamespace(config=types.SimpleNamespace(_commit_hash=model_commit or m['snapshot']['model_revision'],
                                      max_position_embeddings=4096),
        generation_config=types.SimpleNamespace(eos_token_id=99), eval=lambda: None)
    def from_model(*args, **kwargs):
        state['model_loads'] += 1
        state['device_map'] = kwargs['device_map']; state['quant'] = kwargs['quantization_config']; state['dtype'] = kwargs['torch_dtype']
        assert kwargs['trust_remote_code'] is False
        assert kwargs['revision'] == m['snapshot']['model_revision']
        def generate(**gen):
            assert state['inference'] is True
            assert gen['attention_mask'] is not None
            assert gen['do_sample'] is False and gen['max_new_tokens'] == 2048
            assert kwargs['device_map'] == {'': 0}
            return _Output([[0] * state['input_len'] + ([1, 99] if eos_ids == (7, 99) else list(eos_ids))])
        model.generate = generate
        return model
    transformers = types.ModuleType('transformers')
    transformers.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=from_model)
    transformers.BitsAndBytesConfig = lambda **kw: kw
    monkeypatch.setitem(sys.modules, 'transformers', transformers)
    hub = types.ModuleType('huggingface_hub')
    revision = tokenizer_commit or m['snapshot']['tokenizer_revision']
    hub.snapshot_download = lambda *a, **kw: '/cache/' + revision
    monkeypatch.setitem(sys.modules, 'huggingface_hub', hub)
    # load_tokenizer imports AutoTokenizer from this module.
    transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer)
    torch = types.ModuleType('torch')
    torch.cuda = types.SimpleNamespace(is_available=lambda: available)
    torch.float16, torch.float32, torch.long = 'fp16', 'fp32', 'long'
    def tensor(values, **kw):
        state['input_len'] = len(values[0])
        return _Tensor(values)
    torch.tensor = tensor
    torch.ones_like = lambda tensor: tensor
    torch.manual_seed = lambda seed: None
    torch.inference_mode = lambda: _inference_mode(state)
    monkeypatch.setitem(sys.modules, 'torch', torch)
    for name in ('_cache',):
        if hasattr(huggingface_generate, name):
            delattr(huggingface_generate, name)
    return state


def test_qwen35_loading_uses_pinned_text_loader_and_mapping_ids(monkeypatch, tmp_path):
    config_file = tmp_path / 'config.json'; config_file.write_text('{"model_type":"qwen3_5"}')
    m = manifest(real.QWEN35)
    state = {'loads': 0, 'kwargs': None}
    tokenizer = types.SimpleNamespace(chat_template='template', pad_token_id=0,
        apply_chat_template=lambda *a, **kw: {'input_ids': m['chunks'][0]['input_ids']},
        decode=lambda values, skip_special_tokens: 'mock translation', init_kwargs={})
    model = types.SimpleNamespace(config=types.SimpleNamespace(_commit_hash=None,
        text_config=types.SimpleNamespace(max_position_embeddings=4096)),
        generation_config=types.SimpleNamespace(eos_token_id=99), eval=lambda: None)
    def from_model(*args, **kwargs):
        state['loads'] += 1; state['kwargs'] = kwargs
        return model, {'missing_keys': [], 'mismatched_keys': [], 'error_msgs': []}
    tr = types.ModuleType('transformers')
    tr.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **kw: pytest.fail('wrong loader'))
    tr.Qwen3_5ForCausalLM = types.SimpleNamespace(from_pretrained=from_model)
    tr.BitsAndBytesConfig = lambda **kw: kw
    tr.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer)
    utils = types.ModuleType('transformers.utils'); hubutils = types.ModuleType('transformers.utils.hub')
    hubutils.cached_file = lambda *a, **kw: str(config_file)
    hubutils.extract_commit_hash = lambda *a, **kw: m['snapshot']['model_revision']
    utils.hub = hubutils
    monkeypatch.setitem(sys.modules, 'transformers', tr)
    monkeypatch.setitem(sys.modules, 'transformers.utils', utils)
    monkeypatch.setitem(sys.modules, 'transformers.utils.hub', hubutils)
    monkeypatch.setattr(real, 'load_tokenizer', lambda *a: (tokenizer, m['snapshot']['tokenizer_revision']))
    torch = types.ModuleType('torch'); torch.cuda = types.SimpleNamespace(is_available=lambda: True)
    torch.float16, torch.float32, torch.long = 'fp16', 'fp32', 'long'
    torch.tensor = lambda values, **kw: _Tensor(values); torch.ones_like = lambda value: value
    torch.manual_seed = lambda seed: None; torch.inference_mode = lambda: _inference_mode({'inference': False})
    monkeypatch.setitem(sys.modules, 'torch', torch)
    model.generate = lambda **kwargs: _Output([[0] * len(m['chunks'][0]['input_ids']) + [99]])
    if hasattr(huggingface_generate, '_cache'): del huggingface_generate._cache
    out = huggingface_generate(m, m['chunks'][0])
    assert out['finish_reason'] == 'eos' and state['loads'] == 1
    assert state['kwargs']['attn_implementation'] == 'sdpa'
    assert state['kwargs']['key_mapping'] == {r'^model\.language_model\.': 'model.'}
    assert state['kwargs']['output_loading_info'] is True
    del huggingface_generate._cache
    hubutils.extract_commit_hash = lambda *a, **kw: 'wrong-revision'
    with pytest.raises(real.DomainError):
        huggingface_generate(m, m['chunks'][0])
    assert state['loads'] == 1 and not hasattr(huggingface_generate, '_cache')

    hubutils.extract_commit_hash = lambda *a, **kw: m['snapshot']['model_revision']
    model.config.text_config.max_position_embeddings = 2048
    with pytest.raises(real.DomainError, match='context'):
        huggingface_generate(m, m['chunks'][0])
    assert state['loads'] == 2 and not hasattr(huggingface_generate, '_cache')

    model.config.text_config.max_position_embeddings = 4096
    def incomplete(*args, **kwargs):
        state['loads'] += 1
        return model, {'missing_keys': ['model.weight'], 'mismatched_keys': [], 'error_msgs': []}
    tr.Qwen3_5ForCausalLM.from_pretrained = incomplete
    with pytest.raises(real.DomainError, match='did not load completely'):
        huggingface_generate(m, m['chunks'][0])
    assert state['loads'] == 3 and not hasattr(huggingface_generate, '_cache')


def test_reuses_weights_when_only_glossary_snapshot_changes(monkeypatch):
    import copy
    m = manifest('Qwen/Qwen3-4B-Instruct-2507')
    state = _hf_mocks(monkeypatch, m, eos_ids=(99,))
    assert huggingface_generate(m, m['chunks'][0])['finish_reason'] == 'eos'
    changed = copy.deepcopy(m)
    snap = changed['snapshot']
    snap['glossary'] = {'revision': 1, 'entries': [
        {'term': 'moon', 'translation': 'trăng', 'aliases': [], 'notes': ''}]}
    snap['glossary_hash'] = real.digest(snap['glossary'])
    for chunk in changed['chunks']:
        chunk['expected_input_hash'] = real._input_hash(chunk, snap)
    real.validate_manifest(changed)
    assert huggingface_generate(changed, changed['chunks'][0])['finish_reason'] == 'eos'
    assert state['model_loads'] == 1


def test_unsupported_model_revision_still_fails_manifest_validation():
    import copy
    m = manifest(real.QWEN35)
    m = copy.deepcopy(m)
    m['snapshot']['model_revision'] = 'not-a-pinned-revision'
    with pytest.raises(real.DomainError, match='Unsupported or unpinned'):
        real.validate_manifest(m)


def test_huggingface_adapter_uses_pinned_fp32_cuda_and_inference_mode(monkeypatch):
    m = manifest('Qwen/Qwen2.5-7B-Instruct')
    state = _hf_mocks(monkeypatch, m)
    output = huggingface_generate(m, m['chunks'][0])
    assert output['finish_reason'] == 'eos' and output['output_tokens'] == 2
    assert state['model_loads'] == 1 and state['device_map'] == {'': 0}
    assert state['dtype'] == 'fp32' and state['quant']['bnb_4bit_compute_dtype'] == 'fp32'
    assert state['inference'] is False


def test_huggingface_adapter_checks_tokenizer_ids_before_model_load(monkeypatch):
    m = manifest()
    state = _hf_mocks(monkeypatch, m, ids=[999])
    with pytest.raises(real.DomainError):
        huggingface_generate(m, m['chunks'][0])
    assert state['model_loads'] == 0


def test_huggingface_adapter_rejects_wrong_tokenizer_or_model_commit(monkeypatch):
    m = manifest()
    state = _hf_mocks(monkeypatch, m, tokenizer_commit='bad')
    with pytest.raises(real.DomainError):
        huggingface_generate(m, m['chunks'][0])
    assert state['model_loads'] == 0
    state = _hf_mocks(monkeypatch, m, model_commit='bad')
    with pytest.raises(real.DomainError):
        huggingface_generate(m, m['chunks'][0])
    assert state['model_loads'] == 1


def test_huggingface_adapter_refuses_cpu_and_marks_non_eos_as_truncated(monkeypatch):
    m = manifest()
    state = _hf_mocks(monkeypatch, m, available=False)
    with pytest.raises(real.DomainError):
        huggingface_generate(m, m['chunks'][0])
    assert state['model_loads'] == 0
    state = _hf_mocks(monkeypatch, m, eos_ids=(7, 8))
    output = huggingface_generate(m, m['chunks'][0])
    assert output['finish_reason'] == 'max_tokens'
    assert state['model_loads'] == 1 and state['inference'] is False
