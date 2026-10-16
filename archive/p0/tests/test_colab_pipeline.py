from types import SimpleNamespace
import sys

import pytest
pytest.importorskip('colab_cli.client')
from colab_cli.client import Accelerator, AssignmentVariant

from scripts.run_p0_colab import (
    MODEL,
    REVISION,
    _outputs_have_error,
    bootstrap_program,
    dependency_program,
    verify_target,
)


def target():
    return SimpleNamespace(endpoint='runtime-1', kernel_id='kernel-1', session_id=None)


def data(path='p0_qwen35_benchmark.ipynb', state='idle'):
    return (
        [SimpleNamespace(endpoint='runtime-1', accelerator=Accelerator.T4,
                          variant=AssignmentVariant.GPU)],
        [{'id': 'session-1', 'path': path, 'kernel': {'id': 'kernel-1'}}],
        [{'id': 'kernel-1', 'execution_state': state}],
    )


def test_attaches_only_exact_idle_qwen35_kernel():
    session = target()
    assignments, sessions, kernels = data(
        path='p0_qwen35_benchmark-jvsc-faf8f0d4-0315-457e-8f38-3abbe85ef01cfa6c5be7-4194-4b5e-854c-b61180527630.ipynb')
    sessions[0]['name'] = 'p0_qwen35_benchmark-6e032751-053c-4e54-8a9b-095d314335a5.ipynb'
    result = verify_target(session, assignments, sessions, kernels)
    assert result.kernel_id == 'kernel-1'
    assert result.session_id is None


@pytest.mark.parametrize('sessions,kernels,message', [
    ([{'path': 'p0_qwen35_benchmark.ipynb', 'kernel': {'id': 'kernel-1'}},
      {'path': 'p0_qwen35_benchmark.ipynb', 'kernel': {'id': 'kernel-1'}}],
     [{'id': 'kernel-1', 'execution_state': 'idle'}], 'exactly one'),
    ([{'path': 'p0_qwen25_benchmark.ipynb', 'kernel': {'id': 'kernel-1'}}],
     [{'id': 'kernel-1', 'execution_state': 'idle'}], 'identify'),
    ([{'path': 'p0_qwen35_benchmark.ipynb', 'kernel': {'id': 'kernel-1'}}],
     [{'id': 'kernel-1', 'execution_state': 'busy'}], 'busy'),
])
def test_refuses_ambiguous_unrecognized_or_busy_kernel(sessions, kernels, message):
    assignments, _, _ = data()
    with pytest.raises(RuntimeError, match=message):
        verify_target(target(), assignments, sessions, kernels)


def test_refuses_non_gpu_assignment_and_alias_kernel_mismatch():
    assignments, sessions, kernels = data()
    assignments[0] = SimpleNamespace(endpoint='runtime-1', accelerator=Accelerator.A100,
                                     variant=AssignmentVariant.GPU)
    with pytest.raises(RuntimeError, match='T4 GPU'):
        verify_target(target(), assignments, sessions, kernels)
    assignments[0] = SimpleNamespace(endpoint='runtime-1', accelerator=Accelerator.T4,
                                     variant=AssignmentVariant.GPU)
    wrong_alias = target()
    wrong_alias.kernel_id = 'another-kernel'
    with pytest.raises(RuntimeError, match='registered Colab kernel alias'):
        verify_target(wrong_alias, assignments, sessions, kernels)
    unregistered_alias = target()
    unregistered_alias.kernel_id = None
    with pytest.raises(RuntimeError, match='registered Colab kernel alias'):
        verify_target(unregistered_alias, assignments, sessions, kernels)


