import json
import base64
import re
import sys
import types
import uuid
from urllib.parse import unquote

import pytest

from app import real_bundles as real
from app.core import Store
from scripts import run_colab


class TinyTokenizer:
    chat_template = 'tiny-chat'
    def encode(self, text, add_special_tokens=False): return [ord(c) for c in text]
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        assert kwargs == {'enable_thinking': False}
        return [ord(c) for c in ''.join(m['content'] for m in messages)]


def make_job(path, two=False):
    store = Store(path)
    if two:
        raw = b'one\ntwo'
        book = store.import_txt(raw, 'Fixture', [{'title': 'One', 'text': 'one\n'}, {'title': 'Two', 'text': 'two'}])
    else:
        raw = b'fixture source'
        book = store.import_txt(raw, 'Fixture', [{'title': 'One', 'text': raw.decode()}])
    snap = real.default_snapshot(real.QWEN35, real.MODELS[real.QWEN35], TinyTokenizer.chat_template)
    job = store.create_real_job(book, TinyTokenizer(), snap)
    return store, job, store.get_real_manifest(job)


def test_dry_run_is_local_only_and_validates_job(tmp_path, monkeypatch, capsys):
    _, job, manifest = make_job(tmp_path)
    monkeypatch.setattr(run_colab, '_discover_target', lambda *_: pytest.fail('dry-run touched OAuth'))
    assert run_colab.main(['--data-dir', str(tmp_path), '--job-id', job, '--session', 'existing', '--dry-run']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {'job_id': job, 'session': 'existing', 'chunks': len(manifest['chunks']),
                      'limit': None, 'drive_results': f'MyDrive/novel-batch/{job}/results', 'dry_run': True}
    with pytest.raises(SystemExit):
        run_colab.main(['--data-dir', str(tmp_path), '--job-id', job, '--session', 'x', '--timeout', 'nan'])


def test_exact_alias_assignment_kernel_and_idle_guards():
    session = types.SimpleNamespace(endpoint='endpoint', kernel_id='kernel', session_id='session',
                                    accelerator='T4', variant='GPU')
    assignment = {'endpoint': 'endpoint', 'accelerator': 'T4', 'variant': 'GPU'}
    sessions = [{'id': 'session', 'kernel': {'id': 'kernel'}}]
    kernels = [{'id': 'kernel', 'execution_state': 'idle'}]
    assert run_colab.verify_target(session, [assignment], sessions, kernels) == assignment
    session_without_session_id = types.SimpleNamespace(endpoint='endpoint', kernel_id='kernel', session_id=None,
                                                        accelerator='T4', variant='GPU')
    assert run_colab.verify_target(session_without_session_id, [assignment], [], kernels) == assignment
    for assigns, sess, ks in [([assignment, assignment], sessions, kernels),
                               ([assignment | {'accelerator': 'A100'}], sessions, kernels),
                               ([assignment], sessions, [kernels[0] | {'execution_state': 'busy'}]),
                               ([assignment], sessions + sessions, kernels),
                               ([assignment], sessions, kernels + kernels)]:
        with pytest.raises(run_colab.ColabError):
            run_colab.verify_target(session, assigns, sess, ks)


class FakeResponse:
    status_code = 200
    def iter_content(self, size): return iter([b'[]'])
    def close(self): pass


class FakeTransport:
    def __init__(self): self.call = None
    def request(self, *args, **kwargs): self.call = (args, kwargs); return FakeResponse()


def test_jupyter_requests_are_bounded_and_remote_paths_reject_traversal():
    transport = FakeTransport()
    session = types.SimpleNamespace(url='https://runtime.example/', token='private-token')
    api = run_colab.JupyterAPI(session, transport)
    assert api.sessions() == []
    assert transport.call[1]['timeout'] == 20 and transport.call[1]['allow_redirects'] is False
    assert transport.call[1]['params']['colab-runtime-proxy-token'] == 'private-token'
    for path in ('../outside.json', '/absolute.json', 'a\\b.json', 'a//b', './a', 'a/./b', 'a:b', 'a\x00b'):
        with pytest.raises(run_colab.ColabError):
            api.content(path)


def test_contents_root_probe_maps_contents_root_slash_to_content_prefix():
    probe = '.novel-translate-probe-' + 'a' * 32
    expected = b'known-probe-bytes'
    class Response:
        def __init__(self, status, body=b''):
            self.status_code, self.body = status, body
        def iter_content(self, size): return iter([self.body])
        def close(self): pass
    class RootTransport:
        def __init__(self): self.paths = []
        def request(self, method, url, **kwargs):
            path = unquote(url.split('/api/contents/', 1)[1])
            self.paths.append((method, path, kwargs.get('json')))
            if method == 'GET' and path == 'content/' + probe:
                body = json.dumps({'type': 'file', 'format': 'base64',
                                   'content': base64.b64encode(expected).decode()}).encode()
                return Response(200, body)
            if method == 'GET': return Response(404)
            return Response(204)
    transport = RootTransport()
    api = run_colab.JupyterAPI(types.SimpleNamespace(url='https://runtime.example', token='private'), transport)
    assert api.detect_contents_root(probe, expected) == 'content'
    api.put_file('novel-translate-code/app.py', b'runner source')
    assert transport.paths[-1][0:2] == ('PUT', 'content/novel-translate-code/app.py')
    assert transport.paths[-1][2]['path'] == 'content/novel-translate-code/app.py'
    api.read_file('drive/MyDrive/novel-batch/job/results/chunk.json')
    assert transport.paths[-1][1] == 'content/drive/MyDrive/novel-batch/job/results/chunk.json'


def _result(manifest, chunk, translated='machine'):
    stamp = real.now()
    return real.canonical_bytes(real.make_result(manifest, chunk, {
        'translated_text': translated, 'output_tokens': 1, 'finish_reason': 'eos',
        'provenance': real.provenance(manifest)}, stamp, stamp))


def test_partial_collection_duplicates_manual_edits_and_malicious_ids(tmp_path):
    store, job, manifest = make_job(tmp_path, two=True)
    first, second = manifest['chunks']
    store.save_real_revision(job, first['chunk_id'], 'Late manual edit', 0, None, False)
    results = {first['chunk_id']: _result(manifest, first)}
    class API:
        paths = []
        def read_file(self, path):
            self.paths.append(path)
            return results.get(path.rsplit('/', 1)[-1][:-5])
    api = API()
    assert run_colab.collect_results(api, store, manifest, job) == {
        'imported': 1, 'duplicate': 0, 'rejected': 0, 'missing': 1, 'unavailable': 0}
    assert store.get_real_job(job)['chunks'][0]['revision']['edited_text'] == 'Late manual edit'
    assert run_colab.collect_results(api, store, manifest, job)['duplicate'] == 1
    results[second['chunk_id']] = b'{malformed'
    assert run_colab.collect_results(api, store, manifest, job)['rejected'] == 1
    api.paths.clear()
    malicious = json.loads(json.dumps(manifest))
    malicious['chunks'][0]['chunk_id'] = '../escape'
    counts = run_colab.collect_results(api, store, malicious, job)
    assert counts['rejected'] == 2 and all(not p.endswith('../escape.json') for p in api.paths)


def test_run_program_guards_remote_manifest_and_transfers_no_source_in_code(tmp_path):
    _, job, manifest = make_job(tmp_path)
    hashes = {'app/real_runner.py': 'a' * 64}
    program = run_colab.run_program(job, 'b' * 64, hashes, 'c' * 64, 1)
    assert 'DRIVE_MANIFEST_MISMATCH' in program
    assert 'read_bytes() != manifest_raw' in program
    assert 'LIMIT = 1' in program
    assert 'fixture source' not in program
    assert f"'../escape'" not in program


def test_allowlisted_remote_failure_code_survives_summary_mapping():
    outputs = [{'output_type': 'stream', 'text': '__NT_PREFLIGHT_ERROR__DRIVE_NOT_MOUNTED\n'}]
    with pytest.raises(run_colab.ColabError) as raised:
        run_colab._runtime_result(outputs, '__NT_PREFLIGHT', 'Remote preflight')
    assert run_colab._safe_remote_code(raised.value, 'LOCAL_OR_REMOTE_ERROR') == 'DRIVE_NOT_MOUNTED'


def test_execution_timeout_still_collects_durable_checkpoints(tmp_path, monkeypatch, capsys):
    _, job, manifest = make_job(tmp_path)
    class API:
        class Transport:
            closed = False
            def close(self): self.closed = True
        transport = Transport()
        def detect_contents_root(self, *_): return 'content'
    api, stopped, collected = API(), [], []
    session = types.SimpleNamespace(url='https://runtime.invalid', token='secret', kernel_id='kid', session_id='sid')
    monkeypatch.setattr(run_colab, '_discover_target', lambda *_: (session, object(), [], api))
    monkeypatch.setattr(run_colab, 'source_bundle', lambda: ({}, {}, 'bundle'))
    monkeypatch.setattr(run_colab, '_prepare_remote', lambda *a: ({}, 'bundle', 'manifest'))
    monkeypatch.setattr(run_colab, 'preflight_program', lambda *a: 'preflight')
    monkeypatch.setattr(run_colab, 'run_program', lambda *a: 'run')
    def collect(*args, **kwargs):
        collected.append(args)
        if kwargs.get('missing_out') is not None:
            kwargs['missing_out'].append(manifest['chunks'][0]['chunk_id'])
        return {'imported': 1, 'duplicate': 0, 'rejected': 0, 'missing': 0, 'unavailable': 0}
    monkeypatch.setattr(run_colab, 'collect_results', collect)
    class Runtime:
        def __init__(self, *args, **kwargs): pass
        def execute_code(self, code, timeout):
            if code == 'preflight': return [{'output_type': 'stream', 'text': '__NT_PREFLIGHT_OK__\n'}]
            if '__NT_PROBE_CLEANED__' in code: return [{'output_type': 'stream', 'text': '__NT_PROBE_CLEANED__\n'}]
            raise TimeoutError('private websocket URL')
        def stop(self): stopped.append(True)
    runtime_module = types.ModuleType('colab_cli.runtime')
    runtime_module.ColabRuntime = Runtime
    monkeypatch.setitem(sys.modules, 'colab_cli.runtime', runtime_module)
    args = types.SimpleNamespace(data_dir=tmp_path, job_id=job, session='alias', limit=1,
                                 timeout=10.0, restart_kernel=False, dry_run=False)
    monkeypatch.setattr(run_colab, '_load_alias', lambda *_: types.SimpleNamespace(kernel_id=str(uuid.uuid4())))
    assert run_colab.run(args) == 1
    assert stopped and collected and api.transport.closed
    output = capsys.readouterr().out
    assert 'timed_out' in output and 'private websocket URL' not in output


def test_runner_imports_each_new_chunk_before_next_remote_step(tmp_path, monkeypatch, capsys):
    store, job, manifest = make_job(tmp_path)
    session = types.SimpleNamespace(url='https://runtime.invalid', token='secret', kernel_id=str(uuid.uuid4()),
                                    session_id=None)
    class API:
        class Transport:
            closed = False
            def close(self): self.closed = True
        transport = Transport()
        def detect_contents_root(self, *_): return 'content'
    api = API()
    monkeypatch.setattr(run_colab, '_load_alias', lambda *_: types.SimpleNamespace(kernel_id=session.kernel_id))
    monkeypatch.setattr(run_colab, '_discover_target', lambda *_: (session, object(), [], api))
    monkeypatch.setattr(run_colab, 'source_bundle', lambda: ({}, {}, 'bundle'))
    monkeypatch.setattr(run_colab, '_prepare_remote', lambda *a: ({}, 'bundle', 'manifest'))
    monkeypatch.setattr(run_colab, 'preflight_program', lambda *a: 'preflight')
    programs, collected = [], []
    monkeypatch.setattr(run_colab, 'run_program', lambda *a: programs.append(a[-1]) or 'run')
    raw = _result(manifest, manifest['chunks'][0])
    def collect(_api, db, _manifest, _job, chunk_ids=None, missing_out=None):
        collected.append(chunk_ids)
        if chunk_ids is None:
            if missing_out is not None:
                missing_out.extend(chunk['chunk_id'] for chunk in _manifest['chunks'])
            return {'imported': 0, 'duplicate': 0, 'rejected': 0, 'missing': 1, 'unavailable': 0}
        assert db.import_real_result(raw) == 'imported'
        return {'imported': 1, 'duplicate': 0, 'rejected': 0, 'missing': 0, 'unavailable': 0}
    monkeypatch.setattr(run_colab, 'collect_results', collect)
    class Runtime:
        def __init__(self, *args, **kwargs): pass
        def execute_code(self, code, timeout):
            if code == 'preflight': return [{'output_type': 'stream', 'text': '__NT_PREFLIGHT_OK__\n'}]
            if '__NT_PROBE_CLEANED__' in code: return [{'output_type': 'stream', 'text': '__NT_PROBE_CLEANED__\n'}]
            return [{'output_type': 'stream', 'text': '__NT_RUN_OK__{"completed":1}\n'}]
        def stop(self): pass
    runtime_module = types.ModuleType('colab_cli.runtime')
    runtime_module.ColabRuntime = Runtime
    monkeypatch.setitem(sys.modules, 'colab_cli.runtime', runtime_module)
    args = types.SimpleNamespace(data_dir=tmp_path, job_id=job, session='alias', limit=None,
                                 timeout=30.0, restart_kernel=False, dry_run=False)
    assert run_colab.run(args) == 0
    assert programs == [1] and collected == [None, [manifest['chunks'][0]['chunk_id']]]
    assert store.get_real_job(job)['completed'] == 1


def test_local_completed_result_seeds_empty_drive_before_remote_resume(tmp_path, monkeypatch, capsys):
    store, job, manifest = make_job(tmp_path, two=True)
    first, second = manifest['chunks']
    first_raw = _result(manifest, first)
    assert store.import_real_result(first_raw) == 'imported'
    session = types.SimpleNamespace(url='https://runtime.invalid', token='secret', kernel_id=str(uuid.uuid4()),
                                    session_id=None)
    class API:
        class Transport:
            def close(self): pass
        transport = Transport()
        results = {}
        saved_manifest = None
        def detect_contents_root(self, *_): return 'content'
        def read_file(self, path):
            if path.endswith('/manifest.json'):
                return self.saved_manifest
            return self.results.get(path.rsplit('/', 1)[-1][:-5]) if '/results/' in path else None
        def put_file(self, path, raw):
            if path.endswith('/manifest.json'):
                self.saved_manifest = raw
            elif '/results/' in path:
                self.results[path.rsplit('/', 1)[-1][:-5]] = raw
        def ensure_directory(self, path): pass
    api = API()
    monkeypatch.setattr(run_colab, '_load_alias', lambda *_: types.SimpleNamespace(kernel_id=session.kernel_id))
    monkeypatch.setattr(run_colab, '_discover_target', lambda *_: (session, object(), [], api))
    monkeypatch.setattr(run_colab, 'source_bundle', lambda: ({}, {}, 'bundle'))
    monkeypatch.setattr(run_colab, '_prepare_remote', lambda *a: ({}, 'bundle', 'manifest'))
    monkeypatch.setattr(run_colab, 'preflight_program', lambda *a: 'preflight')
    monkeypatch.setattr(run_colab, 'run_program', lambda *a: 'run')
    generated = []
    remote_results = tmp_path / 'remote-results'
    class Runtime:
        def __init__(self, *args, **kwargs): pass
        def execute_code(self, code, timeout):
            if code == 'preflight':
                return [{'output_type': 'stream', 'text': '__NT_PREFLIGHT_OK__\n'}]
            if '__NT_PROBE_CLEANED__' in code:
                return [{'output_type': 'stream', 'text': '__NT_PROBE_CLEANED__\n'}]
            remote_results.mkdir(exist_ok=True)
            for chunk_id, raw in api.results.items():
                (remote_results / (chunk_id + '.json')).write_bytes(raw)
            from app.real_runner import run_manifest
            def generate(batch, chunk):
                generated.append(chunk['chunk_id'])
                return {'translated_text': 'generated second', 'output_tokens': 1, 'finish_reason': 'eos',
                        'provenance': real.provenance(batch)}
            result = run_manifest(manifest, remote_results, generate, limit=1)
            for path in remote_results.glob('*.json'):
                if path.name != 'manifest.json':
                    api.results[path.stem] = path.read_bytes()
            return [{'output_type': 'stream', 'text': '__NT_RUN_OK__' + json.dumps(result) + '\n'}]
        def stop(self): pass
    runtime_module = types.ModuleType('colab_cli.runtime')
    runtime_module.ColabRuntime = Runtime
    monkeypatch.setitem(sys.modules, 'colab_cli.runtime', runtime_module)
    args = types.SimpleNamespace(data_dir=tmp_path, job_id=job, session='alias', limit=1,
                                 timeout=30.0, restart_kernel=False, dry_run=False)
    assert run_colab.run(args) == 0
    assert api.results[first['chunk_id']] == first_raw
    assert generated == [second['chunk_id']]
    assert store.get_real_job(job)['completed'] == 2
    report = json.loads(capsys.readouterr().out)
    assert report['seeded'] == 1 and report['remote'] == 'completed'
