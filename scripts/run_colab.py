#!/usr/bin/env python3
"""Run or resume one existing Colab v2 job and import durable checkpoints."""
import argparse
import base64
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import bundles, real_bundles as real
from app.core import DomainError, Store
from scripts.build_translate_notebook import SOURCES

PINS = {'transformers': '5.3.0', 'accelerate': '1.11.0', 'bitsandbytes': '0.48.2'}
HTTP_TIMEOUT = 20
MAX_HTTP_JSON = bundles.MAX_BYTES * 2 + 65536
SAFE_REMOTE_CODES = {'DRIVE_NOT_MOUNTED', 'GPU_REQUIRED', 'DEPENDENCIES_MISMATCH', 'CODE_CHANGED',
                     'RESTART_REQUIRED', 'MODEL_ALREADY_LOADED', 'SOURCE_HASH_MISMATCH',
                     'MANIFEST_HASH_MISMATCH', 'WRONG_JOB', 'DRIVE_MANIFEST_MISMATCH',
                   'RUNNER_FAILED', 'PREFLIGHT_FAILED', 'CONTENT_ROOT_UNVERIFIED',
                   'CONTENT_PROBE_CLEANUP_FAILED', 'REMOTE_ERROR'}


class ColabError(Exception):
    pass


def _field(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def verify_target(session, assignments, sessions, kernels):
    """Require one T4 GPU assignment and its exact idle registered kernel."""
    if not session or not session.endpoint or not session.kernel_id:
        raise ColabError('Alias is missing endpoint or kernel metadata.')
    assignment = [a for a in assignments if _field(a, 'endpoint') == session.endpoint]
    if len(assignment) != 1:
        raise ColabError('Alias must match exactly one active Colab assignment.')
    a = assignment[0]
    if (_field(_field(a, 'accelerator'), 'name', _field(a, 'accelerator')) != 'T4' or
            _field(_field(a, 'variant'), 'name', _field(a, 'variant')) != 'GPU'):
        raise ColabError('Alias assignment is not a T4 GPU.')
    if session.accelerator != 'T4' or session.variant != 'GPU':
        raise ColabError('Registered alias hardware metadata does not match T4 GPU.')
    matching_kernels = [item for item in kernels if item.get('id') == session.kernel_id]
    if len(matching_kernels) != 1:
        raise ColabError('Alias does not identify exactly one live kernel.')
    if session.session_id:
        matching_sessions = [item for item in sessions if item.get('id') == session.session_id and
                             _field(item.get('kernel') or {}, 'id') == session.kernel_id]
        if len(matching_sessions) != 1:
            raise ColabError('Alias does not identify exactly one live notebook.')
    elif sum(_field(item.get('kernel') or {}, 'id') == session.kernel_id for item in sessions) > 1:
        raise ColabError('Kernel appears in ambiguous notebook sessions.')
    if matching_kernels[0].get('execution_state') != 'idle':
        raise ColabError('Registered Colab kernel is busy; no code was sent.')
    return a


def _remote_path(path):
    if (not isinstance(path, str) or not path or path.startswith('/') or '\\' in path or
            '\x00' in path or ':' in path or any(part in ('', '.', '..') for part in path.split('/'))):
        raise ColabError('Unsafe remote file path.')
    normalized = PurePosixPath(path).as_posix()
    if normalized != path:
        raise ColabError('Unsafe remote file path.')
    return normalized


class JupyterAPI:
    """Small bounded Jupyter REST client; deliberately avoids ContentsClient."""
    def __init__(self, session, transport=None):
        if transport is None:
            import requests
            transport = requests.Session()
        self.transport = transport
        self.base = session.url.rstrip('/') + '/'
        self.token = session.token
        self.deadline = None
        self.contents_prefix = ''
        self.headers = {'X-Colab-Client-Agent': 'colab-cli',
                        'X-Colab-Runtime-Proxy-Token': session.token}

    def request(self, method, path, *, params=None, payload=None, cap=1024 * 1024, allow_404=False):
        url = urljoin(self.base, 'api/' + path.lstrip('/'))
        query = {'authuser': '0', 'colab-runtime-proxy-token': self.token}
        if params:
            query.update(params)
        try:
            timeout = HTTP_TIMEOUT
            if self.deadline is not None:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Colab wall-time budget expired.')
                timeout = min(timeout, remaining)
            response = self.transport.request(method, url, headers=self.headers, params=query,
                json=payload, timeout=timeout, allow_redirects=False, stream=True)
        except TimeoutError:
            raise
        except Exception as exc:
            raise ColabError('Colab HTTP request failed (' + type(exc).__name__ + ').') from None
        try:
            if response.status_code == 404 and allow_404:
                return None
            if response.status_code not in (200, 201, 204):
                raise ColabError('Colab HTTP request returned status ' + str(response.status_code) + '.')
            raw = bytearray()
            for block in response.iter_content(65536):
                raw.extend(block)
                if len(raw) > cap:
                    raise ColabError('Colab response exceeded its size limit.')
            if method == 'DELETE' or not raw:
                return None
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError):
                raise ColabError('Colab returned invalid JSON.') from None
        finally:
            response.close()

    def sessions(self):
        value = self.request('GET', 'sessions')
        if type(value) is not list:
            raise ColabError('Colab returned an invalid session list.')
        return value

    def kernels(self):
        value = self.request('GET', 'kernels')
        if type(value) is not list:
            raise ColabError('Colab returned an invalid kernel list.')
        return value

    def content(self, path):
        path = self._contents_path(path)
        value = self.request('GET', 'contents/' + quote(path, safe='/'), params={'content': '1'},
                             cap=MAX_HTTP_JSON, allow_404=True)
        if value is not None and type(value) is not dict:
            raise ColabError('Colab returned an invalid file record.')
        return value

    def _contents_path(self, path):
        path = _remote_path(path)
        return _remote_path(self.contents_prefix + '/' + path) if self.contents_prefix else path

    def detect_contents_root(self, probe_name, expected):
        """Match API paths to a known file created at /content by preflight."""
        if not re.fullmatch(r'\.novel-translate-probe-[0-9a-f]{32}', probe_name):
            raise ColabError('Invalid content-root probe name.')
        matches = []
        for candidate in (probe_name, 'content/' + probe_name):
            raw = self.read_file(candidate)
            if raw == expected:
                matches.append(candidate)
        if len(matches) != 1:
            raise ColabError('CONTENT_ROOT_UNVERIFIED')
        self.contents_prefix = 'content' if matches[0].startswith('content/') else ''
        return self.contents_prefix

    def ensure_directory(self, path):
        path = _remote_path(path)
        current = self.content(path)
        if current is not None:
            if current.get('type') != 'directory':
                raise ColabError('Remote code folder is not a directory.')
            return
        mapped = self._contents_path(path)
        self.request('PUT', 'contents/' + quote(mapped, safe='/'),
                     payload={'type': 'directory', 'path': mapped}, cap=65536)

    def put_file(self, path, raw):
        path = _remote_path(path)
        if not isinstance(raw, bytes) or len(raw) > bundles.MAX_BYTES:
            raise ColabError('Local transfer file exceeds the size limit.')
        mapped = self._contents_path(path)
        self.request('PUT', 'contents/' + quote(mapped, safe='/'), payload={
            'type': 'file', 'format': 'base64', 'content': base64.b64encode(raw).decode('ascii'),
            'path': mapped, 'name': PurePosixPath(mapped).name,
        }, cap=MAX_HTTP_JSON)

    def read_file(self, path):
        value = self.content(path)
        if value is None:
            return None
        if value.get('type') != 'file':
            raise ColabError('Expected a remote regular file.')
        content, fmt = value.get('content'), value.get('format')
        if type(content) is not str:
            raise ColabError('Remote file has invalid content.')
        try:
            raw = base64.b64decode(content, validate=True) if fmt == 'base64' else content.encode('utf-8')
        except (ValueError, UnicodeError):
            raise ColabError('Remote file content is invalid.') from None
        if len(raw) > bundles.MAX_BYTES:
            raise ColabError('Remote result exceeds the size limit.')
        return raw

    def restart(self, kernel_id):
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', kernel_id):
            raise ColabError('Registered kernel ID is invalid.')
        self.request('POST', 'kernels/' + quote(kernel_id, safe='') + '/restart', cap=65536)
        deadline = time.monotonic() + 60
        while True:
            kernels = self.kernels()
            matches = [k for k in kernels if k.get('id') == kernel_id]
            if len(matches) != 1:
                raise ColabError('Restarted kernel could not be identified.')
            if matches[0].get('execution_state') == 'idle':
                return
            if time.monotonic() >= deadline:
                raise ColabError('Restart did not become idle within 60 seconds.')
            time.sleep(1)


