import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from app.backups import MANIFEST, create_backup, restore_backup
from app.bundles import DomainError, canonical_bytes, fake_result, now
from app.core import Store


class TinyTokenizer:
    chat_template = 'tiny-chat-template-v1'

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        return [ord(char) for message in messages for char in message['content']]


def make_epub():
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OPS/book.opf': b'<package xmlns="http://www.idpf.org/2007/opf"><metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Fixture</dc:title></metadata><manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>',
        'OPS/c.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Small licensed fixture text.</p></body></html>',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED)
    return output.getvalue()


def populated_data(path):
    store = Store(path)
    raw = b'Chapter 1\nShort synthetic source.'
    book = store.import_txt(raw, 'Synthetic TXT', store.preview_txt(raw, 'Synthetic TXT'))
    job = store.create_job(book)
    manifest = store.get_manifest(job)
    store.import_result(canonical_bytes(fake_result(manifest, manifest['chunks'][0])))
    chunk = manifest['chunks'][0]
    store.save_revision(chunk['chunk_id'], 'Approved synthetic edit.', 0,
                        store.get_book(book)['chapters'][0]['chunks'][0]['base_result_hash'])
    from app.real_bundles import MODELS, default_snapshot
    snapshot = default_snapshot('Qwen/Qwen3-4B-Instruct-2507', MODELS['Qwen/Qwen3-4B-Instruct-2507'], TinyTokenizer.chat_template)
    store.save_glossary(book, [{'term': 'dragon', 'translation': 'rồng', 'aliases': [], 'notes': 'fixture'}], 0)
    real_job = store.create_real_job(book, TinyTokenizer(), snapshot)
    from app.real_bundles import make_result, provenance
    real_manifest = store.get_real_manifest(real_job)
    real_chunk = real_manifest['chunks'][0]
    stamp = now()
    result = make_result(real_manifest, real_chunk, {
        'translated_text': 'Machine result.', 'output_tokens': 3, 'finish_reason': 'eos',
        'provenance': provenance(real_manifest)}, stamp, stamp)
    store.import_real_result(canonical_bytes(result))
    store.save_real_revision(real_job, real_chunk['chunk_id'], 'Approved real edit.', 0, result['checksum'], True)
    epub_book = store.import_epub(make_epub())
    return store, book, job, real_job, epub_book


def test_backup_restore_preserves_db_assets_and_excludes_user_directories(tmp_path):
    source = tmp_path / 'source'
    store, book, job, real_job, epub_book = populated_data(source)
    for name in ('colab-cli', 'auth', 'logs', 'backups', 'my-notes'):
        (source / name).mkdir()
        (source / name / 'private.txt').write_text('excluded')
    archive = tmp_path / 'library.zip'
    create_backup(source, archive)
    target = tmp_path / 'restored'
    restore_backup(archive, target)
    restored = Store(target)
    assert restored.export_real_txt(real_job) == store.export_real_txt(real_job)
    assert restored.export_real_txt(real_job).endswith('Approved real edit.')
    assert restored.get_book(book)['chapters'][0]['chunks'][0]['edited_text'] == 'Approved synthetic edit.'
    assert restored.get_manifest(job) == store.get_manifest(job)
    assert restored.get_real_manifest(real_job) == store.get_real_manifest(real_job)
    assert restored.get_glossary(book) == store.get_glossary(book)
    raw_path = sqlite3.connect(target / 'library.sqlite3').execute('SELECT raw_path FROM books WHERE id=?', (epub_book,)).fetchone()[0]
    assert hashlib.sha256((target / raw_path).read_bytes()).hexdigest() == sqlite3.connect(target / 'library.sqlite3').execute('SELECT raw_hash FROM books WHERE id=?', (epub_book,)).fetchone()[0]
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert not any(name.startswith(('auth/', 'logs/', 'backups/', 'colab-cli/', 'my-notes/')) for name in names)


