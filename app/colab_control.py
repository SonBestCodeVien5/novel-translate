"""Local start/status controls for the existing Colab CLI aliases."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'run_colab.py'
MAX_STATE = 64 * 1024
SAFE_SUMMARY = {'job_id', 'remote', 'error_type', 'imported', 'duplicate', 'rejected',
                'missing', 'unavailable', 'seeded'}
_START_LOCK = threading.Lock()


class ColabControlError(Exception):
    pass


def _sessions_path(data_dir):
    return Path(data_dir) / 'colab-cli' / 'sessions.json'


def _read_sessions(data_dir):
    path = _sessions_path(data_dir)
    try:
        if path.stat().st_size > 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    sessions = value.get('sessions', value)
    return sessions if isinstance(sessions, dict) else {}


def _is_t4_gpu(item):
    if not isinstance(item, dict):
        return False
    accelerator = item.get('accelerator')
    variant = item.get('variant')
    if isinstance(accelerator, dict):
        accelerator = accelerator.get('name')
    if isinstance(variant, dict):
        variant = variant.get('name')
    return (accelerator == 'T4' and variant == 'GPU' and
            isinstance(item.get('kernel_id'), str) and
            re.fullmatch(r'[0-9a-fA-F-]{36}', item['kernel_id']) is not None)


def available_sessions(data_dir):
    """Return only display-safe T4 aliases; never return endpoints or credentials."""
    if importlib.util.find_spec('colab_cli') is None:
        return []
    return sorted(alias for alias, item in _read_sessions(data_dir).items()
                  if isinstance(alias, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', alias)
                  and _is_t4_gpu(item))


def validate_alias(data_dir, alias):
    if not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', alias):
        raise ColabControlError('Choose a registered T4 GPU alias.')
    item = _read_sessions(data_dir).get(alias)
    if not _is_t4_gpu(item):
        raise ColabControlError('The selected alias is unavailable or is not a registered T4 GPU.')
    # The CLI StateStore is the source of truth consumed by the runner.
    try:
        from colab_cli.state import StateStore
        registered = StateStore(str(_sessions_path(data_dir))).get(alias)
    except Exception:
        registered = None
    if registered is None or getattr(registered, 'kernel_id', None) != item['kernel_id']:
        raise ColabControlError('The selected alias could not be verified by the Colab CLI.')
    return item


def _paths(data_dir, job_id):
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', job_id):
        raise ColabControlError('Invalid job ID.')
    root = Path(data_dir) / 'colab-cli' / 'web-jobs'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root / (job_id + '.json'), root / (job_id + '.log')


def _write_state(path, state):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(state, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read_state(path):
    try:
        if path.stat().st_size > MAX_STATE:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _owned_pid(pid, script, job_id, data_dir):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        argv = Path('/proc', str(pid), 'cmdline').read_bytes().split(b'\0')
        values = [part.decode('utf-8', 'replace') for part in argv if part]
        if str(script) not in values or '--job-id' not in values or '--data-dir' not in values:
            return False
        return (values[values.index('--job-id') + 1] == job_id and
                Path(values[values.index('--data-dir') + 1]).resolve() == Path(data_dir).resolve())
    except (OSError, ValueError, IndexError):
        return False


def _summary(log_path):
    try:
        with log_path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 16384))
            raw = stream.read(16384)
    except OSError:
        return {}
    for line in reversed(raw.decode('utf-8', 'replace').splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return {key: value[key] for key in SAFE_SUMMARY if key in value and
                    (isinstance(value[key], (str, int)) and type(value[key]) in (str, int))}
    return {}


def start_job(data_dir, job_id, alias, limit):
    item = validate_alias(data_dir, alias)
    state_path, log_path = _paths(data_dir, job_id)
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ColabControlError('Chunk limit must be a positive integer.')
    with _START_LOCK:
        old = _read_state(state_path) or {}
        if _owned_pid(old.get('pid'), SCRIPT, job_id, data_dir):
            if old.get('alias') == alias:
                return status_job(data_dir, job_id)
            raise ColabControlError('This job already has a local Colab process running.')
        for candidate in state_path.parent.glob('*.json'):
            other = _read_state(candidate)
            other_job = other.get('job_id') if other else None
            if (other_job and other_job != job_id and other.get('kernel_id') == item['kernel_id'] and
                    _owned_pid(other.get('pid'), SCRIPT, other_job, data_dir)):
                raise ColabControlError('This registered kernel already has a local Colab process running.')
        argv = [sys.executable, str(SCRIPT), '--data-dir', str(Path(data_dir).resolve()),
                '--job-id', job_id, '--session', alias]
        if limit is not None:
            argv += ['--limit', str(limit)]
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'wb') as log:
            process = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, shell=False, close_fds=True)
        state = {'job_id': job_id, 'alias': alias, 'kernel_id': item['kernel_id'],
                 'pid': process.pid, 'started_at': int(time.time()), 'log': str(log_path)}
        _write_state(state_path, state)
        return {'state': 'running', 'alias': alias, 'summary': {}}


def status_job(data_dir, job_id):
    state_path, log_path = _paths(data_dir, job_id)
    state = _read_state(state_path)
    if not state or state.get('job_id') != job_id or state.get('log') != str(log_path):
        return {'state': 'not_started', 'alias': None, 'summary': {}}
    running = _owned_pid(state.get('pid'), SCRIPT, job_id, data_dir)
    summary = _summary(log_path)
    success = (summary.get('remote') == 'completed' and summary.get('error_type') is None and
               summary.get('rejected', 0) == 0 and summary.get('unavailable', 0) == 0)
    return {'state': 'running' if running else ('finished' if success else 'failed'),
            'alias': state.get('alias'), 'summary': summary}