def source_bundle():
    sources = {name: (ROOT / name).read_bytes() for name in SOURCES}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
    bundle_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return sources, hashes, bundle_hash


def preflight_program(hashes, bundle_hash, probe_name, probe_bytes):
    return f'''import importlib.metadata, json, sys
from pathlib import Path
PINS = {PINS!r}
EXPECTED_HASHES = {hashes!r}
EXPECTED_BUNDLE_HASH = {bundle_hash!r}
PROBE_NAME = {probe_name!r}
PROBE_BYTES = {probe_bytes!r}
class RemoteAbort(Exception): pass
try:
    if not Path('/content/drive/MyDrive').is_dir(): raise RemoteAbort('DRIVE_NOT_MOUNTED')
    import torch
    if not torch.cuda.is_available(): raise RemoteAbort('GPU_REQUIRED')
    missing = []
    for name, expected in PINS.items():
        try: actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: actual = None
        if actual != expected: missing.append(name + '==' + expected)
    if missing: raise RemoteAbort('DEPENDENCIES_MISMATCH')
    loaded = globals().get('NOVEL_TRANSLATE_SOURCE_BUNDLE_HASH')
    if loaded not in (None, EXPECTED_BUNDLE_HASH): raise RemoteAbort('CODE_CHANGED')
    module = sys.modules.get('app.real_runner')
    if loaded is None and (module is not None or globals().get('model') is not None): raise RemoteAbort('RESTART_REQUIRED')
    if globals().get('model') is not None: raise RemoteAbort('MODEL_ALREADY_LOADED')
    with (Path('/content') / PROBE_NAME).open('xb') as probe_file:
        probe_file.write(PROBE_BYTES)
    print('__NT_PREFLIGHT_OK__')
except RemoteAbort as exc:
    print('__NT_PREFLIGHT_ERROR__' + str(exc))
except Exception:
    print('__NT_PREFLIGHT_ERROR__PREFLIGHT_FAILED')
'''