def test_generated_remote_flow_uses_trusted_bootstrap_and_runner_resume_contract():
    source = bootstrap_program(None)
    compile(source, '<remote P0 program>', 'exec')
    assert "Path('/content/drive/MyDrive').is_dir()" in source
    assert 'Drive is not mounted' in source
    assert "Path('/content/drive/MyDrive/p0/corpus.json')" in source
    assert 'bootstrap_source' not in source
    assert f"MODEL = {MODEL!r}" in source
    assert f"REVISION = {REVISION!r}" in source
    assert "digest({'corpus': corpus, 'model': MODEL, 'revision': REVISION, 'config': CONFIG})" in source
    assert "runner.main()" in source
    assert "'--limit'" in source  # Existing progress cell forwards the optional smoke limit.
    assert "LIMIT = None" in source
    smoke_source = bootstrap_program(1)
    assert "LIMIT = 1" in smoke_source
    assert "CORPUS.read_bytes()" in source  # Corpus content is read remotely, never embedded locally.


def test_dependency_subprocess_failure_propagates_and_remote_errors_are_detected():
    source = dependency_program()
    compile(source, '<remote dependency preflight>', 'exec')
    assert 'subprocess.run([sys.executable, \'-m\', \'pip\', \'install\', *missing], check=True)' in source
    assert 'if not False and globals().get(\'model\')' in source
    assert 'if not True and globals().get(\'model\')' in dependency_program(True)
    error = {'output_type': 'error', 'ename': 'RuntimeError', 'evalue': 'Drive is not mounted'}
    assert _outputs_have_error([{'output_type': 'stream', 'text': 'ok'}, error]) is error


@pytest.mark.parametrize('restart_kernel,dependency_output,expect_error', [
    (False, [{'output_type': 'error', 'ename': 'CalledProcessError', 'evalue': 'pip failed'}], True),
    (True, [{'output_type': 'stream', 'text': 'P0_DEPENDENCIES_OK'}], False),
])
def test_local_run_uses_verified_proxy_auth_and_restarts_or_propagates_install_error(
        monkeypatch, tmp_path, restart_kernel, dependency_output, expect_error):
    import requests
    import scripts.run_p0_colab as cli

    session = SimpleNamespace(endpoint='runtime-1', kernel_id='kernel-1', session_id='registered-id',
                              token='private-token', url='https://runtime.example/')
    assignments, sessions, kernels = data()
    store = SimpleNamespace(add=lambda value: None)
    fake_state = SimpleNamespace(config_path=None, client=SimpleNamespace(list_assignments=lambda: assignments),
                                 get_session=lambda name: session, store=store)
    monkeypatch.setitem(sys.modules, 'colab_cli.common', SimpleNamespace(state=fake_state))
    seen = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    def get(url, **kwargs):
        seen.append((url, kwargs))
        return Response(sessions if url.endswith('api/sessions') else kernels)

    monkeypatch.setattr(requests, 'get', get)
    calls = []

    class Runtime:
        def __init__(self, *args, **kwargs): calls.append(('init', args, kwargs))
        def execute_code(self, code, **kwargs):
            if code == dependency_program(restart_kernel):
                return dependency_output
            calls.append(('runner', code))
            return []
        def restart(self, **kwargs): calls.append(('restart', kwargs))
        def stop(self): calls.append(('stop',))

    monkeypatch.setattr('colab_cli.runtime.ColabRuntime', Runtime)
    monkeypatch.setattr(cli, 'STATE_FILE', tmp_path / 'data' / 'sessions.json')
    args = SimpleNamespace(session='qwen35-vscode', limit=None, timeout=120,
                           restart_kernel=restart_kernel)
    if expect_error:
        with pytest.raises(RuntimeError, match='Dependency preflight failed'):
            cli.run(args)
    else:
        cli.run(args)

    assert [url for url, _ in seen] == ['https://runtime.example/api/sessions', 'https://runtime.example/api/kernels']
    for _, kwargs in seen:
        assert kwargs['headers'] == {'X-Colab-Client-Agent': 'colab-cli',
                                     'X-Colab-Runtime-Proxy-Token': 'private-token'}
        assert kwargs['params'] == {'colab-runtime-proxy-token': 'private-token'}
    assert calls[0][2]['session_id'] == 'registered-id'
    assert calls[-1] == ('stop',)
    assert ('restart', {'timeout': 120}) in calls if restart_kernel else not any(c[0] == 'restart' for c in calls)
