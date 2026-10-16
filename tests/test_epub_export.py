import hashlib
import io
import sqlite3
import zipfile
from xml.etree import ElementTree as ET

import pytest

from app.bundles import DomainError, canonical_bytes, now
from app.core import Store
from app.epub import OPF, XHTML, parse_epub
from app.real_bundles import MODELS, default_snapshot, make_result, provenance


class TinyTokenizer:
    chat_template = 'tiny-chat-template-v1'

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
        return [ord(char) for message in messages for char in message['content']]


def fixture_epub(mixed=False):
    paragraph = '<p><a href="../refs.xhtml#target">Source &amp; link.</a></p>'
    if mixed:
        paragraph = '<p>Source <em>mixed</em> text.</p>'
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OPS/package.opf': b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata><dc:identifier xmlns:dc="http://purl.org/dc/elements/1.1/" id="uid">source-id</dc:identifier><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Synthetic Edition</dc:title><dc:language xmlns:dc="http://purl.org/dc/elements/1.1/">en</dc:language></metadata><manifest><item id="a" href="Text/actual.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="b" href="sub/part.xhtml" media-type="application/xhtml+xml"/><item id="ref" href="refs.xhtml" media-type="application/xhtml+xml"/><item id="img" href="../Images/cover.png" media-type="image/png"/></manifest><spine><itemref idref="a"/><itemref idref="cover"/><itemref idref="b"/></spine></package>',
        'OPS/Text/actual.xhtml': ('<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter One</h1>' + paragraph + '</body></html>').encode(),
        'OPS/cover.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="../Images/cover.png"/></body></html>',
        'OPS/sub/part.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter Two</h1><p>Second source paragraph.</p></body></html>',
        'OPS/refs.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="target">Reference.</p></body></html>',
        'Images/cover.png': b'not a real image; fixture bytes only',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw, compress_type=zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED)
    return output.getvalue()


def fixture_epub2():
    original, _, _ = archive_content(fixture_epub())
    package = original['OPS/package.opf'].replace(b'version="3.0"', b'version="2.0"')
    package = package.replace(b'</manifest>', b'<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>')
    package = package.replace(b'<spine>', b'<spine toc="ncx">')
    original['OPS/package.opf'] = package
    original['OPS/toc.ncx'] = b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap/></ncx>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, raw in original.items():
            archive.writestr(name, raw, compress_type=zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED)
    return output.getvalue()


def reviewed_job(store, book_id, texts):
    manifest = store.create_real_job(book_id, TinyTokenizer(), default_snapshot(
        'Qwen/Qwen3-4B-Instruct-2507', MODELS['Qwen/Qwen3-4B-Instruct-2507'], TinyTokenizer.chat_template))
    batch = store.get_real_manifest(manifest)
    for chunk in batch['chunks']:
        stamp = now()
        translated = texts[chunk['chapter_ordinal']]
        result = make_result(batch, chunk, {'translated_text': translated, 'output_tokens': 2,
            'finish_reason': 'eos', 'provenance': provenance(batch)}, stamp, stamp)
        store.import_real_result(canonical_bytes(result))
        store.save_real_revision(manifest, chunk['chunk_id'], translated, 0, result['checksum'], True)
    return manifest


def archive_content(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}, archive.infolist(), archive.comment


def repack(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw, compress_type=zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED)
    return output.getvalue()


