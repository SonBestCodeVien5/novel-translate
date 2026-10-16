#!/usr/bin/env python3
"""Run/resume the existing Qwen3.5 P0 Colab kernel from the local CLI."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.p0.build_notebook import QWEN35 as MODEL, QWEN35_REVISION as REVISION

STATE_FILE = ROOT / 'data/colab-cli/sessions.json'
PINS = {'transformers': '5.3.0', 'accelerate': '1.11.0', 'bitsandbytes': '0.48.2'}


def _is_qwen35_notebook(item):
    filename = Path(item.get('path') or item.get('name') or '').name
    return re.fullmatch(r'p0_qwen35_benchmark(?:-[a-zA-Z0-9_-]+)?\.ipynb', filename) is not None


def verify_target(session, assignments, sessions, kernels):
    assignment = [a for a in assignments if a.endpoint == session.endpoint]
    if (len(assignment) != 1 or assignment[0].accelerator.name != 'T4'
            or assignment[0].variant.name != 'GPU'):
        raise RuntimeError('Alias must resolve to exactly one active T4 GPU assignment.')
    kernels_by_id = {item['id']: item for item in kernels}
    matches = [item for item in sessions if _is_qwen35_notebook(item)]
    if len(matches) != 1:
        raise RuntimeError('Could not identify exactly one Qwen3.5 benchmark notebook session.')
    kernel_id = matches[0].get('kernel', {}).get('id')
    kernel = kernels_by_id.get(kernel_id)
    if not kernel or session.kernel_id != kernel_id:
        raise RuntimeError('Notebook session does not match the registered Colab kernel alias.')
    if kernel.get('execution_state') != 'idle':
        raise RuntimeError('Colab kernel is busy; wait for it to become idle before running.')
    session.kernel_id = kernel_id
    return session


def bootstrap_program(limit):
    from benchmarks.p0.build_notebook import bootstrap_source

    notebook = json.loads((ROOT / 'notebooks/p0_qwen35_benchmark.ipynb').read_text(encoding='utf-8'))
    progress = ''.join(notebook['cells'][7]['source'])
    limit_source = 'None' if limit is None else str(limit)
    return '\n'.join((
        bootstrap_source(),
        "import importlib, json, os, sys",
        "from pathlib import Path",
        "from google.colab import drive",
        "if not Path('/content/drive/MyDrive').is_dir(): raise RuntimeError('Drive is not mounted. Authenticate Drive in the existing Colab notebook, then rerun this command.')",
        "if globals().get('MODEL', " + repr(MODEL) + ") != " + repr(MODEL) + " or globals().get('REVISION', " + repr(REVISION) + ") != " + repr(REVISION) + ": raise RuntimeError('Kernel contains a different model/revision configuration.')",
        "if globals().get('model') is not None: raise RuntimeError('A model is already loaded in this kernel; refusing to load a second copy.')",
        "import torch",
        "if not torch.cuda.is_available(): raise RuntimeError('The attached Colab kernel has no CUDA GPU.')",
        "sys.path.insert(0, str(REPO))",
        "from app.bundles import digest, load_json",
        "from benchmarks.p0 import runner",
        "runner = importlib.reload(runner)",
        "CONFIG, apply_model_profile, validate_corpus = runner.CONFIG, runner.apply_model_profile, runner.validate_corpus",
        f"CORPUS = Path('/content/drive/MyDrive/p0/corpus.json')",
        f"MODEL = {MODEL!r}",
        f"REVISION = {REVISION!r}",
        f"LIMIT = {limit_source}",
        "apply_model_profile(MODEL)",
        "if not CORPUS.is_file(): raise FileNotFoundError('Expected corpus at /content/drive/MyDrive/p0/corpus.json.')",
        "corpus = validate_corpus(load_json(CORPUS.read_bytes()))",
        "snapshot = digest({'corpus': corpus, 'model': MODEL, 'revision': REVISION, 'config': CONFIG})",
        "OUTPUT = Path('/content/drive/MyDrive/p0/runs') / (MODEL.split('/')[-1] + '-' + snapshot)",
        "print('P0 run:', corpus.get('mode', 'full'), 'chapters:', len(corpus['chapters']), 'output:', OUTPUT, flush=True)",
        progress,
    ))


def dependency_program(allow_loaded_model=False):
    return """import importlib.metadata, subprocess, sys
