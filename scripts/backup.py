#!/usr/bin/env python3
"""Create or safely restore a local novel-translate backup."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.backups import create_backup, restore_backup
from app.bundles import DomainError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    create.add_argument('--data-dir', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--archive', type=Path, required=True)
    restore.add_argument('--target', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            path = create_backup(args.data_dir, args.output)
        else:
            path = restore_backup(args.archive, args.target)
        print(path)
        return 0
    except (DomainError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