def test_backup_restore_preserves_historical_v1_schema_then_store_migrates_additively(tmp_path):
    source = tmp_path / 'v1-source'
    store = Store(source)
    raw = b'Chapter 1\nHistorical synthetic source.'
    book = store.import_txt(raw, 'Historical v1', store.preview_txt(raw, 'Historical v1'))
    job = store.create_job(book)
    manifest = store.get_manifest(job)
    result = fake_result(manifest, manifest['chunks'][0])
    store.import_result(canonical_bytes(result))
    store.save_revision(manifest['chunks'][0]['chunk_id'], 'Historical manual edit.', 0,
                        result['checksum'])
    connection = sqlite3.connect(source / 'library.sqlite3')
    for table in ('real_revisions', 'real_results', 'real_chunks', 'real_jobs', 'book_glossaries'):
        connection.execute(f'DROP TABLE {table}')
    connection.commit()
    connection.close()

    archive = tmp_path / 'v1.zip'
    create_backup(source, archive)
    target = tmp_path / 'v1-restored'
    restore_backup(archive, target)
    connection = sqlite3.connect(target / 'library.sqlite3')
    assert {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")} == {
        'books', 'chapters', 'chunks', 'jobs', 'results', 'revisions'}
    connection.close()
    migrated = Store(target)
    assert migrated.get_book(book)['chapters'][0]['chunks'][0]['edited_text'] == 'Historical manual edit.'
    assert migrated.export_txt(book).endswith('Historical manual edit.')
    connection = sqlite3.connect(target / 'library.sqlite3')
    assert {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")} == {
        'books', 'chapters', 'chunks', 'jobs', 'results', 'revisions', 'real_jobs',
        'real_chunks', 'real_results', 'real_revisions', 'book_glossaries'}
    connection.close()


def test_backup_rejects_partial_real_job_schema(tmp_path):
    source = tmp_path / 'partial-real'
    populated_data(source)
    connection = sqlite3.connect(source / 'library.sqlite3')
    connection.execute('DROP TABLE real_revisions')
    connection.commit()
    connection.close()
    with pytest.raises(DomainError, match='required app schema'):
        create_backup(source, tmp_path / 'partial.zip')
    assert not (tmp_path / 'partial.zip').exists()


def test_backup_and_restore_refuse_existing_paths_and_nested_output(tmp_path):
    source = tmp_path / 'source'
    populated_data(source)
    existing = tmp_path / 'exists.zip'
    existing.touch()
    with pytest.raises(DomainError):
        create_backup(source, existing)
    with pytest.raises(DomainError):
        create_backup(source, source / 'backup.zip')
    archive = tmp_path / 'backup.zip'
    create_backup(source, archive)
    target = tmp_path / 'restore'
    target.mkdir()
    with pytest.raises(DomainError):
        restore_backup(archive, target)
    assert target.is_dir() and not list(target.iterdir())


def test_backup_snapshots_committed_wal_state(tmp_path):
    source = tmp_path / 'source'
    populated_data(source)
    connection = sqlite3.connect(source / 'library.sqlite3')
    assert connection.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() == 'wal'
    connection.execute("UPDATE books SET title='Committed in WAL'")
    connection.commit()
    archive = tmp_path / 'wal.zip'
    create_backup(source, archive)
    target = tmp_path / 'wal-restored'
    restore_backup(archive, target)
    assert sqlite3.connect(target / 'library.sqlite3').execute('SELECT title FROM books LIMIT 1').fetchone()[0] == 'Committed in WAL'
    connection.close()


