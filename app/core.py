"""Local SQLite owner and durable TXT/fake-provider workflow."""
import hashlib
from contextlib import contextmanager
import re
import sqlite3
import uuid
from pathlib import Path
from .bundles import (DomainError, MAX_BYTES, MAX_TEXT, atomic_write, canonical_bytes, digest, fake_result,
                      input_hash, load_json, now, snapshot, text_hash, validate_manifest, validate_result)


def new_id():
    return str(uuid.uuid4())


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for directory in ('sources', 'batches', 'results', 'rejected', 'real-batches', 'real-results'):
            (self.data_dir / directory).mkdir(exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL, raw_hash TEXT NOT NULL, source_hash TEXT NOT NULL,
                    import_key TEXT UNIQUE NOT NULL, raw_path TEXT NOT NULL, import_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS chapters (
                    id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id),
                    ordinal INTEGER NOT NULL, title TEXT NOT NULL, source_text TEXT NOT NULL,
                    UNIQUE(book_id, ordinal));
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL REFERENCES chapters(id), ordinal INTEGER NOT NULL,
                    source_text TEXT NOT NULL, source_hash TEXT NOT NULL, source_start INTEGER NOT NULL,
                    source_end INTEGER NOT NULL, chunker_version TEXT NOT NULL,
                    UNIQUE(chapter_id, ordinal));
                CREATE TABLE IF NOT EXISTS jobs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    book_id TEXT NOT NULL REFERENCES books(id), manifest TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS results (
                    job_id TEXT NOT NULL REFERENCES jobs(id), chunk_id TEXT NOT NULL REFERENCES chunks(id),
                    checksum TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(job_id, chunk_id));
                CREATE TABLE IF NOT EXISTS revisions (
                    chunk_id TEXT NOT NULL REFERENCES chunks(id), revision INTEGER NOT NULL,
                    edited_text TEXT NOT NULL, base_result_hash TEXT, created_at TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, revision));
                CREATE TABLE IF NOT EXISTS real_jobs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    book_id TEXT NOT NULL REFERENCES books(id), manifest TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS real_chunks (
                    job_id TEXT NOT NULL REFERENCES real_jobs(id), chunk_id TEXT NOT NULL,
                    chapter_id TEXT NOT NULL REFERENCES chapters(id), chapter_ordinal INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(job_id, chunk_id), UNIQUE(job_id, chapter_ordinal, ordinal));
                CREATE TABLE IF NOT EXISTS real_results (
                    job_id TEXT NOT NULL, chunk_id TEXT NOT NULL, checksum TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(job_id, chunk_id),
                    FOREIGN KEY(job_id, chunk_id) REFERENCES real_chunks(job_id, chunk_id));
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.data_dir / 'library.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _source(raw):
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_TEXT:
            raise DomainError('TXT must contain between 1 byte and 4 MiB.')
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError as exc:
            raise DomainError('TXT must use UTF-8 encoding.') from exc
        if '\x00' in text or not text.strip():
            raise DomainError('TXT is empty or contains NUL characters.')
        return text.replace('\r\n', '\n').replace('\r', '\n')

    @staticmethod
    def _title(title):
        if type(title) is not str or not title.strip() or len(title) > 300 or '\x00' in title:
            raise DomainError('A title of 1–300 characters is required.')

    def preview_txt(self, raw, title, split_headings=True):
        self._title(title)
        if type(split_headings) is not bool:
            raise DomainError('Invalid heading option.')
        text = self._source(raw)
        headings = list(re.finditer(r'(?im)^(?:chapter|chương)\s+(?:\d+|[ivxlcdm]+)\b[^\n]*', text)) if split_headings else []
        starts = [match.start() for match in headings]
        if not starts:
            return [{'title': title, 'text': text}]
        chapters = []
        prefix_is_blank = starts[0] > 0 and not text[:starts[0]].strip()
        if starts[0] > 0 and not prefix_is_blank:
            chapters.append({'title': title, 'text': text[:starts[0]]})
        for index, match in enumerate(headings):
            end = starts[index + 1] if index + 1 < len(starts) else len(text)
            chapters.append({'title': match.group().strip(), 'text': text[0 if index == 0 and prefix_is_blank else match.start():end]})
        return chapters

    @staticmethod
    def _chunk_text(text, maximum=1200):
        start = 0
        while start < len(text):
            end = min(start + maximum, len(text))
            if end < len(text):
                candidates = list(re.finditer(r'[.!?][ \t\n]+|\n\n+', text[start:end]))
                if candidates:
                    end = start + candidates[-1].end()
                else:
                    space = text.rfind(' ', start + maximum // 2, end)
                    if space >= 0:
                        end = space + 1
            if not text[end:].strip():
                end = len(text)
            if not text[start:end].strip():
                first_content = re.search(r'\S', text[end:])
                if first_content:
                    end += first_content.end()
            yield start, end, text[start:end]
            start = end

    def import_txt(self, raw, title, chapters, source_language='en', target_language='vi'):
        self._title(title)
        source = self._source(raw)
        for language in (source_language, target_language):
            if type(language) is not str or not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*', language):
                raise DomainError('Invalid language code.')
        if type(chapters) is not list or not chapters or len(chapters) > 10000:
            raise DomainError('Invalid chapters.')
        for chapter in chapters:
            if type(chapter) is not dict or set(chapter) != {'title', 'text'}:
                raise DomainError('Invalid chapter fields.')
            self._title(chapter['title'])
            if type(chapter['text']) is not str or not chapter['text'].strip():
                raise DomainError('Chapter source must not be empty.')
        if ''.join(c['text'] for c in chapters) != source:
            raise DomainError('Chapter boundaries must preserve all source text in order.')
        raw_hash = hashlib.sha256(raw).hexdigest()
        import_key = digest({'raw_hash': raw_hash, 'import_version': 1, 'normalization': 'utf8-newlines-1',
                             'chapters': chapters, 'source_language': source_language, 'target_language': target_language})
        with self._connect() as db:
            existing = db.execute('SELECT id FROM books WHERE import_key=?', (import_key,)).fetchone()
            if existing:
                return existing['id']
            book_id = new_id()
            raw_path = 'sources/' + raw_hash + '.txt'
            path = self.data_dir / raw_path
            if not path.exists():
                atomic_write(path, raw)
            elif path.read_bytes() != raw:
                raise DomainError('Stored source integrity error.')
            db.execute('INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?)',
                       (book_id, title, source_language, target_language, raw_hash, text_hash(source), import_key, raw_path, 1))
            for ordinal, chapter in enumerate(chapters):
                chapter_id = new_id()
                db.execute('INSERT INTO chapters VALUES (?,?,?,?,?)',
                           (chapter_id, book_id, ordinal, chapter['title'], chapter['text']))
                for chunk_ordinal, (start, end, text) in enumerate(self._chunk_text(chapter['text'])):
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)',
                               (new_id(), chapter_id, chunk_ordinal, text, text_hash(text), start, end, 'chars-1'))
        return book_id

    def import_epub(self, raw, title=None, source_language='en', target_language='vi'):
        from .epub import parse_epub
        parsed = parse_epub(raw)
        title = parsed['title'] or 'Imported EPUB' if title is None else title
        self._title(title)
        for language in (source_language, target_language):
            if type(language) is not str or not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*', language):
                raise DomainError('Invalid language code.')
        raw_hash = hashlib.sha256(raw).hexdigest()
        import_key = digest({'raw_hash': raw_hash, 'parser_version': parsed['parser_version'],
                             'source_language': source_language, 'target_language': target_language})
        raw_path = 'sources/' + raw_hash + '.epub'
        mapping_path = self.data_dir / ('sources/' + raw_hash + '.' + parsed['parser_version'] + '.mapping.json')
        mapping = canonical_bytes(parsed)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM books WHERE import_key=?', (import_key,)).fetchone()
            for path, content in ((self.data_dir / raw_path, raw), (mapping_path, mapping)):
                if path.exists():
                    if path.read_bytes() != content:
                        raise DomainError('Stored EPUB source integrity error.')
                else:
                    atomic_write(path, content)
            if existing:
                return existing['id']
            book_id = new_id()
            source_hash = text_hash(''.join(u['text'] for u in parsed['units']))
            db.execute('INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?)',
                       (book_id, title, source_language, target_language, raw_hash, source_hash, import_key, raw_path, 1))
            for unit in parsed['units']:
                if unit['excluded_from_text']:
                    continue
                chapter_id = new_id()
                db.execute('INSERT INTO chapters VALUES (?,?,?,?,?)',
                           (chapter_id, book_id, unit['chapter_ordinal'], unit['title'], unit['text']))
                for ordinal, (start, end, text) in enumerate(self._chunk_text(unit['text'])):
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)',
                               (new_id(), chapter_id, ordinal, text, text_hash(text), start, end, 'chars-1'))
        return book_id

    def list_books(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT id,title FROM books ORDER BY rowid DESC')]

    @staticmethod
    def _book(db, book_id):
        book = db.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
        if book is None:
            raise DomainError('Book not found.', 404)
        return book

    @staticmethod
    def _latest_job(db, book_id):
        return db.execute('SELECT * FROM jobs WHERE book_id=? ORDER BY sequence DESC LIMIT 1', (book_id,)).fetchone()

    @staticmethod
    def _latest_revision(db, chunk_id):
        return db.execute('SELECT * FROM revisions WHERE chunk_id=? ORDER BY revision DESC LIMIT 1', (chunk_id,)).fetchone()

    def get_book(self, book_id):
        with self._connect() as db:
            book = self._book(db, book_id)
            latest = self._latest_job(db, book_id)
            output = {'id': book['id'], 'title': book['title'], 'chapters': [], 'jobs': []}
            for chapter in db.execute('SELECT * FROM chapters WHERE book_id=? ORDER BY ordinal', (book_id,)):
                entry = {key: chapter[key] for key in ('id', 'title', 'ordinal')}
                entry['chunks'] = []
                for chunk in db.execute('SELECT * FROM chunks WHERE chapter_id=? ORDER BY ordinal', (chapter['id'],)):
                    revision = self._latest_revision(db, chunk['id'])
                    result = db.execute('SELECT * FROM results WHERE job_id=? AND chunk_id=?',
                                        (latest['id'], chunk['id'])).fetchone() if latest else None
                    entry['chunks'].append({'id': chunk['id'], 'source_text': chunk['source_text'],
                        'translated_text': load_json(result['payload'].encode())['translated_text'] if result else None,
                        'edited_text': revision['edited_text'] if revision else None,
                        'revision': revision['revision'] if revision else 0,
                        'base_result_hash': result['checksum'] if result else None,
                        'revision_base_result_hash': revision['base_result_hash'] if revision else None,
                        'stale': bool(revision and revision['base_result_hash'] != (result['checksum'] if result else None))})
                output['chapters'].append(entry)
            for job in db.execute('SELECT * FROM jobs WHERE book_id=? ORDER BY sequence DESC', (book_id,)):
                completed = db.execute('SELECT COUNT(*) FROM results WHERE job_id=?', (job['id'],)).fetchone()[0]
                output['jobs'].append({'id': job['id'], 'status': job['status'], 'completed': completed,
                                       'total': len(load_json(job['manifest'].encode())['chunks'])})
            return output

    def create_job(self, book_id):
        with self._connect() as db:
            book = self._book(db, book_id)
            job_id = new_id()
            manifest = {'schema_version': 1, 'job_id': job_id, 'book_id': book_id, 'created_at': now(),
                        'source_language': book['source_language'], 'target_language': book['target_language'],
                        'source_hash': book['source_hash'], 'snapshot': snapshot(), 'chunks': []}
            for row in db.execute('''SELECT c.*,ch.ordinal AS chapter_ordinal FROM chunks c
                                   JOIN chapters ch ON c.chapter_id=ch.id WHERE ch.book_id=?
                                   ORDER BY ch.ordinal,c.ordinal''', (book_id,)):
                chunk = {'chunk_id': row['id'], 'chapter_id': row['chapter_id'], 'chapter_ordinal': row['chapter_ordinal'],
                         'ordinal': row['ordinal'], 'source_start': row['source_start'], 'source_end': row['source_end'],
                         'source_text': row['source_text'], 'source_hash': row['source_hash'],
                         'context_text': '', 'context_hash': text_hash('')}
                chunk['expected_input_hash'] = input_hash(chunk, manifest['snapshot'])
                manifest['chunks'].append(chunk)
            validate_manifest(manifest)
            atomic_write(self.data_dir / 'batches' / (job_id + '.json'), canonical_bytes(manifest))
            db.execute('INSERT INTO jobs(id,book_id,manifest,manifest_hash,status) VALUES (?,?,?,?,?)',
                       (job_id, book_id, canonical_bytes(manifest).decode(), digest(manifest), 'exported'))
        return job_id

    def get_manifest(self, job_id):
        with self._connect() as db:
            row = db.execute('SELECT manifest FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise DomainError('Job not found.', 404)
            return validate_manifest(load_json(row['manifest'].encode()))

    def _after_result_insert(self, db):
        """Fault injection seam: transaction must roll back on interruption."""

    def import_result(self, raw):
        if not isinstance(raw, bytes):
            raise DomainError('Result must be a JSON file.')
        try:
            result = load_json(raw)
            if type(result) is not dict or type(result.get('job_id')) is not str:
                raise DomainError('Missing job ID.')
            manifest = self.get_manifest(result['job_id'])
            validate_result(result, manifest)
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT checksum FROM results WHERE job_id=? AND chunk_id=?',
                                      (result['job_id'], result['chunk_id'])).fetchone()
                if previous:
                    if previous['checksum'] == result['checksum']:
                        return 'duplicate'
                    raise DomainError('Conflicting result: saved output was preserved.', 409)
                # Persist before commit so a crash can be recovered by importing this file again.
                path = self.data_dir / 'results' / result['job_id'] / (result['chunk_id'] + '.json')
                if path.exists():
                    saved = validate_result(load_json(path.read_bytes()), manifest)
                    if saved['checksum'] != result['checksum']:
                        raise DomainError('Conflicting durable result: saved output was preserved.', 409)
                else:
                    atomic_write(path, canonical_bytes(result))
                db.execute('INSERT INTO results VALUES (?,?,?,?)',
                           (result['job_id'], result['chunk_id'], result['checksum'], canonical_bytes(result).decode()))
                self._after_result_insert(db)
                count = db.execute('SELECT COUNT(*) FROM results WHERE job_id=?', (result['job_id'],)).fetchone()[0]
                db.execute('UPDATE jobs SET status=? WHERE id=?',
                           ('completed' if count == len(manifest['chunks']) else 'partial', result['job_id']))
            return 'imported'
        except DomainError:
            # Keep bounded rejected input outside the canonical results directory.
            if len(raw) <= 16 * 1024 * 1024:
                atomic_write(self.data_dir / 'rejected' / (new_id() + '.json'), raw)
            raise

    def run_fake(self, job_id, limit=1):
        if type(limit) is not int or limit < 1:
            raise DomainError('Chunk limit must be positive.')
        manifest = self.get_manifest(job_id)
        produced = 0
        for chunk in manifest['chunks']:
            path = self.data_dir / 'results' / job_id / (chunk['chunk_id'] + '.json')
            if path.exists():
                self.import_result(path.read_bytes())
                continue
            if produced >= limit:
                continue
            self.import_result(canonical_bytes(fake_result(manifest, chunk)))
            produced += 1
        with self._connect() as db:
            completed = db.execute('SELECT COUNT(*) FROM results WHERE job_id=?', (job_id,)).fetchone()[0]
        return {'completed': completed, 'total': len(manifest['chunks'])}

    @staticmethod
    def _verify_real_source(book, chapters, manifest):
        if (manifest['book_id'] != book['id'] or manifest['source_language'] != book['source_language']
            or manifest['target_language'] != book['target_language'] or manifest['source_hash'] != book['source_hash']):
            raise DomainError('Manifest does not match the current book source.')
        grouped = {}
        for chunk in manifest['chunks']:
            grouped.setdefault(chunk['chapter_ordinal'], []).append(chunk)
        if len(grouped) != len(chapters):
            raise DomainError('Manifest chapter list does not match the current book.')
        for ordinal, chapter in enumerate(chapters):
            chunks = grouped.get(ordinal, [])
            if (not chunks or any(c['chapter_id'] != chapter['id'] or c['chapter_ordinal'] != ordinal for c in chunks)
                or ''.join(c['source_text'] for c in chunks) != chapter['source_text']):
                raise DomainError('Manifest source or chapter order does not match the current book.')

    def create_real_job(self, book_id, tokenizer, snapshot):
        from .real_bundles import build_manifest, validate_manifest as validate_real_manifest
        with self._connect() as db:
            book = self._book(db, book_id)
            chapters = [dict(row) for row in db.execute(
                'SELECT id,ordinal,source_text FROM chapters WHERE book_id=? ORDER BY ordinal', (book_id,))]
            if text_hash(''.join(row['source_text'] for row in chapters)) != book['source_hash']:
                raise DomainError('Stored book source integrity error.')
            manifest = build_manifest(
                {key: book[key] for key in ('id', 'source_language', 'target_language', 'source_hash')},
                chapters, tokenizer, snapshot)
            validate_real_manifest(manifest)
            self._verify_real_source(book, chapters, manifest)
            raw = canonical_bytes(manifest)
            db.execute('BEGIN IMMEDIATE')
            atomic_write(self.data_dir / 'real-batches' / (manifest['job_id'] + '.json'), raw)
            db.execute('INSERT INTO real_jobs(id,book_id,manifest,manifest_hash,status) VALUES (?,?,?,?,?)',
                       (manifest['job_id'], book_id, raw.decode(), digest(manifest), 'exported'))
            for chunk in manifest['chunks']:
                db.execute('INSERT INTO real_chunks VALUES (?,?,?,?,?,?)',
                           (manifest['job_id'], chunk['chunk_id'], chunk['chapter_id'], chunk['chapter_ordinal'],
                            chunk['ordinal'], canonical_bytes(chunk).decode()))
        return manifest['job_id']

    def get_real_manifest(self, job_id):
        from .real_bundles import validate_manifest as validate_real_manifest
        with self._connect() as db:
            row = db.execute('SELECT manifest,manifest_hash,book_id FROM real_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise DomainError('Real job not found.', 404)
            manifest = validate_real_manifest(load_json(row['manifest'].encode()))
            if digest(manifest) != row['manifest_hash']:
                raise DomainError('Stored real manifest integrity error.')
            book = self._book(db, row['book_id'])
            chapters = [dict(chapter) for chapter in db.execute(
                'SELECT id,ordinal,source_text FROM chapters WHERE book_id=? ORDER BY ordinal', (row['book_id'],))]
            if text_hash(''.join(chapter['source_text'] for chapter in chapters)) != book['source_hash']:
                raise DomainError('Stored book source integrity error.')
            self._verify_real_source(book, chapters, manifest)
            return manifest

    def get_real_job(self, job_id):
        manifest = self.get_real_manifest(job_id)
        with self._connect() as db:
            job = db.execute('SELECT status FROM real_jobs WHERE id=?', (job_id,)).fetchone()
            chunks = []
            for row in db.execute('''SELECT c.payload,r.payload AS result FROM real_chunks c
                                     LEFT JOIN real_results r USING(job_id,chunk_id)
                                     WHERE c.job_id=? ORDER BY c.chapter_ordinal,c.ordinal''', (job_id,)):
                chunk = load_json(row['payload'].encode())
                chunks.append({'chunk': chunk, 'result': load_json(row['result'].encode()) if row['result'] else None})
            return {'id': job_id, 'status': job['status'], 'completed': sum(c['result'] is not None for c in chunks),
                    'total': len(chunks), 'chunks': chunks, 'manifest': manifest}

    def _after_real_result_insert(self, db):
        """Fault injection seam: transaction must roll back on interruption."""

    def import_real_result(self, raw):
        from .real_bundles import validate_result as validate_real_result
        if not isinstance(raw, bytes):
            raise DomainError('Result must be a JSON file.')
        try:
            result = load_json(raw)
            if type(result) is not dict or type(result.get('job_id')) is not str:
                raise DomainError('Missing job ID.')
            manifest = self.get_real_manifest(result['job_id'])
            validate_real_result(result, manifest)
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT checksum FROM real_results WHERE job_id=? AND chunk_id=?',
                                      (result['job_id'], result['chunk_id'])).fetchone()
                if previous:
                    if previous['checksum'] == result['checksum']:
                        return 'duplicate'
                    raise DomainError('Conflicting real result: saved output was preserved.', 409)
                path = self.data_dir / 'real-results' / result['job_id'] / (result['chunk_id'] + '.json')
                if path.exists():
                    if path.stat().st_size > MAX_BYTES:
                        raise DomainError('Stored durable result exceeds the size limit.')
                    with path.open('rb') as stream:
                        durable = stream.read(MAX_BYTES + 1)
                    if len(durable) > MAX_BYTES:
                        raise DomainError('Stored durable result exceeds the size limit.')
                    saved = validate_real_result(load_json(durable), manifest)
                    if saved['checksum'] != result['checksum']:
                        raise DomainError('Conflicting durable real result: saved output was preserved.', 409)
                else:
                    atomic_write(path, canonical_bytes(result))
                db.execute('INSERT INTO real_results VALUES (?,?,?,?)',
                           (result['job_id'], result['chunk_id'], result['checksum'], canonical_bytes(result).decode()))
                self._after_real_result_insert(db)
                count = db.execute('SELECT COUNT(*) FROM real_results WHERE job_id=?', (result['job_id'],)).fetchone()[0]
                db.execute('UPDATE real_jobs SET status=? WHERE id=?',
                           ('completed' if count == len(manifest['chunks']) else 'partial', result['job_id']))
            return 'imported'
        except DomainError:
            if len(raw) <= MAX_BYTES:
                path = self.data_dir / 'real-results' / 'rejected' / (new_id() + '.json')
                atomic_write(path, raw)
            raise

    def save_revision(self, chunk_id, text, base_revision, base_result_hash):
        if type(text) is not str or not text.strip() or any(0xD800 <= ord(char) <= 0xDFFF for char in text) or len(text.encode('utf-8')) > MAX_TEXT or '\x00' in text:
            raise DomainError('Revision must contain nonempty text within 4 MiB.')
        if type(base_revision) is not int or base_revision < 0:
            raise DomainError('Invalid base revision.')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            chunk = db.execute('SELECT ch.book_id FROM chunks c JOIN chapters ch ON c.chapter_id=ch.id WHERE c.id=?',
                               (chunk_id,)).fetchone()
            if chunk is None:
                raise DomainError('Chunk not found.', 404)
            revision = self._latest_revision(db, chunk_id)
            job = self._latest_job(db, chunk['book_id'])
            result = db.execute('SELECT checksum FROM results WHERE job_id=? AND chunk_id=?',
                                (job['id'], chunk_id)).fetchone() if job else None
            current_hash = result['checksum'] if result else None
            if base_revision != (revision['revision'] if revision else 0) or base_result_hash != current_hash:
                raise DomainError('Revision conflict. Reload the current text before saving.', 409)
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',
                       (chunk_id, base_revision + 1, text, base_result_hash, now()))

    def export_txt(self, book_id, draft=False):
        if type(draft) is not bool:
            raise DomainError('Invalid draft option.')
        book = self.get_book(book_id)
        blocks, missing = [], 0
        for chapter in book['chapters']:
            text = []
            for chunk in chapter['chunks']:
                if chunk['translated_text'] is None:
                    missing += 1
                    text.append('[MISSING CHUNK ' + chunk['id'] + ']\n' + (chunk['edited_text'] or ''))
                else:
                    text.append(chunk['edited_text'] if chunk['edited_text'] is not None else chunk['translated_text'])
            blocks.append(chapter['title'] + '\n\n' + ''.join(text))
        if missing and not draft:
            raise DomainError('Official export blocked: chunks are missing from the latest job. Choose draft export.')
        return ('[DRAFT — missing chunks: ' + str(missing) + ']\n\n' if draft else '') + '\n\n'.join(blocks)