pins = %r
from pathlib import Path
import torch
if not Path('/content/drive/MyDrive').is_dir(): raise RuntimeError('Drive is not mounted. Authenticate Drive in the existing Colab notebook, then rerun this command.')
if not torch.cuda.is_available(): raise RuntimeError('The attached Colab kernel has no CUDA GPU.')
if globals().get('MODEL', %r) != %r or globals().get('REVISION', %r) != %r: raise RuntimeError('Kernel contains a different model/revision configuration.')
if not %r and globals().get('model') is not None: raise RuntimeError('A model is already loaded in this kernel; use --restart-kernel to clear it first.')
missing = []
for name, version in pins.items():
    try: current = importlib.metadata.distribution(name).version
    except importlib.metadata.PackageNotFoundError: current = None
    if current != version: missing.append(name + '==' + version)
if missing:
    subprocess.run([sys.executable, '-m', 'pip', 'install', *missing], check=True)
    print('P0_DEPENDENCIES_CHANGED', flush=True)
else:
    print('P0_DEPENDENCIES_OK', flush=True)
""" % (PINS, MODEL, MODEL, REVISION, REVISION, allow_loaded_model)


def _outputs_have_error(outputs):
    return next((item for item in outputs if item.get('output_type') == 'error'), None)


def _stream(output):
    if output.get('output_type') == 'stream':
        sys.stdout.write(output.get('text', ''))
        sys.stdout.flush()
    elif output.get('output_type') == 'error':
        print('Remote error: ' + output.get('ename', 'Error') + ': ' + output.get('evalue', ''), file=sys.stderr)


def run(args):
    # Keep the CLI's proxy token file private; it is already Git-ignored under data/.
    STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE_FILE.parent, 0o700)
    if STATE_FILE.exists():
        os.chmod(STATE_FILE, 0o600)
    from colab_cli.common import state
    state.config_path = str(STATE_FILE)
    assignments = state.client.list_assignments()
    session = state.get_session(args.session)
    if session is None:
        raise RuntimeError('Named Colab session was not found; authenticate and register its existing kernel first.')
    import requests
    headers = {'X-Colab-Client-Agent': 'colab-cli',
               'X-Colab-Runtime-Proxy-Token': session.token}
    params = {'colab-runtime-proxy-token': session.token}
    base = session.url.rstrip('/') + '/'
    response = requests.get(urljoin(base, 'api/sessions'), headers=headers, params=params, timeout=20)
    response.raise_for_status()
    sessions = response.json()
    response = requests.get(urljoin(base, 'api/kernels'), headers=headers, params=params, timeout=20)
    response.raise_for_status()
    session = verify_target(session, assignments, sessions, response.json())
    state.store.add(session)
    if STATE_FILE.exists():
        os.chmod(STATE_FILE, 0o600)

    from colab_cli.runtime import ColabRuntime
    runtime = ColabRuntime(session.url, session.token, kernel_id=session.kernel_id,
                           session_id=session.session_id)
    try:
        deps = runtime.execute_code(dependency_program(args.restart_kernel), timeout=300)
        error = _outputs_have_error(deps)
        if error:
            _stream(error)
            raise RuntimeError('Dependency preflight failed; remote execution stopped.')
        changed = any('P0_DEPENDENCIES_CHANGED' in item.get('text', '')
                      for item in deps if item.get('output_type') == 'stream')
        if changed and not args.restart_kernel:
            raise RuntimeError('Pinned packages changed. Rerun with --restart-kernel to restart this existing kernel before model execution.')
        if args.restart_kernel:
            runtime.restart(timeout=120)
        outputs = runtime.execute_code(bootstrap_program(args.limit), output_hook=_stream,
                                       timeout=args.timeout)
        error = _outputs_have_error(outputs)
        if error:
            _stream(error)
            raise RuntimeError('P0 runner failed; inspect the checkpoint and resume only after resolving the reported error.')
    finally:
        runtime.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', default='qwen35-vscode', help='Registered existing Colab session alias')
    parser.add_argument('--limit', type=int, help='Smoke limit; default runs/resumes all remaining chunks')
    parser.add_argument('--timeout', type=float, default=43200, help='Remote execution timeout in seconds')
    parser.add_argument('--restart-kernel', action='store_true', help='Restart the existing kernel before running (required if dependency pins change)')
    parser.add_argument('--dry-run', action='store_true', help='Show the pinned target and local corpus path without connecting')
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.dry_run:
        print(f'{MODEL}@{REVISION}; corpus=/content/drive/MyDrive/p0/corpus.json; limit={args.limit}; session={args.session}')
        return 0
    run(args)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'P0 Colab run stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)
