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
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
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
    monkeypatch.setattr(real_runner, 'run_manifest', lambda *args: called.append(args))
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
    if hasattr(huggingface_generate, '_cache'):
        del huggingface_generate._cache
    return state


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