def cleanup_probe_program(probe_name, probe_bytes):
    if not re.fullmatch(r'\.novel-translate-probe-[0-9a-f]{32}', probe_name):
        raise ColabError('Invalid content-root probe name.')
    return f'''from pathlib import Path
path = Path('/content') / {probe_name!r}
if path.exists():
    if path.read_bytes() != {probe_bytes!r}: raise RuntimeError('probe changed')
    path.unlink()
print('__NT_PROBE_CLEANED__')
'''


def run_program(job_id, manifest_hash, hashes, bundle_hash, limit):
    limit_value = 'None' if limit is None else str(limit)
    manifest_path = 'jobs/' + job_id + '/run_manifest.json'
    return f'''import hashlib, json, sys
from pathlib import Path
EXPECTED_HASHES = {hashes!r}
EXPECTED_BUNDLE_HASH = {bundle_hash!r}
EXPECTED_MANIFEST_HASH = {manifest_hash!r}
JOB_ID = {job_id!r}
MANIFEST_RELATIVE = {manifest_path!r}
LIMIT = {limit_value}
REPO = Path('/content/novel-translate-code')
class RemoteAbort(Exception): pass
try:
    for name, expected in EXPECTED_HASHES.items():
        path = REPO / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RemoteAbort('SOURCE_HASH_MISMATCH')
    loaded = globals().get('NOVEL_TRANSLATE_SOURCE_BUNDLE_HASH')
    if loaded not in (None, EXPECTED_BUNDLE_HASH): raise RemoteAbort('CODE_CHANGED')
    if loaded is None and ('app.real_runner' in sys.modules or globals().get('model') is not None):
        raise RemoteAbort('RESTART_REQUIRED')
    sys.path.insert(0, str(REPO))
    from app import bundles, real_bundles
    from app.real_runner import run_manifest, huggingface_generate
    manifest_raw = (REPO / MANIFEST_RELATIVE).read_bytes()
    if len(manifest_raw) > bundles.MAX_BYTES or hashlib.sha256(manifest_raw).hexdigest() != EXPECTED_MANIFEST_HASH:
        raise RemoteAbort('MANIFEST_HASH_MISMATCH')
    manifest = bundles.load_json(manifest_raw)
    real_bundles.validate_manifest(manifest)
    if manifest.get('job_id') != JOB_ID: raise RemoteAbort('WRONG_JOB')
    globals()['NOVEL_TRANSLATE_SOURCE_BUNDLE_HASH'] = EXPECTED_BUNDLE_HASH
    drive = Path('/content/drive/MyDrive')
    if not drive.is_dir(): raise RemoteAbort('DRIVE_NOT_MOUNTED')
    root = drive / 'novel-batch' / JOB_ID
    root.mkdir(parents=True, exist_ok=True)
    saved_manifest = root / 'manifest.json'
    if saved_manifest.exists():
        if saved_manifest.stat().st_size > bundles.MAX_BYTES or saved_manifest.read_bytes() != manifest_raw:
            raise RemoteAbort('DRIVE_MANIFEST_MISMATCH')
    else:
        bundles.atomic_write(saved_manifest, manifest_raw)
    result = run_manifest(manifest, root / 'results', huggingface_generate, limit=LIMIT)
    print('__NT_RUN_OK__' + json.dumps(result, separators=(',', ':')))
except RemoteAbort as exc:
    print('__NT_RUN_ERROR__' + str(exc))
except Exception:
    print('__NT_RUN_ERROR__RUNNER_FAILED')
'''


