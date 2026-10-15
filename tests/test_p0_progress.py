import io
import json
import copy
from contextlib import redirect_stdout
from pathlib import Path
import sys
import types
from unittest.mock import patch

import pytest
from benchmarks.p0 import runner
from tests.test_p0 import Tokenizer, corpus


def progress_cell():
    notebook = json.loads(Path('notebooks/p0_qwen25_benchmark.ipynb').read_text())
    return ''.join(notebook['cells'][7]['source'])


def fake_torch():
    torch = types.ModuleType('torch')

    class OutOfMemoryError(RuntimeError):
        pass

    torch.cuda = types.SimpleNamespace(mem_get_info=lambda: (8 * 1024**3, 16 * 1024**3),
                                       OutOfMemoryError=OutOfMemoryError)
    return torch


def execute_progress(namespace, torch=None):
    with patch.dict(sys.modules, {'torch': torch or fake_torch()}):
        exec(compile(progress_cell(), '<progress>', 'exec'), namespace)


def test_qwen25_config_cell_changes_snapshot_and_runner_config(tmp_path):
    notebook = json.loads(Path('notebooks/p0_qwen25_benchmark.ipynb').read_text())
    source = ''.join(notebook['cells'][6]['source'])
    corpus_path = tmp_path / 'corpus.json'
    corpus_path.write_text(json.dumps(corpus()), encoding='utf-8')
    source = source.replace("Path('/content/drive/MyDrive/p0/corpus.json')", f'Path({str(corpus_path)!r})')
    original = copy.deepcopy(runner.CONFIG)
    baseline = runner.digest({'corpus': corpus(), 'model': runner.MODELS[1],
                              'revision': 'a09a35458c702b33eeacc393d103063234e8bc28', 'config': original})
    baseline_plan = copy.deepcopy(runner.build_plan(corpus(), Tokenizer(), runner.MODELS[1],
                                                   'a09a35458c702b33eeacc393d103063234e8bc28'))
    try:
        namespace = {'REPO': Path.cwd()}
        exec(compile(source, '<qwen25-config-cell>', 'exec'), namespace)
        assert runner.CONFIG['quantization']['bnb_4bit_compute_dtype'] == 'float32'
        assert namespace['CONFIG'] is runner.CONFIG
        assert namespace['snapshot'] != baseline
        assert namespace['OUTPUT'].name == 'Qwen2.5-7B-Instruct-' + namespace['snapshot']
        plan = runner.build_plan(corpus(), Tokenizer(), runner.MODELS[1],
                                 'a09a35458c702b33eeacc393d103063234e8bc28')
        assert plan['config']['quantization']['bnb_4bit_compute_dtype'] == 'float32'
        assert runner.digest(plan) != runner.digest(baseline_plan)
    finally:
        runner.CONFIG.clear()
        runner.CONFIG.update(original)


def test_progress_saved_after_write_and_resume(tmp_path):
    plan = runner.build_plan(corpus(), Tokenizer(), runner.MODELS[1], 'a' * 40)
    output = tmp_path / 'run'
    generated, written, logs = [], [], io.StringIO()
    original_run, original_write = runner.run, runner.write_new

    def generate(chunk):
        generated.append(chunk['id'])
        assert 'Đã lưu chunk ' + chunk['id'] not in logs.getvalue()
        return {'translated_text': 'PRIVATE OUTPUT', 'raw_output_ids': [2], 'finish_reason': 'eos'}

    def write(path, value):
        original_write(path, value)
        if Path(path).parent == output / 'results':
            assert Path(path).exists()
            assert 'Đã lưu chunk ' + value['chunk_id'] not in logs.getvalue()
            written.append(value['chunk_id'])

    def main():
        result = runner.run(plan, output, generate, limit=1)
        assert result['technical_complete'] == len(written)

    namespace = {'sys': __import__('sys'), 'Path': Path, 'REPO': tmp_path,
                 'MODEL': runner.MODELS[1], 'REVISION': 'a' * 40,
                 'CORPUS': tmp_path / 'corpus.json', 'OUTPUT': output, 'LIMIT': 1}
    with patch.object(runner, 'main', main), patch.object(runner, 'write_new', write):
        with redirect_stdout(logs):
            execute_progress(namespace)
            first = (output / 'results' / (plan['chunks'][0]['id'] + '.json')).read_bytes()
            execute_progress(namespace)
        assert runner.run is original_run
        assert runner.write_new is write
    assert runner.write_new is original_write
    assert generated == written == [chunk['id'] for chunk in plan['chunks'][:2]]
    assert (output / 'results' / (plan['chunks'][0]['id'] + '.json')).read_bytes() == first
    assert 'resume: 1/' in logs.getvalue()
    assert '2/' in logs.getvalue()
    assert 'PRIVATE OUTPUT' not in logs.getvalue()
    assert plan['chunks'][0]['source_text'] not in logs.getvalue()


