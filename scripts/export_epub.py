#!/usr/bin/env python3
"""Export an approved real translation job as an EPUB."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bundles import DomainError
from app.core import Store


def write_new(path, raw):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise DomainError('Output already exists; choose a new path.')
    if not path.parent.is_dir():
        raise DomainError('Output directory does not exist.')
    descriptor, temporary = tempfile.mkstemp(prefix='.novel-epub-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = Store(args.data_dir).export_real_epub(args.job_id)
        print(write_new(args.output, raw))
        return 0
    except (DomainError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
