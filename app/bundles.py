"""Versioned, self-contained fake translation bundles; no database access."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from datetime import datetime, timezone

MAX_BYTES = 16 * 1024 * 1024
MAX_TEXT = 4 * 1024 * 1024


class DomainError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DomainError('Invalid JSON value.') from exc


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def load_json(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise DomainError('JSON file exceeds the size limit.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DomainError('Duplicate JSON field.')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(DomainError('Non-finite JSON number.')))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DomainError('Invalid or incomplete JSON file.') from exc


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise DomainError('Unexpected or missing bundle fields.')


def string(value, empty=False):
    if type(value) is not str or (not empty and not value.strip()) or len(value) > MAX_TEXT or any(0xD800 <= ord(char) <= 0xDFFF for char in value) or len(value.encode('utf-8')) > MAX_TEXT:
        raise DomainError('Invalid text field.')


def integer(value):
    if type(value) is not int or value < 0:
        raise DomainError('Invalid nonnegative integer.')


def identifier(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise DomainError('Invalid UUID.') from exc


def hash_field(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise DomainError('Invalid SHA-256.')


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', value):
        raise DomainError('Invalid UTC timestamp.')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise DomainError('Invalid UTC timestamp.') from exc


def snapshot():
    prompt = {'version': 'fake-1', 'text': 'Return a deterministic FAKE marker followed by source; this is NOT real translation.'}
    glossary = {'revision': 0, 'entries': []}
    chunker = {'version': 'chars-1', 'config': {'target_chars': 1200}}
    context = {'policy': 'none', 'text': ''}
    return {'model_id': 'fake', 'model_revision': '1', 'tokenizer_id': 'none', 'tokenizer_revision': '1',
            'parameters': {}, 'prompt': prompt, 'prompt_hash': digest(prompt),
            'glossary': glossary, 'glossary_hash': digest(glossary),
            'chunker': chunker, 'chunker_hash': digest(chunker),
            'context': context, 'context_hash': digest(context)}


def input_hash(chunk, snap):
    return digest({'source_text': chunk['source_text'], 'source_hash': chunk['source_hash'],
                   'context_text': chunk['context_text'], 'context_hash': chunk['context_hash'], 'snapshot': snap})


def validate_manifest(manifest):
    fields(manifest, 'schema_version job_id book_id created_at source_language target_language source_hash snapshot chunks')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise DomainError('Unsupported manifest version.')
    for key in ('job_id', 'book_id'):
        identifier(manifest[key])
    timestamp(manifest['created_at'])
    for key in ('source_language', 'target_language'):
        string(manifest[key])
    hash_field(manifest['source_hash'])
    # P1 accepts only its pinned fake provider configuration.
    if manifest['snapshot'] != snapshot() or canonical_bytes(manifest['snapshot']) != canonical_bytes(snapshot()):
        raise DomainError('Unsupported or mismatched fake snapshot.')
    if type(manifest['chunks']) is not list or not manifest['chunks'] or len(manifest['chunks']) > 10000:
        raise DomainError('Invalid chunk list.')
    seen, chapters, previous = set(), {}, None
    chapter_ends = {}
    chapter_ids = set()
    for chunk in manifest['chunks']:
        fields(chunk, 'chunk_id chapter_id chapter_ordinal ordinal source_start source_end source_text source_hash context_text context_hash expected_input_hash')
        for key in ('chunk_id', 'chapter_id'):
            identifier(chunk[key])
        for key in ('chapter_ordinal', 'ordinal', 'source_start', 'source_end'):
            integer(chunk[key])
        string(chunk['source_text'])
        string(chunk['context_text'], empty=True)
        for key in ('source_hash', 'context_hash', 'expected_input_hash'):
            hash_field(chunk[key])
        position = (chunk['chapter_ordinal'], chunk['ordinal'])
        if chunk['chunk_id'] in seen or (previous is not None and position <= previous):
            raise DomainError('Duplicate or unordered chunk.')
        if chunk['chapter_ordinal'] in chapters and chapters[chunk['chapter_ordinal']] != chunk['chapter_id']:
            raise DomainError('Chapter identity mismatch.')
        chapter_ordinal = chunk['chapter_ordinal']
        if chapter_ordinal not in chapters:
            if chapter_ordinal != len(chapters) or chunk['chapter_id'] in chapter_ids or chunk['ordinal'] != 0:
                raise DomainError('Invalid chapter ordering.')
            chapter_ids.add(chunk['chapter_id'])
        elif chunk['ordinal'] != previous[1] + 1:
            raise DomainError('Invalid chunk ordering.')
        if chunk['source_start'] != chapter_ends.get(chapter_ordinal, 0):
            raise DomainError('Invalid source offsets.')
        chapter_ends[chapter_ordinal] = chunk['source_end']
        chapters[chapter_ordinal] = chunk['chapter_id']
        seen.add(chunk['chunk_id'])
        previous = position
        if (chunk['source_end'] - chunk['source_start'] != len(chunk['source_text'])
            or chunk['source_hash'] != text_hash(chunk['source_text'])
            or chunk['context_text'] != '' or chunk['context_hash'] != text_hash('')
            or chunk['expected_input_hash'] != input_hash(chunk, manifest['snapshot'])):
            raise DomainError('Chunk source or input hash mismatch.')
    if text_hash(''.join(chunk['source_text'] for chunk in manifest['chunks'])) != manifest['source_hash']:
        raise DomainError('Manifest source checksum mismatch.')
    if len(canonical_bytes(manifest)) > MAX_BYTES:
        raise DomainError('Manifest exceeds size limit.')
    return manifest


def provenance(manifest):
    snap = manifest['snapshot']
    return {**{key: snap[key] for key in ('model_id', 'model_revision', 'tokenizer_id', 'tokenizer_revision',
                                         'parameters', 'prompt_hash', 'glossary_hash', 'chunker_hash', 'context_hash')},
            'runner_version': 'fake-1'}


def validate_result(result, manifest):
    validate_manifest(manifest)
    fields(result, 'schema_version job_id manifest_hash chunk_id expected_input_hash status provenance translated_text input_tokens output_tokens started_at completed_at checksum')
    if type(result['schema_version']) is not int or result['schema_version'] != 1 or result['status'] != 'completed':
        raise DomainError('Only completed version 1 results are accepted.')
    identifier(result['job_id']); identifier(result['chunk_id'])
    for key in ('manifest_hash', 'expected_input_hash', 'checksum'):
        hash_field(result[key])
    chunk = next((c for c in manifest['chunks'] if c['chunk_id'] == result['chunk_id']), None)
    if (chunk is None or result['job_id'] != manifest['job_id'] or result['manifest_hash'] != digest(manifest)
        or result['expected_input_hash'] != chunk['expected_input_hash']
        or canonical_bytes(result['provenance']) != canonical_bytes(provenance(manifest))):
        raise DomainError('Result does not match this batch snapshot.')
    string(result['translated_text'])
    for key in ('input_tokens', 'output_tokens'):
        if result[key] is not None:
            integer(result[key])
    timestamp(result['started_at']); timestamp(result['completed_at'])
    if datetime.fromisoformat(result['completed_at'].replace('Z', '+00:00')) < datetime.fromisoformat(result['started_at'].replace('Z', '+00:00')):
        raise DomainError('Result completion precedes its start.')
    if result['checksum'] != digest({k: v for k, v in result.items() if k != 'checksum'}):
        raise DomainError('Result checksum mismatch.')
    return result


def fake_result(manifest, chunk):
    validate_manifest(manifest)
    if chunk not in manifest['chunks']:
        raise DomainError('Unknown chunk.')
    stamp = now()
    result = {'schema_version': 1, 'job_id': manifest['job_id'], 'manifest_hash': digest(manifest),
              'chunk_id': chunk['chunk_id'], 'expected_input_hash': chunk['expected_input_hash'],
              'status': 'completed', 'provenance': provenance(manifest),
              'translated_text': '[FAKE — NOT REAL TRANSLATION]\n' + chunk['source_text'],
              'input_tokens': None, 'output_tokens': None, 'started_at': stamp, 'completed_at': stamp}
    result['checksum'] = digest(result)
    return result


def atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def run_fake_bundle(manifest, result_dir, limit=None):
    validate_manifest(manifest)
    if limit is not None and (type(limit) is not int or limit < 1):
        raise DomainError('Chunk limit must be positive.')
    result_dir = Path(result_dir)
    completed, produced = 0, 0
    for chunk in manifest['chunks']:
        path = result_dir / (chunk['chunk_id'] + '.json')
        if path.exists():
            validate_result(load_json(path.read_bytes()), manifest)
            completed += 1
        elif limit is None or produced < limit:
            atomic_write(path, canonical_bytes(fake_result(manifest, chunk)))
            produced += 1
            completed += 1
    return {'completed': completed, 'total': len(manifest['chunks'])}