def test_progress_restores_globals_on_error(tmp_path):
    original_run, original_write, original_argv = runner.run, runner.write_new, sys.argv
    namespace = {'sys': sys, 'Path': Path, 'REPO': tmp_path, 'MODEL': runner.MODELS[1],
                 'REVISION': 'a' * 40, 'CORPUS': tmp_path / 'corpus.json',
                 'OUTPUT': tmp_path / 'run', 'LIMIT': None}
    with patch.object(runner, 'main', side_effect=RuntimeError('load failed')):
        with pytest.raises(RuntimeError, match='load failed'):
            execute_progress(namespace)
    assert (runner.run, runner.write_new, sys.argv) == (original_run, original_write, original_argv)


def test_progress_wraps_cuda_oom_and_restores_globals(tmp_path):
    torch = fake_torch()
    original_run, original_write, original_argv = runner.run, runner.write_new, sys.argv
    logs = io.StringIO()
    private_marker = 'PRIVATE NOVEL TEXT'
    oom = torch.cuda.OutOfMemoryError('CUDA out of memory while loading ' + private_marker)
    namespace = {'sys': sys, 'Path': Path, 'REPO': tmp_path, 'MODEL': runner.MODELS[1],
                 'REVISION': 'a' * 40, 'CORPUS': tmp_path / 'corpus.json',
                 'OUTPUT': tmp_path / 'run', 'LIMIT': None}
    with patch.object(runner, 'main', side_effect=oom), redirect_stdout(logs), \
         pytest.raises(RuntimeError, match='Disconnect and delete runtime') as caught:
        execute_progress(namespace, torch)
    assert caught.value.__cause__ is oom
    assert private_marker not in str(caught.value)
    assert private_marker not in logs.getvalue()
    assert 'GPU preflight PID=' in logs.getvalue()
    assert 'free=8.00 GiB total=16.00 GiB' in logs.getvalue()
    assert (runner.run, runner.write_new, sys.argv) == (original_run, original_write, original_argv)


def test_progress_does_not_claim_save_when_write_fails(tmp_path):
    plan = runner.build_plan(corpus(), Tokenizer(), runner.MODELS[1], 'a' * 40)
    logs = io.StringIO()
    original_run = runner.run

    def fail_result_write(path, value):
        if Path(path).parent.name == 'results':
            raise OSError('disk full')
        runner_original_write(path, value)

    runner_original_write = runner.write_new

    def main():
        runner.run(plan, tmp_path / 'run', lambda chunk: {
            'translated_text': 'fake', 'raw_output_ids': [2], 'finish_reason': 'eos'})

    namespace = {'sys': __import__('sys'), 'Path': Path, 'REPO': tmp_path,
                 'MODEL': runner.MODELS[1], 'REVISION': 'a' * 40,
                 'CORPUS': tmp_path / 'corpus.json', 'OUTPUT': tmp_path / 'run', 'LIMIT': None}
    with patch.object(runner, 'main', main), patch.object(runner, 'write_new', fail_result_write):
        with redirect_stdout(logs), pytest.raises(OSError, match='disk full'):
            execute_progress(namespace)
        assert runner.write_new is fail_result_write
        assert runner.run is original_run
    assert 'sinh xong' in logs.getvalue()
    assert 'Đã lưu chunk' not in logs.getvalue()