def _outputs_text(outputs):
    return '\n'.join(item.get('text', '') for item in outputs if item.get('output_type') == 'stream')


def _marker(outputs, prefix):
    for line in _outputs_text(outputs).splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return None


def collect_results(api, store, manifest, job_id, chunk_ids=None, missing_out=None):
    expected = ({chunk['chunk_id'] for chunk in manifest['chunks']} if chunk_ids is None
                else set(chunk_ids))
    counts = {'imported': 0, 'duplicate': 0, 'rejected': 0, 'missing': 0, 'unavailable': 0}
    valid_ids = []
    for chunk_id in sorted(expected):
        # Manifest validation guarantees UUID IDs; still enforce before path construction.
        try:
            if type(chunk_id) is not str or str(uuid.UUID(chunk_id)) != chunk_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            counts['rejected'] += 1
            continue
        valid_ids.append(chunk_id)

    if not valid_ids:
        return counts
    results_dir = f'drive/MyDrive/novel-batch/{job_id}/results'
    try:
        directory = api.content(results_dir)
    except Exception:
        counts['unavailable'] += 1
        return counts
    if directory is None:
        missing_ids = valid_ids
        names = {}
    else:
        if (type(directory) is not dict or directory.get('type') != 'directory'
                or type(directory.get('content')) is not list):
            counts['unavailable'] += 1
            return counts
        names = {}
        for entry in directory['content']:
            if (type(entry) is not dict or type(entry.get('name')) is not str
                    or not entry['name'] or entry['name'] in ('.', '..')
                    or any(char in entry['name'] for char in ('/', '\\', '\x00'))
                    or entry.get('type') not in ('file', 'directory')
                    or entry['name'] in names):
                counts['unavailable'] += 1
                return counts
            names[entry['name']] = entry['type']
        expected_names = {chunk_id + '.json' for chunk_id in valid_ids}
        if any(names.get(name) == 'directory' for name in expected_names):
            counts['unavailable'] += 1
            return counts
        missing_ids = [chunk_id for chunk_id in valid_ids if chunk_id + '.json' not in names]

    for chunk_id in missing_ids:
        counts['missing'] += 1
        if missing_out is not None:
            missing_out.append(chunk_id)
    if directory is None:
        return counts

    for chunk_id in valid_ids:
        if names.get(chunk_id + '.json') != 'file':
            continue
        path = f'{results_dir}/{chunk_id}.json'
        try:
            raw = api.read_file(path)
        except TimeoutError:
            counts['unavailable'] += 1
            break
        except Exception:
            counts['unavailable'] += 1
            continue
        if raw is None:
            counts['missing'] += 1
            if missing_out is not None:
                missing_out.append(chunk_id)
            continue
        try:
            payload = bundles.load_json(raw)
            result = real.validate_result(payload, manifest)
            if result['chunk_id'] != chunk_id or result['job_id'] != job_id:
                raise DomainError('Remote result identity mismatch.')
            status = store.import_real_result(raw)
            if status not in ('imported', 'duplicate'):
                counts['rejected'] += 1
            else:
                counts[status] += 1
        except Exception:
            counts['rejected'] += 1
    return counts


