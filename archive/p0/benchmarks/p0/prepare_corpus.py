"""Prepare full five-chapter or explicit smoke UTF-8 corpus offline; never fetch or overwrite source."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.bundles import MAX_BYTES, MAX_TEXT, canonical_bytes, load_json
from benchmarks.p0.runner import validate_corpus, write_new


def prepare(manifest, files, output, smoke=False):
    if (type(manifest) is not dict or type(manifest.get('schema_version')) is not int
        or manifest['schema_version'] != 1 or type(manifest.get('chapters')) is not list
        or len(manifest['chapters']) != 5 or not (1 <= len(files) <= 4 if smoke else len(files) == 5)):
        raise ValueError('Expected schema_version 1 and five chapter files (or one to four with --smoke).')
    chapters = []
    for index, (entry, path) in enumerate(zip(manifest['chapters'], files), 1):
        if type(entry) is not dict or entry.get('id') != f'ch{index:02d}' or not isinstance(entry.get('title'), str) or not entry['title'].strip():
            raise ValueError('Invalid chapter order/title.')
        tags = entry.get('tags', [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ValueError('Invalid chapter tags.')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_TEXT + 1)
        if len(raw) > MAX_TEXT:
            raise ValueError('Chapter exceeds text size limit.')
        text = raw.decode('utf-8')
        if not text.strip() or '\x00' in text or text.startswith('\ufeff'):
            raise ValueError('Expected nonempty UTF-8 text without BOM/NUL.')
        actual_hash = hashlib.sha256(raw).hexdigest()
        expected_hash = entry.get('text_sha256')
        if expected_hash is not None and expected_hash != actual_hash:
            raise ValueError('Text hash differs from source manifest.')
        chapters.append({'id': entry['id'], 'title': entry['title'], 'tags': tags, 'text': text})
    corpus_id = manifest.get('corpus_id')
    if not isinstance(corpus_id, str) or not corpus_id.strip():
        raise ValueError('Missing corpus_id.')
    mode = 'smoke' if smoke else 'full'
    corpus = {'schema_version': 2, 'mode': mode, 'corpus_id': corpus_id + ('-smoke' if smoke else ''),
              'provenance': json.dumps({'mode': mode, 'scope': 'pipeline smoke only; not full P0' if smoke else 'five-chapter P0',
                                       'rights_status': manifest.get('rights_status', 'unverified'),
                                       'rights_evidence': manifest.get('rights_evidence'),
                                       'book_url': manifest.get('book_url'),
                                       'sources': [{'raw_sha256': c.get('raw_sha256'), 'id': c['id'], 'url': c.get('url'),
                                                    'text_sha256': hashlib.sha256(v['text'].encode('utf-8')).hexdigest()}
                                                   for c, v in zip(manifest['chapters'], chapters)]}, ensure_ascii=False, sort_keys=True),
              'glossary': '', 'chapters': chapters}
    validate_corpus(corpus)
    if len(canonical_bytes(corpus)) > MAX_BYTES:
        raise ValueError('Corpus exceeds JSON size limit.')
    write_new(output, corpus)
    return corpus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--smoke', action='store_true', help='Explicit pipeline smoke only, using one to four initial chapters.')
    parser.add_argument('files', nargs='+', type=Path, help='Chapter 1..5 UTF-8 TXT files, in order.')
    args = parser.parse_args()
    try:
        prepare(load_json(args.manifest.read_bytes()), args.files, args.output, smoke=args.smoke)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
