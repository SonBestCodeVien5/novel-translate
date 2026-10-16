"""Safe, self-contained backups of the local library and its app-owned assets."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import ctypes
import errno
import shutil
import sqlite3
import stat
import tempfile
import zipfile

from .bundles import (DomainError, MAX_BYTES, canonical_bytes, digest, load_json,
                      text_hash, validate_manifest, validate_result)
from .epub import MAX_RAW as MAX_EPUB_RAW, parse_epub

VERSION = 1
ASSET_DIRS = ('sources', 'batches', 'results', 'rejected', 'real-batches', 'real-results')
BASE_TABLES = {'books', 'chapters', 'chunks', 'jobs', 'results', 'revisions'}
REAL_TABLES = {'real_jobs', 'real_chunks', 'real_results', 'real_revisions'}
OPTIONAL_TABLES = REAL_TABLES | {'book_glossaries'}
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_ENTRY = 512 * 1024 * 1024
MANIFEST = 'backup-manifest.json'


def _fail(message):
    raise DomainError(message)


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def _safe_file(path):
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _walk_assets(root):
    files = []
    for name in ASSET_DIRS:
        directory = root / name
        if not directory.exists() and not directory.is_symlink():
            continue
        if directory.is_symlink() or not directory.is_dir():
            _fail('Unsafe app asset directory.')
        for current, dirs, names in os.walk(directory, followlinks=False):
            base = Path(current)
            for child in dirs:
                p = base / child
                if p.is_symlink():
                    _fail('Symlinks are not allowed in app assets.')
            for child in names:
                p = base / child
                if not _safe_file(p):
                    _fail('Non-regular files are not allowed in app assets.')
                files.append(p)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _inventory(path):
    size = path.stat().st_size
    if size > MAX_ENTRY:
        _fail('A backup entry exceeds the size limit.')
    return {'path': path, 'size': size, 'sha256': _digest(path)}


def _source_lock(db_path):
    if not _safe_file(db_path):
        _fail('library.sqlite3 is missing or unsafe.')
    lock = sqlite3.connect(db_path, timeout=5, isolation_level=None)
    try:
        lock.execute('PRAGMA busy_timeout=5000')
        lock.execute('BEGIN IMMEDIATE')
    except sqlite3.Error as exc:
        lock.close()
        raise DomainError('Could not acquire the library backup lock.') from exc
    return lock


def _validate_db(path, assets):
    uri = path.resolve().as_uri() + '?mode=ro'
    try:
        db = sqlite3.connect(uri, uri=True)
        db.execute('PRAGMA trusted_schema=OFF')
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            _fail('Backup database integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            _fail('Backup database has foreign key errors.')
        objects = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if any(kind in ('trigger', 'view') for kind, _ in objects):
            _fail('Backup database contains unexpected triggers or views.')
        tables = {name for kind, name in objects if kind == 'table'}
        if (not BASE_TABLES <= tables or tables - BASE_TABLES - OPTIONAL_TABLES or
                bool(tables & REAL_TABLES) != (REAL_TABLES <= tables)):
            _fail('Backup database does not have the required app schema.')
        from .real_bundles import validate_manifest as validate_real_manifest, validate_result as validate_real_result
        files = {item['path']: item['file'] for item in assets}
        for book_id, raw_path, raw_hash, source_hash in db.execute('SELECT id,raw_path,raw_hash,source_hash FROM books'):
            rel = _safe_relative(raw_path)
            if rel.parts[0] != 'sources' or raw_path not in files:
                _fail('A referenced source asset is missing from the backup.')
            if _digest(files[raw_path]) != raw_hash:
                _fail('A referenced source asset failed its checksum.')
            if raw_path.lower().endswith('.epub'):
                if files[raw_path].stat().st_size > MAX_EPUB_RAW:
                    _fail('A referenced EPUB exceeds the parser size limit.')
                parsed = parse_epub(files[raw_path].read_bytes())
                mapping_path = f"sources/{raw_hash}.{parsed['parser_version']}.mapping.json"
                if mapping_path not in files or files[mapping_path].read_bytes() != canonical_bytes(parsed):
                    _fail('A referenced EPUB mapping is missing or inconsistent.')
            chapter_text = ''.join(row[0] for row in db.execute(
                'SELECT source_text FROM chapters WHERE book_id=? ORDER BY ordinal', (book_id,)))
            if text_hash(chapter_text) != source_hash:
                _fail('Stored book text failed its checksum.')
        manifests = {}
        job_tables = [('jobs', 'batches')]
        if REAL_TABLES <= tables:
            job_tables.append(('real_jobs', 'real-batches'))
        for table, folder in job_tables:
            for job_id, book_id, manifest, manifest_hash in db.execute(
                    f'SELECT id,book_id,manifest,manifest_hash FROM {table}'):
                value = load_json(manifest.encode('utf-8'))
                (validate_manifest if table == 'jobs' else validate_real_manifest)(value)
                raw = canonical_bytes(value)
                if digest(value) != manifest_hash or value['job_id'] != job_id or value['book_id'] != book_id:
                    _fail('A stored job manifest failed its checksum.')
                manifests[(table, job_id)] = value
                path = f'{folder}/{job_id}.json'
                if path not in files or files[path].stat().st_size > MAX_BYTES or files[path].read_bytes() != raw:
                    _fail('A referenced job batch is missing or inconsistent.')
        result_tables = [('results', 'results')]
        if REAL_TABLES <= tables:
            result_tables.append(('real_results', 'real-results'))
        for table, folder in result_tables:
            for job_id, chunk_id, checksum, payload in db.execute(
                    f'SELECT job_id,chunk_id,checksum,payload FROM {table}'):
                value = load_json(payload.encode('utf-8'))
                if table == 'results':
                    validate_result(value, manifests[('jobs', job_id)])
                else:
                    validate_real_result(value, manifests[('real_jobs', job_id)])
                if value.get('checksum') != checksum or value.get('job_id') != job_id or value.get('chunk_id') != chunk_id:
                    _fail('Stored result fields are inconsistent.')
                raw = canonical_bytes(value)
                path = f'{folder}/{job_id}/{chunk_id}.json'
                if path not in files or files[path].stat().st_size > MAX_BYTES or files[path].read_bytes() != raw:
                    _fail('A referenced result file is missing or inconsistent.')
    except sqlite3.Error as exc:
        raise DomainError('Backup database could not be validated.') from exc
    finally:
        if 'db' in locals():
            db.close()


def _safe_relative(value):
    if type(value) is not str or '\\' in value or '\x00' in value:
        _fail('Unsafe backup path.')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or path.as_posix() != value or any(part in ('', '.', '..') for part in path.parts):
        _fail('Unsafe backup path.')
    if path.parts[0] not in ('library.sqlite3', *ASSET_DIRS) or (path.parts[0] == 'library.sqlite3' and len(path.parts) != 1):
        _fail('Backup contains a path outside app-owned data.')
    return path


def create_backup(data_dir, output_path):
    root = Path(data_dir).resolve()
    output = Path(output_path).absolute()
    if output.exists():
        _fail('Backup output already exists.')
    if output.parent.resolve() == root or root in output.parent.resolve().parents:
        _fail('Backup output must be outside the data directory.')
    if not output.parent.is_dir():
        _fail('Backup output directory does not exist.')
    db_path = root / 'library.sqlite3'
    lock = _source_lock(db_path)
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix='.novel-backup-', dir=output.parent))
        snapshot = stage / 'library.sqlite3'
        readonly = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
        target = sqlite3.connect(snapshot)
        try:
            readonly.backup(target)
        finally:
            target.close(); readonly.close()
        assets_root = stage / 'assets'
        assets_root.mkdir()
        assets = []
        source_files = _walk_assets(root)
        if len(source_files) + 2 > MAX_ENTRIES or sum(p.stat().st_size for p in source_files) > MAX_EXPANDED:
            _fail('Backup exceeds the expanded size limit.')
        for source_file in source_files:
            before = source_file.stat()
            if before.st_size > MAX_ENTRY:
                _fail('A backup entry exceeds the size limit.')
            relative = source_file.relative_to(root)
            target_file = assets_root / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(source_file, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as src, target_file.open('xb') as dst:
                if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                    _fail('An app asset changed while it was being backed up.')
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush(); os.fsync(dst.fileno())
            after = source_file.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                _fail('An app asset changed while it was being backed up.')
            if _digest(source_file) != _digest(target_file):
                _fail('An app asset changed while it was being backed up.')
            assets.append(_inventory(target_file))
        entries = [_inventory(snapshot), *assets]
        if len(entries) + 1 > MAX_ENTRIES or sum(item['size'] for item in entries) > MAX_EXPANDED:
            _fail('Backup exceeds the expanded size limit.')
        _validate_db(snapshot, [{'path': item['path'].relative_to(assets_root).as_posix(), 'file': item['path']} for item in assets])
        manifest = {'version': VERSION, 'entries': [
            {'path': 'library.sqlite3', 'size': entries[0]['size'], 'sha256': entries[0]['sha256']},
            *[{'path': item['path'].relative_to(assets_root).as_posix(), 'size': item['size'], 'sha256': item['sha256']} for item in assets]]}
        manifest_bytes = canonical_bytes(manifest)
        if len(manifest_bytes) > MAX_BYTES:
            _fail('Backup manifest exceeds the size limit.')
        archive_tmp = stage / 'archive.zip'
        with zipfile.ZipFile(archive_tmp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
            zf.writestr(MANIFEST, manifest_bytes)
            zf.write(snapshot, 'library.sqlite3')
            for item in assets:
                zf.write(item['path'], item['path'].relative_to(assets_root).as_posix())
        if archive_tmp.stat().st_size > MAX_ARCHIVE:
            _fail('Backup archive exceeds the size limit.')
        with archive_tmp.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(archive_tmp, output)
        dirfd = os.open(output.parent, os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
        return output
    except sqlite3.Error as exc:
        raise DomainError('Could not snapshot the library database.') from exc
    finally:
        lock.rollback(); lock.close()
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def restore_backup(archive_path, target_dir):
    archive = Path(archive_path)
    target = Path(target_dir).absolute()
    if target.exists() or target.is_symlink():
        _fail('Restore target already exists.')
    if not target.parent.is_dir():
        _fail('Restore parent directory does not exist.')
    stage = Path(tempfile.mkdtemp(prefix='.novel-restore-', dir=target.parent))
    try:
        if archive.stat().st_size > MAX_ARCHIVE:
            _fail('Backup archive exceeds the size limit.')
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_ENTRIES or len(names) != len(set(names)) or MANIFEST not in names:
                _fail('Backup archive has duplicate entries or an invalid inventory.')
            total = 0
            for info in infos:
                if info.flag_bits & 1 or info.is_dir() or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    _fail('Backup archive contains an unsupported entry.')
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or (mode and not (stat.S_ISREG(mode) or stat.S_IFMT(mode) == 0)):
                    _fail('Backup archive contains a non-regular file.')
                if info.filename != MANIFEST:
                    _safe_relative(info.filename)
                if info.file_size > MAX_ENTRY or info.file_size > MAX_EXPANDED:
                    _fail('Backup entry exceeds the size limit.')
                total += info.file_size
            if total > MAX_EXPANDED:
                _fail('Backup exceeds the expanded size limit.')
            if zf.getinfo(MANIFEST).file_size > MAX_BYTES:
                _fail('Backup manifest exceeds the size limit.')
            raw_manifest = zf.read(MANIFEST)
            manifest = load_json(raw_manifest)
            if (type(manifest) is not dict or set(manifest) != {'version', 'entries'} or
                type(manifest['version']) is not int or manifest['version'] != VERSION or
                type(manifest['entries']) is not list):
                _fail('Unsupported or invalid backup manifest.')
            expected = {}
            expanded = 0
            for item in manifest['entries']:
                if type(item) is not dict or set(item) != {'path', 'size', 'sha256'}:
                    _fail('Invalid backup inventory entry.')
                rel = _safe_relative(item['path'])
                if (item['path'] in expected or type(item['size']) is not int or item['size'] < 0 or
                    type(item['sha256']) is not str or len(item['sha256']) != 64 or
                    any(ch not in '0123456789abcdef' for ch in item['sha256'])):
                    _fail('Invalid backup inventory entry.')
                expected[item['path']] = item
                expanded += item['size']
                if len(expected) > MAX_ENTRIES or expanded > MAX_EXPANDED:
                    _fail('Backup inventory exceeds the size limit.')
            if 'library.sqlite3' not in expected or set(names) != {MANIFEST, *expected}:
                _fail('Backup archive does not match its inventory.')
            for name, item in expected.items():
                info = zf.getinfo(name)
                if info.file_size != item['size']:
                    _fail('Backup entry size does not match its inventory.')
                output = stage.joinpath(*_safe_relative(name).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256(); size = 0
                with zf.open(info) as src, output.open('xb') as dst:
                    while block := src.read(1024 * 1024):
                        size += len(block)
                        if size > item['size']:
                            _fail('Backup entry exceeds its declared size.')
                        h.update(block); dst.write(block)
                    dst.flush(); os.fsync(dst.fileno())
                if size != item['size'] or h.hexdigest() != item['sha256']:
                    _fail('Backup entry checksum mismatch.')
        asset_records = [{'path': name, 'file': stage.joinpath(*_safe_relative(name).parts)} for name in expected if name != 'library.sqlite3']
        _validate_db(stage / 'library.sqlite3', asset_records)
        renameat2 = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
        if renameat2 is None:
            _fail('Atomic no-overwrite restore is unsupported on this platform.')
        if renameat2(-100, os.fsencode(stage), -100, os.fsencode(target), 1) != 0:  # RENAME_NOREPLACE
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                _fail('Restore target already exists.')
            raise OSError(error, os.strerror(error))
        dirfd = os.open(target.parent, os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
        return target
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError('Backup archive could not be safely restored.') from exc
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
