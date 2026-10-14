import hashlib
import json

import pytest

from benchmarks.p0.prepare_corpus import prepare


def fixture(tmp_path):
    files = []
    entries = []
    for number in range(1, 6):
        path = tmp_path / f'{number}.txt'
        path.write_bytes(f'Mira said hello.\r\nChapter {number}.\n'.encode())
        files.append(path)
        entries.append({'id': f'ch{number:02d}', 'title': f'Invented {number}', 'tags': ['dialogue'], 'url': None, 'text_sha256': None})
    return {'schema_version': 1, 'corpus_id': 'invented', 'rights_status': 'unverified', 'chapters': entries}, files


def test_preserves_source_and_refuses_overwrite(tmp_path):
    manifest, files = fixture(tmp_path)
    output = tmp_path / 'corpus.json'
    result = prepare(manifest, files, output)
    assert result['chapters'][0]['text'].encode() == files[0].read_bytes()
    provenance = json.loads(result['provenance'])
    assert provenance['rights_status'] == 'unverified'
    assert provenance['sources'][0]['text_sha256'] == hashlib.sha256(files[0].read_bytes()).hexdigest()
    saved = output.read_bytes()
    with pytest.raises(ValueError):
        prepare(manifest, files, output)
    assert output.read_bytes() == saved


@pytest.mark.parametrize('problem', ['empty', 'encoding', 'hash', 'order', 'count', 'version', 'large', 'null'])
def test_rejects_bad_source_before_writing(tmp_path, problem):
    manifest, files = fixture(tmp_path)
    if problem == 'empty':
        files[0].write_text('  ')
    elif problem == 'encoding':
        files[0].write_bytes(b'\xff')
    elif problem == 'hash':
        manifest['chapters'][0]['text_sha256'] = '0' * 64
    elif problem == 'order':
        manifest['chapters'][0]['id'] = 'ch00'
    elif problem == 'version':
        manifest['schema_version'] = True
    elif problem == 'large':
        from app.bundles import MAX_TEXT
        files[0].write_bytes(b'x' * (MAX_TEXT + 1))
    elif problem == 'null':
        manifest['chapters'] = None
    else:
        files.pop()
    output = tmp_path / 'corpus.json'
    with pytest.raises(ValueError):
        prepare(manifest, files, output)
    assert not output.exists()


def test_rejects_total_corpus_limit_before_publication(tmp_path, monkeypatch):
    import benchmarks.p0.prepare_corpus as module
    manifest, files = fixture(tmp_path)
    monkeypatch.setattr(module, 'MAX_BYTES', 32)
    output = tmp_path / 'corpus.json'
    with pytest.raises(ValueError, match='JSON size limit'):
        prepare(manifest, files, output)
    assert not output.exists()


def test_two_chapters_require_explicit_smoke_preserving_hashes(tmp_path):
    manifest, files = fixture(tmp_path)
    output = tmp_path / 'smoke.json'
    with pytest.raises(ValueError):
        prepare(manifest, files[:2], output)
    result = prepare(manifest, files[:2], output, smoke=True)
    assert result['schema_version'] == 2 and result['mode'] == 'smoke'
    assert result['corpus_id'] == 'invented-smoke'
    assert len(result['chapters']) == 2
    provenance = json.loads(result['provenance'])
    assert provenance['mode'] == 'smoke'
    for entry, file in zip(provenance['sources'], files):
        assert entry['text_sha256'] == hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        prepare(manifest, files, tmp_path / 'wrong.json', smoke=True)