def seed_local_results(api, store, manifest, job_id, missing_ids, raw_manifest):
    """Copy already-imported valid results to Drive before the file runner resumes."""
    local = {item['chunk']['chunk_id']: item['result'] for item in store.get_real_job(job_id)['chunks']}
    seed_ids = [chunk_id for chunk_id in missing_ids if local.get(chunk_id) is not None]
    if not seed_ids:
        return 0
    root = 'drive/MyDrive/novel-batch/' + job_id
    manifest_path = root + '/manifest.json'
    saved_manifest = api.read_file(manifest_path)
    if saved_manifest is not None and saved_manifest != raw_manifest:
        raise ColabError('Drive manifest differs from the local immutable job.')
    if saved_manifest is None:
        api.ensure_directory('drive/MyDrive/novel-batch')
        api.ensure_directory(root)
        api.put_file(manifest_path, raw_manifest)
    results_dir = root + '/results'
    api.ensure_directory(results_dir)
    seeded = 0
    for chunk_id in seed_ids:
        try:
            if str(uuid.UUID(chunk_id)) != chunk_id:
                raise ValueError
            payload = real.validate_result(local[chunk_id], manifest)
            if payload['job_id'] != job_id or payload['chunk_id'] != chunk_id:
                raise ValueError
            raw = real.canonical_bytes(payload)
        except Exception:
            raise ColabError('A local completed result failed validation before Drive seeding.') from None
        path = results_dir + '/' + chunk_id + '.json'
        existing = api.read_file(path)
        if existing is not None:
            try:
                remote = real.validate_result(bundles.load_json(existing), manifest)
            except Exception:
                raise ColabError('An existing Drive checkpoint is invalid; it was left untouched.') from None
            if remote['checksum'] != payload['checksum']:
                raise ColabError('An existing Drive checkpoint conflicts with the local result; it was left untouched.')
            continue
        api.put_file(path, raw)
        seeded += 1
    return seeded


def _load_alias(data_dir, alias):
    from colab_cli.state import StateStore
    path = Path(data_dir) / 'colab-cli' / 'sessions.json'
    session = StateStore(str(path)).get(alias)
    if session is None:
        raise ColabError('Registered session alias was not found; register the existing kernel first.')
    return session