def test_txt_source_builds_valid_epub3_with_official_edited_text_and_escaping(tmp_path):
    store = Store(tmp_path)
    raw = 'Chapter 1\n\nSource paragraph.\n\nChapter 2\n\nAnother paragraph.'.encode()
    book = store.import_txt(raw, 'Synthetic & <Novel>', store.preview_txt(raw, 'Synthetic & <Novel>'))
    job = reviewed_job(store, book, {0: 'Chương Một\n\nXin & <bạn>.', 1: 'Chương Hai\n\nRồng & gió.'})
    first = store.get_real_manifest(job)['chunks'][0]
    result = next(item['result'] for item in store.get_real_job(job)['chunks'] if item['chunk']['chunk_id'] == first['chunk_id'])
    store.save_real_revision(job, first['chunk_id'], 'Chương Một\n\nXin & <bạn>!', 1, result['checksum'], True)
    raw_epub = store.export_real_epub(job)
    assert parse_epub(raw_epub)['title'] == 'Synthetic & <Novel>'
    files, infos, _ = archive_content(raw_epub)
    assert infos[0].filename == 'mimetype' and infos[0].compress_type == zipfile.ZIP_STORED and infos[0].extra == b''
    content = parse_epub(raw_epub)
    assert content['units'][0]['text'] == 'Chương Một\n\nXin & <bạn>!'
    opf = ET.fromstring(files['package.opf'])
    metadata = opf.find(OPF + 'metadata')
    assert metadata.find('{http://purl.org/dc/elements/1.1/}language').text == 'vi'
    assert metadata.find(OPF + 'meta').get('property') == 'dcterms:modified'
    assert opf.get('version') == '3.0'
    assert any(item.get('properties') == 'nav' for item in opf.find(OPF + 'manifest'))
    chapter = ET.fromstring(files['text/chapter-0001.xhtml'])
    assert [node.text for node in chapter.findall('.//' + XHTML + 'p')] == ['Chương Một', 'Xin & <bạn>!']


def test_imported_epub_preserves_spine_resources_link_and_updates_only_mapped_text(tmp_path):
    store = Store(tmp_path)
    source = fixture_epub()
    book = store.import_epub(source)
    job = reviewed_job(store, book, {
        0: 'Chương Một\n\nLiên kết & <đích>.',
        1: 'Chương Hai\n\nĐoạn thứ hai.',
    })
    output = store.export_real_epub(job)
    assert parse_epub(output)['units'][0]['text'] == 'Chương Một\n\nLiên kết & <đích>.'
    original, _, _ = archive_content(source)
    result, infos, _ = archive_content(output)
    assert result['Images/cover.png'] == original['Images/cover.png']
    assert result['OPS/cover.xhtml'] == original['OPS/cover.xhtml']
    assert result['OPS/refs.xhtml'] == original['OPS/refs.xhtml']
    assert 'OPS/Text/actual.xhtml' in result and 'OPS/sub/part.xhtml' in result
    assert infos[0].filename == 'mimetype' and infos[0].compress_type == zipfile.ZIP_STORED
    actual = ET.fromstring(result['OPS/Text/actual.xhtml'])
    anchor = actual.find('.//' + XHTML + 'a')
    assert anchor.get('href') == '../refs.xhtml#target' and anchor.text == 'Liên kết & <đích>.'
    package = ET.fromstring(result['OPS/package.opf'])
    assert package.find(OPF + 'metadata').find('{http://purl.org/dc/elements/1.1/}language').text == 'vi'
    assert package.find(OPF + 'metadata').find('{http://purl.org/dc/elements/1.1/}identifier').text.startswith('urn:uuid:')
    assert source == (tmp_path / 'sources' / (hashlib.sha256(source).hexdigest() + '.epub')).read_bytes()


def test_percent_encoded_package_path_uses_canonical_parser_path(tmp_path):
    files, _, _ = archive_content(fixture_epub())
    files['META-INF/container.xml'] = files['META-INF/container.xml'].replace(b'OPS/package.opf', b'OPS%20Dir/package.opf')
    files['OPS Dir/package.opf'] = files.pop('OPS/package.opf')
    for path in list(files):
        if path.startswith('OPS/'):
            files['OPS Dir/' + path[len('OPS/'):]] = files.pop(path)
    source = repack(files)
    store = Store(tmp_path)
    book = store.import_epub(source)
    job = reviewed_job(store, book, {0: 'Chương Một\n\nLiên kết.', 1: 'Chương Hai\n\nĐoạn.'})
    assert parse_epub(store.export_real_epub(job))['package_path'] == 'OPS Dir/package.opf'


def test_epub2_keeps_version_spine_and_ncx(tmp_path):
    store = Store(tmp_path)
    source = fixture_epub2()
    book = store.import_epub(source)
    job = reviewed_job(store, book, {0: 'Chương Một\n\nLiên kết.', 1: 'Chương Hai\n\nĐoạn.'})
    files, _, _ = archive_content(store.export_real_epub(job))
    assert ET.fromstring(files['OPS/package.opf']).get('version') == '2.0'
    assert files['OPS/toc.ncx'] == b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap/></ncx>'
    assert 'nav' not in files


