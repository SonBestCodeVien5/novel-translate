#!/usr/bin/env python3
"""Export and inspect local real-provider batches; import one result at a time."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bundles import DomainError, MAX_BYTES, atomic_write, canonical_bytes
from app.core import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--data-dir', type=Path, default=Path('data'))
    export.add_argument('--book-id', required=True)
    export.add_argument('--model', required=True)
    export.add_argument('--revision', required=True)
    export.add_argument('--output', type=Path, required=True)
    importer = commands.add_parser('import')
    importer.add_argument('--data-dir', type=Path, default=Path('data'))
    importer.add_argument('--result', type=Path, required=True)
    status = commands.add_parser('status')
    status.add_argument('--data-dir', type=Path, default=Path('data'))
    status.add_argument('--job-id', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'export':
            if args.output.exists():
                raise DomainError('Output already exists; choose a new path.')
            from app.real_bundles import MODELS, default_snapshot, load_tokenizer
            if MODELS.get(args.model) != args.revision:
                raise DomainError('Choose a supported model and its pinned revision.')
            try:
                tokenizer, resolved_commit = load_tokenizer(args.model, args.revision)
            except ImportError as exc:
                version = '5.3.0' if args.model == 'Qwen/Qwen3.5-4B' else '4.57.3'
                raise DomainError(f'Install transformers=={version} to load the pinned tokenizer.') from exc
            if resolved_commit != args.revision:
                raise DomainError('Loaded tokenizer revision does not match the requested pin.')
            snap = default_snapshot(args.model, args.revision, tokenizer.chat_template)
            store = Store(args.data_dir)
            job_id = store.create_real_job(args.book_id, tokenizer, snap)
            raw = canonical_bytes(store.get_real_manifest(job_id))
            if len(raw) > MAX_BYTES:
                raise DomainError('Manifest exceeds the size limit.')
            atomic_write(args.output, raw)
            print(json.dumps({'job_id': job_id, 'output': str(args.output)}))
        elif args.command == 'import':
            if args.result.stat().st_size > MAX_BYTES:
                raise DomainError('Result exceeds the size limit.')
            with args.result.open('rb') as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise DomainError('Result exceeds the size limit.')
            store = Store(args.data_dir)
            print(store.import_real_result(raw))
        else:
            store = Store(args.data_dir)
            job = store.get_real_job(args.job_id)
            print(json.dumps({key: job[key] for key in ('id', 'status', 'completed', 'total')}))
        return 0
    except (DomainError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
