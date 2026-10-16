import json
import re
import stat
import uuid

from fastapi.testclient import TestClient
import pytest

from app import colab_control
from app.main import create_app
from app.real_bundles import MODELS, QWEN35, default_snapshot


class TinyTokenizer:
    chat_template = 'tiny-chat'
    def encode(self, text, add_special_tokens=False): return [ord(c) for c in text]
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        return [ord(c) for m in messages for c in m['content']]


def _csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def _job(client):
    store = client.app.state.store
    book = store.import_txt(b'fixture', 'Fixture', [{'title': 'One', 'text': 'fixture'}])
    snapshot = default_snapshot(QWEN35, MODELS[QWEN35], TinyTokenizer.chat_template)
    return book, store.create_real_job(book, TinyTokenizer(), snapshot)


def test_colab_form_csrf_ownership_and_safe_status(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    calls = []
    monkeypatch.setattr('app.colab_control.available_sessions', lambda *_: ['registered-t4'])
    monkeypatch.setattr('app.colab_control.status_job', lambda *_: {
        'state': 'running', 'alias': 'registered-t4', 'summary': {'remote': 'preflight_ok'}})
    monkeypatch.setattr('app.colab_control.start_job', lambda *args: calls.append(args) or {
        'state': 'running', 'alias': args[2], 'summary': {}})
    with TestClient(app, base_url='http://127.0.0.1') as client:
        book, job = _job(client)
        other = client.app.state.store.import_txt(b'other', 'Other', [{'title': 'One', 'text': 'other'}])
        url = f'/books/{book}/real-jobs/{job}'
        token = _csrf(client.get(url))
        page = client.get(url)
        assert 'running' in page.text and 'registered-t4' in page.text
        assert 'Chạy hoặc resume trên Colab' in page.text
        assert client.post(url + '/colab', data={'session': 'registered-t4'}).status_code == 403
        assert client.post(f'/books/{other}/real-jobs/{job}/colab',
                           data={'csrf': token, 'session': 'registered-t4'}).status_code == 404
        assert client.post(url + '/colab', data={'csrf': token, 'session': 'registered-t4', 'limit': '2'},
                           follow_redirects=False).status_code == 303
        assert calls == [(tmp_path, job, 'registered-t4', 2)]


def test_start_uses_fixed_script_argv_and_status_sanitizes_log(tmp_path, monkeypatch):
    job, kernel = str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setattr(colab_control, 'validate_alias', lambda *_: {'kernel_id': kernel})
    captured = {}
    class Process:
        pid = 12345
    def popen(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        return Process()
    monkeypatch.setattr(colab_control.subprocess, 'Popen', popen)
    started = colab_control.start_job(tmp_path, job, 'registered-t4', 3)
    assert started['state'] == 'running'
    assert captured['argv'] == [colab_control.sys.executable, str(colab_control.SCRIPT), '--data-dir',
                                str(tmp_path.resolve()), '--job-id', job, '--session', 'registered-t4',
                                '--limit', '3']
    assert captured['kwargs']['shell'] is False
    assert captured['kwargs']['stdin'] is colab_control.subprocess.DEVNULL
    state_path, log_path = colab_control._paths(tmp_path, job)
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600
    log_path.write_bytes(b'x' * 100000 + b'\n' + json.dumps({'job_id': job, 'remote': 'completed', 'imported': 1,
                                    'token': 'must-not-escape'}).encode())
    colab_control._write_state(state_path, {'job_id': job, 'alias': 'registered-t4', 'kernel_id': kernel,
                                            'pid': 12345, 'log': str(log_path)})
    monkeypatch.setattr(colab_control, '_owned_pid', lambda *_: False)
    status = colab_control.status_job(tmp_path, job)
    assert status['state'] == 'finished' and status['summary']['imported'] == 1
    assert 'token' not in status['summary']


def test_start_rejects_second_alias_for_same_running_kernel(tmp_path, monkeypatch):
    job, other_job, kernel = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setattr(colab_control, 'validate_alias', lambda *_: {'kernel_id': kernel})
    state_path, log_path = colab_control._paths(tmp_path, other_job)
    log_path.touch()
    colab_control._write_state(state_path, {'job_id': other_job, 'alias': 'other-alias', 'kernel_id': kernel,
                                            'pid': 99999, 'log': str(log_path)})
    monkeypatch.setattr(colab_control, '_owned_pid', lambda pid, *_: pid == 99999)
    monkeypatch.setattr(colab_control.subprocess, 'Popen', lambda *a, **kw: pytest.fail('must not launch'))
    with pytest.raises(colab_control.ColabControlError, match='kernel already has'):
        colab_control.start_job(tmp_path, job, 'alias', 1)
