#!/usr/bin/env python3
"""Create a separate TXT book from a contiguous range of an imported book."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bundles import DomainError, atomic_write, canonical_bytes, digest
from app.core import Store


def prepare(store, book_id, skip_front_matter, chapters_count):
    if type(skip_front_matter) is not int or skip_front_matter < 0:
        raise DomainError('Front-matter count must be zero or greater.')
    if type(chapters_count) is not int or chapters_count < 1:
        raise DomainError('Chapter count must be positive.')
    with store._connect() as db:
        book = Store._book(db, book_id)
        metadata = dict(book)
    all_chapters = store.book_chapters(book_id)
    selected = all_chapters[skip_front_matter:skip_front_matter + chapters_count]
    if len(selected) != chapters_count or any(
            row['ordinal'] != skip_front_matter + index for index, row in enumerate(selected)):
        raise DomainError('Source book does not contain the requested contiguous chapter range.')

    skipped = [store.get_raw_chapter(book_id, row['ordinal']) for row in all_chapters[:skip_front_matter]]
    source_raw_path = store.data_dir / metadata['raw_path']
    source_raw = source_raw_path.read_bytes()
    if hashlib.sha256(source_raw).hexdigest() != metadata['raw_hash']:
        raise DomainError('Stored source integrity error.')
    selected_chapters = [store.get_raw_chapter(book_id, row['ordinal']) for row in selected]
    source = ''.join(row['source_text'] for row in selected_chapters)
    raw = source.encode('utf-8')
    sample_title = f"{metadata['title']} · {chapters_count} chương đầu (từ {selected[0]['title']})"[:300]
    chapter_payload = [{'title': row['title'], 'text': row['source_text']} for row in selected_chapters]

    # Match Store.import_txt's key so a conflicting archive is detected before any DB write.
    raw_hash = hashlib.sha256(raw).hexdigest()
    import_key = digest({'raw_hash': raw_hash, 'import_version': 1, 'normalization': 'utf8-newlines-1',
                         'chapters': chapter_payload, 'source_language': metadata['source_language'],
                         'target_language': metadata['target_language']})
    with store._connect() as db:
        existing = db.execute('SELECT id FROM books WHERE import_key=?', (import_key,)).fetchone()
    sample_id = existing['id'] if existing else None
    archive_path = None if sample_id is None else store.data_dir / 'sources' / f'reading-sample-{sample_id}.json'
    if archive_path and archive_path.exists():
        old = archive_path.read_bytes()
        try:
            old_data = json.loads(old)
        except (UnicodeError, json.JSONDecodeError):
            old_data = None
        if old_data != _archive(book_id, source_raw, skipped, selected, sample_id):
            raise DomainError('A different reading-sample archive already exists; refusing to overwrite it.')

    sample_id = store.import_txt(raw, sample_title, chapter_payload,
                                 metadata['source_language'], metadata['target_language'])
    archive_path = store.data_dir / 'sources' / f'reading-sample-{sample_id}.json'
    archive = _archive(book_id, source_raw, skipped, selected, sample_id)
    archive_raw = canonical_bytes(archive)
    if archive_path.exists() and archive_path.read_bytes() != archive_raw:
        raise DomainError('A different reading-sample archive already exists; refusing to overwrite it.')
    if not archive_path.exists():
        atomic_write(archive_path, archive_raw)
    return {'book_id': sample_id, 'chapter_count': len(selected), 'archived_count': len(skipped),
            'archive': str(archive_path)}


def _archive(book_id, raw, skipped, selected, sample_id):
    return {'schema_version': 1, 'source_book_id': book_id,
            'source_raw_sha256': hashlib.sha256(raw).hexdigest(),
            'sample_book_id': sample_id,
            'skipped': [{'ordinal': row['ordinal'], 'title': row['title'], 'text': row['source_text'],
                         'source_sha256': hashlib.sha256(row['source_text'].encode('utf-8')).hexdigest()}
                        for row in skipped],
            'selected': [{'source_ordinal': row['ordinal'], 'sample_ordinal': index,
                          'source_title': row['title']} for index, row in enumerate(selected)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--book-id', required=True)
    parser.add_argument('--skip-front-matter', type=int, required=True)
    parser.add_argument('--chapters', type=int, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(Store(args.data_dir), args.book_id,
                                 args.skip_front_matter, args.chapters), ensure_ascii=False))
        return 0
    except (DomainError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
