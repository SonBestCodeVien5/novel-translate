import json

import pytest

from app.bundles import DomainError
from app.core import Store
from scripts.prepare_reading_sample import prepare


def library(tmp_path):
    store = Store(tmp_path)
    chapters = [{'title': 'Cover image', 'text': 'https://example.test/cover.jpg\n'},
                {'title': 'Information', 'text': 'Source information.\n'},
                {'title': 'Prologue', 'text': 'Opening story.\n'}]
    chapters += [{'title': f'Chapter {n}', 'text': f'Story {n}.\n'} for n in range(1, 12)]
    raw = ''.join(ch['text'] for ch in chapters).encode()
    book_id = store.import_txt(raw, 'A book', chapters, 'zh', 'vi')
    return store, book_id


def test_sample_archives_front_matter_and_is_idempotent(tmp_path):
    store, book_id = library(tmp_path)
    original = store.book_chapters(book_id)
    result = prepare(store, book_id, 2, 10)
    sample = store.get_book(result['book_id'])
    assert [chapter['title'] for chapter in sample['chapters']] == [
        'Prologue', *[f'Chapter {n}' for n in range(1, 10)]]
    archive = json.loads((tmp_path / result['archive']).read_text())
    assert [row['title'] for row in archive['skipped']] == ['Cover image', 'Information']
    assert [row['sample_ordinal'] for row in archive['selected']] == list(range(10))
    assert store.book_chapters(book_id) == original
    assert prepare(store, book_id, 2, 10) == result
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM books').fetchone()[0] == 2


@pytest.mark.parametrize(('skip', 'count'), [(0, 0), (-1, 2), (2, 20)])
def test_invalid_range_does_not_create_sample(tmp_path, skip, count):
    store, book_id = library(tmp_path)
    with pytest.raises(DomainError):
        prepare(store, book_id, skip, count)
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM books').fetchone()[0] == 1


def test_archive_collision_does_not_overwrite_or_create_book(tmp_path):
    store, book_id = library(tmp_path)
    # Build the expected sample once to discover its id, then alter its archive.
    result = prepare(store, book_id, 2, 10)
    archive_path = tmp_path / result['archive']
    archive_path.write_text('{"other":true}')
    before = archive_path.read_bytes()
    with pytest.raises(DomainError, match='refusing to overwrite'):
        prepare(store, book_id, 2, 10)
    assert archive_path.read_bytes() == before
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM books').fetchone()[0] == 2
