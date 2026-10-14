#!/usr/bin/env python3
"""Import an EPUB into the local Store, without creating a translation job."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Store, DomainError
from app.epub import MAX_RAW


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('epub', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--title')
    args = parser.parse_args()
    try:
        with args.epub.open('rb') as file:
            raw = file.read(MAX_RAW + 1)
        store = Store(args.data_dir)
        book_id = store.import_epub(raw, args.title)
        with store._connect() as db:
            chapters = db.execute('SELECT COUNT(*) FROM chapters WHERE book_id=?', (book_id,)).fetchone()[0]
            chunks = db.execute('SELECT COUNT(*) FROM chunks c JOIN chapters ch ON ch.id=c.chapter_id WHERE ch.book_id=?', (book_id,)).fetchone()[0]
        print(json.dumps({'book_id': book_id, 'chapters': chapters, 'chunks': chunks,
                          'source_unit_rule': 'one nonempty XHTML spine item per chapter'}))
        return 0
    except (DomainError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