@pytest.mark.parametrize(('fixture', 'texts', 'error'), [
    (lambda: fixture_epub(), {0: 'Chương Một\n\nMột\n\nHai', 1: 'Chương Hai\n\nĐoạn.'}, 'paragraph counts differ'),
    (lambda: fixture_epub(mixed=True), {0: 'Chương Một\n\nĐoạn mới.', 1: 'Chương Hai\n\nĐoạn.'}, 'exactly one source text node'),
])
def test_unaligned_or_mixed_markup_fails_without_creating_output(tmp_path, fixture, texts, error):
    store = Store(tmp_path)
    book = store.import_epub(fixture())
    job = reviewed_job(store, book, texts)
    with pytest.raises(DomainError, match=error):
        store.export_real_epub(job)
    assert not list(tmp_path.glob('*.epub'))


def test_export_requires_every_current_result_to_be_approved(tmp_path):
    store = Store(tmp_path)
    raw = b'Chapter 1\n\nSource.'
    book = store.import_txt(raw, 'Book', store.preview_txt(raw, 'Book'))
    job = store.create_real_job(book, TinyTokenizer(), default_snapshot(
        'Qwen/Qwen3-4B-Instruct-2507', MODELS['Qwen/Qwen3-4B-Instruct-2507'], TinyTokenizer.chat_template))
    with pytest.raises(DomainError, match='approved'):
        store.export_real_epub(job)
    manifest = store.get_real_manifest(job)
    chunk = manifest['chunks'][0]
    stamp = now()
    result = make_result(manifest, chunk, {'translated_text': 'Draft.', 'output_tokens': 1,
        'finish_reason': 'eos', 'provenance': provenance(manifest)}, stamp, stamp)
    store.import_real_result(canonical_bytes(result))
    store.save_real_revision(job, chunk['chunk_id'], 'Saved but not approved.', 0, result['checksum'], False)
    with pytest.raises(DomainError, match='approved'):
        store.export_real_epub(job)


@pytest.mark.parametrize('markup', [
    '<p onclick="alert(1)">Source.</p>',
    '<p><script>alert(1)</script>Source.</p>',
    '<p><a href="missing.xhtml#there">Source.</a></p>',
])
def test_active_content_and_broken_local_links_are_rejected(tmp_path, markup):
    raw = fixture_epub()
    files, _, _ = archive_content(raw)
    doc = files['OPS/Text/actual.xhtml'].decode()
    start = doc.index('<p>')
    end = doc.index('</p>', start) + len('</p>')
    files['OPS/Text/actual.xhtml'] = (doc[:start] + markup + doc[end:]).encode()
    store = Store(tmp_path)
    book = store.import_epub(repack(files))
    job = reviewed_job(store, book, {0: 'Chương Một\n\nDịch.', 1: 'Chương Hai\n\nĐoạn.'})
    with pytest.raises(DomainError):
        store.export_real_epub(job)


@pytest.mark.parametrize('markup', [
    '<p><script>alert(1)</script>Source &amp; link.</p>',
    '<p><a href="missing#there">Source &amp; link.</a></p>',
])
def test_extensionless_manifest_xhtml_is_scanned_for_active_content_and_links(tmp_path, markup):
    files, _, _ = archive_content(fixture_epub())
    package = files['OPS/package.opf']
    files['OPS/package.opf'] = package.replace(b'Text/actual.xhtml', b'Text/actual')
    document = files.pop('OPS/Text/actual.xhtml').decode()
    start, end = document.index('<p>'), document.index('</p>') + len('</p>')
    files['OPS/Text/actual'] = (document[:start] + markup + document[end:]).encode()
    store = Store(tmp_path)
    book = store.import_epub(repack(files))
    job = reviewed_job(store, book, {0: 'Chương Một\n\nDịch.', 1: 'Chương Hai\n\nĐoạn.'})
    with pytest.raises(DomainError):
        store.export_real_epub(job)