def _colab_client(data_dir, deadline=None):
    import logging
    logging.disable(logging.CRITICAL)
    from colab_cli.auth import PUBLIC_SCOPES, TOKEN_CONFIG_PATH
    from colab_cli.client import Client, Prod
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials
    token_path = Path(TOKEN_CONFIG_PATH)
    if not token_path.is_file():
        raise ColabError('Colab CLI authentication is unavailable; authenticate the existing CLI session first.')
    try:
        credentials = Credentials.from_authorized_user_file(str(token_path), PUBLIC_SCOPES)
    except Exception as exc:
        raise ColabError('Colab CLI authentication file is invalid (' + type(exc).__name__ + ').') from None
    if not credentials.valid:
        try:
            if not credentials.refresh_token:
                raise ValueError
            remaining = HTTP_TIMEOUT if deadline is None else min(HTTP_TIMEOUT, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError
            credentials.refresh(Request(timeout=remaining))
        except Exception:
            raise ColabError('Colab CLI authentication could not be refreshed; reauthenticate with the existing CLI.') from None
    transport = AuthorizedSession(credentials)
    original_request = transport.request
    def bounded_request(method, url, **kwargs):
        timeout = HTTP_TIMEOUT
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Colab wall-time budget expired.')
            timeout = min(timeout, remaining)
        kwargs.setdefault('timeout', timeout)
        return original_request(method, url, **kwargs)
    transport.request = bounded_request
    return Client(Prod(), transport)


def _discover_target(data_dir, alias, deadline=None):
    session = _load_alias(data_dir, alias)
    client = _colab_client(data_dir, deadline)
    try:
        assignments = client.list_assignments()
    except Exception as exc:
        raise ColabError('Could not verify Colab assignments (' + type(exc).__name__ + ').') from None
    matching = [a for a in assignments if _field(a, 'endpoint') == session.endpoint]
    if len(matching) != 1:
        raise ColabError('Alias must match exactly one active Colab assignment.')
    assignment = matching[0]
    if (_field(_field(assignment, 'accelerator'), 'name', _field(assignment, 'accelerator')) != 'T4' or
            _field(_field(assignment, 'variant'), 'name', _field(assignment, 'variant')) != 'GPU'):
        raise ColabError('Alias does not point to an existing T4 GPU assignment.')
    proxy = assignment.runtime_proxy_info
    session.token, session.url = proxy.token, proxy.url
    api = JupyterAPI(session)
    api.deadline = deadline
    try:
        verify_target(session, assignments, api.sessions(), api.kernels())
    except Exception as exc:
        api.transport.close()
        if isinstance(exc, ColabError):
            raise
        raise ColabError('Could not verify the registered notebook (' + type(exc).__name__ + ').') from None
    return session, client, assignments, api


def _prepare_remote(api, manifest, raw_manifest, limit):
    sources, hashes, bundle_hash = source_bundle()
    code_root = 'novel-translate-code'
    api.ensure_directory(code_root)
    api.ensure_directory(code_root + '/app')
    api.ensure_directory(code_root + '/jobs')
    job_path = code_root + '/jobs/' + manifest['job_id']
    api.ensure_directory(job_path)
    for name, raw in sources.items():
        api.put_file(code_root + '/' + name, raw)
    manifest_hash = hashlib.sha256(raw_manifest).hexdigest()
    api.put_file(job_path + '/run_manifest.json', raw_manifest)
    return hashes, bundle_hash, manifest_hash


def _runtime_result(outputs, prefix, action):
    error = _marker(outputs, prefix + '_ERROR__')
    if error:
        code = error if error in SAFE_REMOTE_CODES else 'REMOTE_ERROR'
        raise ColabError(action + ' failed remotely (' + code + ').')
    success = _marker(outputs, prefix + '_OK__')
    if success is None:
        raise ColabError(action + ' returned no completion marker.')
    return success


def _safe_remote_code(exc, fallback):
    message = str(exc)
    if message in SAFE_REMOTE_CODES:
        return message
    match = re.search(r'\(([A-Z][A-Z0-9_]*)\)', message)
    return match.group(1) if match and match.group(1) in SAFE_REMOTE_CODES else fallback


def run(args):
    store = Store(args.data_dir)
    manifest = store.get_real_manifest(args.job_id)
    if manifest['job_id'] != args.job_id or manifest['snapshot']['model_id'] != real.QWEN35:
        raise ColabError('Job identity or pinned Qwen3.5 model does not match.')
    raw_manifest = real.canonical_bytes(manifest)
    if len(raw_manifest) > bundles.MAX_BYTES:
        raise ColabError('Manifest exceeds the transfer limit.')
    if args.dry_run:
        print(json.dumps({'job_id': args.job_id, 'session': args.session, 'chunks': len(manifest['chunks']),
                          'limit': args.limit, 'drive_results': f'MyDrive/novel-batch/{args.job_id}/results',
                          'dry_run': True}, separators=(',', ':')))
        return 0

    deadline = time.monotonic() + args.timeout
    lock_dir = Path(args.data_dir) / 'colab-cli' / 'locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(lock_dir, 0o700)
    except OSError:
        pass
    registered = _load_alias(args.data_dir, args.session)
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', registered.kernel_id or ''):
        raise ColabError('Registered kernel ID is invalid.')
    lock_path = lock_dir / (registered.kernel_id + '.lock')
    lock_stream = lock_path.open('a+b')
    try:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_stream.close()
        raise ColabError('Another local process already owns this registered kernel.') from None
    try:
        session, client, assignments, api = _discover_target(args.data_dir, args.session, deadline)
    except BaseException:
        lock_stream.close()
        raise
    runtime = None
    remote_state = 'not_started'
    remote_error = None
    counts = {'imported': 0, 'duplicate': 0, 'rejected': 0, 'missing': 0,
              'unavailable': 0, 'seeded': 0}
    try:
        if args.restart_kernel:
            verify_target(session, assignments, api.sessions(), api.kernels())
            api.restart(session.kernel_id)
            assignments = client.list_assignments()
            matches = [a for a in assignments if _field(a, 'endpoint') == session.endpoint]
            if len(matches) != 1:
                raise ColabError('Restarted alias no longer matches one active assignment.')
            proxy = matches[0].runtime_proxy_info
            if session.token != proxy.token or session.url != proxy.url:
                api.transport.close()
                session.token, session.url = proxy.token, proxy.url
                api = JupyterAPI(session)
                api.deadline = deadline
            verify_target(session, assignments, api.sessions(), api.kernels())
        from colab_cli.runtime import ColabRuntime
        runtime_args = {'kernel_id': session.kernel_id}
        if session.session_id:
            runtime_args['session_id'] = session.session_id
        runtime = ColabRuntime(session.url, session.token, **runtime_args)
        sources, hashes, bundle_hash = source_bundle()
        probe_name = '.novel-translate-probe-' + uuid.uuid4().hex
        probe_bytes = uuid.uuid4().hex.encode('ascii')
        preflight = runtime.execute_code(preflight_program(hashes, bundle_hash, probe_name, probe_bytes),
                                         timeout=min(HTTP_TIMEOUT, max(1, deadline-time.monotonic())))
        _runtime_result(preflight, '__NT_PREFLIGHT', 'Remote preflight')
        detected = False
        try:
            api.detect_contents_root(probe_name, probe_bytes)
            detected = True
        finally:
            try:
                cleanup = runtime.execute_code(cleanup_probe_program(probe_name, probe_bytes),
                                               timeout=min(HTTP_TIMEOUT, max(1, deadline-time.monotonic())))
                if _marker(cleanup, '__NT_PROBE_CLEANED__') is None and detected:
                    raise ColabError('CONTENT_PROBE_CLEANUP_FAILED')
            except Exception:
                if detected:
                    raise ColabError('CONTENT_PROBE_CLEANUP_FAILED') from None
        remote_state = 'preflight_ok'
        initial_missing = []
        initial = collect_results(api, store, manifest, args.job_id, missing_out=initial_missing)
        for key in ('imported', 'duplicate', 'rejected', 'unavailable'):
            counts[key] += initial[key]
        if initial['rejected'] or initial['unavailable']:
            remote_state, remote_error = 'failed', 'RESULT_COLLECTION_FAILED'
        else:
            counts['seeded'] = seed_local_results(api, store, manifest, args.job_id,
                                                   initial_missing, raw_manifest)
            hashes, bundle_hash, manifest_hash = _prepare_remote(api, manifest, raw_manifest, args.limit)
            job = store.get_real_job(args.job_id)
            pending = [item['chunk']['chunk_id'] for item in job['chunks'] if item['result'] is None]
            requested = len(pending) if args.limit is None else min(args.limit, len(pending))
            remote_state = 'completed'
            for chunk_id in pending[:requested]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    remote_state, remote_error = 'timed_out', 'REMOTE_TIMEOUT'
                    break
                code = run_program(args.job_id, manifest_hash, hashes, bundle_hash, 1)
                try:
                    outputs = runtime.execute_code(code, timeout=max(1, remaining))
                    _runtime_result(outputs, '__NT_RUN', 'Remote runner')
                except TimeoutError:
                    remote_state, remote_error = 'timed_out', 'REMOTE_TIMEOUT'
                    imported = collect_results(api, store, manifest, args.job_id, [chunk_id])
                    for key in ('imported', 'duplicate', 'rejected', 'unavailable'):
                        counts[key] += imported[key]
                    break
                except ColabError as exc:
                    remote_state, remote_error = 'failed', _safe_remote_code(exc, 'REMOTE_RUN_FAILED')
                    imported = collect_results(api, store, manifest, args.job_id, [chunk_id])
                    for key in ('imported', 'duplicate', 'rejected', 'unavailable'):
                        counts[key] += imported[key]
                    break
                except Exception:
                    remote_state, remote_error = 'failed', 'REMOTE_RUN_FAILED'
                    imported = collect_results(api, store, manifest, args.job_id, [chunk_id])
                    for key in ('imported', 'duplicate', 'rejected', 'unavailable'):
                        counts[key] += imported[key]
                    break
                imported = collect_results(api, store, manifest, args.job_id, [chunk_id])
                for key in ('imported', 'duplicate', 'rejected', 'unavailable'):
                    counts[key] += imported[key]
                if imported['rejected'] or imported['unavailable'] or imported['missing']:
                    remote_state, remote_error = 'failed', 'RESULT_COLLECTION_FAILED'
                    break
    except ColabError as exc:
        remote_state, remote_error = 'failed', _safe_remote_code(exc, 'LOCAL_OR_REMOTE_ERROR')
    except TimeoutError:
        remote_state, remote_error = 'timed_out', 'REMOTE_TIMEOUT'
    except Exception:
        remote_state, remote_error = 'failed', 'LOCAL_OR_REMOTE_ERROR'
    finally:
        if runtime is not None:
            try:
                runtime.stop()  # Disconnect only; never shuts down the Colab kernel.
            except Exception:
                pass

    try:
        final_job = store.get_real_job(args.job_id)
        counts['missing'] = sum(item['result'] is None for item in final_job['chunks'])
    finally:
        try:
            api.transport.close()
        finally:
            lock_stream.close()
    print(json.dumps({'job_id': args.job_id, 'remote': remote_state, 'error_type': remote_error,
                      **counts}, separators=(',', ':')))
    return 0 if remote_state == 'completed' and counts['rejected'] == 0 and counts['unavailable'] == 0 else 1


def _positive(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a finite positive number') from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--session', required=True, help='Registered existing Colab kernel alias')
    parser.add_argument('--limit', type=int, help='Stop after this many newly completed chunks')
    parser.add_argument('--timeout', type=_positive, default=1800.0)
    parser.add_argument('--restart-kernel', action='store_true', help='Restart only the verified idle target kernel')
    parser.add_argument('--dry-run', action='store_true', help='Validate local job without OAuth or Colab requests')
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    try:
        return run(args)
    except Exception as exc:
        code = 'TARGET_OR_AUTH_FAILED' if isinstance(exc, ColabError) else 'LOCAL_VALIDATION_FAILED'
        print(json.dumps({'action': 'Colab batch stopped', 'error_type': code}, separators=(',', ':')), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