def test_corrupt_archive_inventory_or_unsafe_zip_is_rejected_without_target(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    populated_data(source)
    valid = tmp_path / 'valid.zip'
    create_backup(source, valid)
    with zipfile.ZipFile(valid) as zf:
        entries = [(item.filename, zf.read(item.filename), item.compress_type) for item in zf.infolist()]
    cases = []
    bad_hash = [(n, b'broken' if n == 'library.sqlite3' else d, c) for n, d, c in entries]
    cases.append(bad_hash)
    manifest = json.loads(next(d for n, d, _ in entries if n == MANIFEST))
    manifest['version'] = 99
    cases.append([(n, canonical_bytes(manifest) if n == MANIFEST else d, c) for n, d, c in entries])
    manifest['version'] = True
    cases.append([(n, canonical_bytes(manifest) if n == MANIFEST else d, c) for n, d, c in entries])
    cases.append(entries + [entries[-1]])
    traversal = entries + [('../outside.txt', b'x', zipfile.ZIP_STORED)]
    cases.append(traversal)
    cases.append(entries + [('sources//bad', b'x', zipfile.ZIP_STORED)])
    for index, case in enumerate(cases):
        archive = tmp_path / f'bad-{index}.zip'
        with zipfile.ZipFile(archive, 'w') as zf:
            for name, data, compression in case:
                zf.writestr(name, data, compress_type=compression)
        target = tmp_path / f'target-{index}'
        with pytest.raises((DomainError, zipfile.BadZipFile)):
            restore_backup(archive, target)
        assert not target.exists()

    truncated = tmp_path / 'truncated.zip'
    truncated.write_bytes(valid.read_bytes()[:-12])
    with pytest.raises(DomainError):
        restore_backup(truncated, tmp_path / 'truncated-target')

    import app.backups as backups
    monkeypatch_value = backups.MAX_ENTRY
    backups.MAX_ENTRY = 1
    try:
        with pytest.raises(DomainError):
            restore_backup(valid, tmp_path / 'oversized-target')
    finally:
        backups.MAX_ENTRY = monkeypatch_value

    symlink = tmp_path / 'symlink.zip'
    with zipfile.ZipFile(symlink, 'w') as zf:
        info = zipfile.ZipInfo('sources/link')
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, b'backup-manifest.json')
    with pytest.raises(DomainError):
        restore_backup(symlink, tmp_path / 'symlink-target')


def test_backup_holds_writer_lock_and_releases_it_after_failure(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    populated_data(source)
    import app.backups as backups
    original = backups._walk_assets

    def fail_after_lock(_):
        db = sqlite3.connect(source / 'library.sqlite3', timeout=0.05, isolation_level=None)
        with pytest.raises(sqlite3.OperationalError):
            db.execute('BEGIN IMMEDIATE')
        db.close()
        raise DomainError('injected asset failure')

    monkeypatch.setattr(backups, '_walk_assets', fail_after_lock)
    output = tmp_path / 'failed.zip'
    with pytest.raises(DomainError):
        create_backup(source, output)
    assert not output.exists()
    monkeypatch.setattr(backups, '_walk_assets', original)
    connection = sqlite3.connect(source / 'library.sqlite3', timeout=0.1, isolation_level=None)
    connection.execute('BEGIN IMMEDIATE')
    connection.rollback()
    connection.close()

    monkeypatch.setattr(backups.tempfile, 'mkdtemp', lambda **_: (_ for _ in ()).throw(OSError('injected staging failure')))
    with pytest.raises(OSError):
        create_backup(source, tmp_path / 'stage-failure.zip')
    connection = sqlite3.connect(source / 'library.sqlite3', timeout=0.1, isolation_level=None)
    connection.execute('BEGIN IMMEDIATE')
    connection.rollback()
    connection.close()


def test_missing_epub_mapping_and_oversized_manifest_fail_without_publishing(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    populated_data(source)
    connection = sqlite3.connect(source / 'library.sqlite3')
    epub_raw_hash = connection.execute("SELECT raw_hash FROM books WHERE raw_path LIKE '%.epub'").fetchone()[0]
    connection.close()
    (source / 'sources' / f'{epub_raw_hash}.epub-spine-1.mapping.json').unlink()
    output = tmp_path / 'missing-map.zip'
    with pytest.raises(DomainError):
        create_backup(source, output)
    assert not output.exists()

    source = tmp_path / 'txt-only'
    store = Store(source)
    raw = b'synthetic text'
    store.import_txt(raw, 'Synthetic', store.preview_txt(raw, 'Synthetic'))
    import app.backups as backups
    original = backups.canonical_bytes

    def oversized(value):
        if type(value) is dict and set(value) == {'version', 'entries'}:
            return b'x' * (backups.MAX_BYTES + 1)
        return original(value)

    monkeypatch.setattr(backups, 'canonical_bytes', oversized)
    output = tmp_path / 'oversized-manifest.zip'
    with pytest.raises(DomainError):
        create_backup(source, output)
    assert not output.exists()
