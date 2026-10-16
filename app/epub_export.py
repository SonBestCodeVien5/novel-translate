"""Conservative official EPUB export preserving imported structure and assets."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import posixpath
import re
import stat
import uuid
import zipfile
import zlib
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from .bundles import DomainError, MAX_BYTES, load_json
from .epub import MAX_ENTRY, MAX_EXPANDED, MAX_RAW, OPF, XHTML, _xml, parse_epub

DC = '{http://purl.org/dc/elements/1.1/}'
XML = '{http://www.w3.org/XML/1998/namespace}'
CONTAINER = 'META-INF/container.xml'
MIMETYPE = 'mimetype'
MAX_ENTRIES = 10_000
ACTIVE_TYPES = {'application/javascript', 'text/javascript', 'application/x-javascript',
                'application/wasm', 'application/x-shockwave-flash'}
ACTIVE_ELEMENTS = {'script', 'style', 'iframe', 'object', 'embed', 'form', 'audio', 'video', 'base'}
URL_ATTRS = {'href', 'src', 'poster', 'data', 'action', 'formaction', 'longdesc', 'cite', 'xlink:href'}


def _review(chapter, reason):
    raise DomainError(f'EPUB export needs review at chapter {chapter}: {reason} Export as TXT or fix paragraph breaks, then retry.')


def _paragraphs(text):
    return [(match.start(), match.end(), match.group()) for match in re.finditer(r'\S.*?(?=\n[ \t]*\n|\Z)', text, re.S)]


def _element(root, locator):
    parts = locator.split('/')
    if not parts or parts[0] != 'body':
        raise ValueError('invalid body locator')
    node = next(iter(root.findall(XHTML + 'body')))
    for part in parts[1:]:
        node = [child for child in node if isinstance(child.tag, str)][int(part)]
    return node


def _xml_preserving(raw):
    _xml(raw)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(raw, parser=parser)


def _serialize(root, original):
    raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    decoded = original.decode('utf-16' if original.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    doctype = re.search(r'<!\s*DOCTYPE\b[^>]*>', decoded, re.I)
    if doctype:
        end = raw.find(b'?>') + 2
        raw = raw[:end] + b'\n' + doctype.group().encode('utf-8') + raw[end:]
    return raw


def _set_text_node(root, node, text):
    element = _element(root, node['locator'])
    if node['field'] == 'text':
        current = element.text or ''
        leading = current[:len(current) - len(current.lstrip())]
        trailing = current[len(current.rstrip()):]
        element.text = leading + text + trailing
    else:
        current = element.tail or ''
        leading = current[:len(current) - len(current.lstrip())]
        trailing = current[len(current.rstrip()):]
        element.tail = leading + text + trailing


def _align_unit(unit, translated, chapter):
    source_parts, target_parts = _paragraphs(unit['text']), _paragraphs(translated)
    if len(source_parts) != len(target_parts):
        _review(chapter, 'source and translated paragraph counts differ.')
    nodes = unit['text_nodes']
    replacements = []
    for (start, end, _), (_, _, target) in zip(source_parts, target_parts):
        significant = [node for node in nodes if node['start'] < end and node['end'] > start and node['original'].strip()]
        if len(significant) != 1 or significant[0]['start'] > start or significant[0]['end'] < end:
            _review(chapter, 'a paragraph does not map to exactly one source text node.')
        replacements.append((significant[0], target))
    root = _xml_preserving(unit['_raw'])
    for node, target in replacements:
        _set_text_node(root, node, target)
    root.set('lang', 'vi')
    root.set(XML + 'lang', 'vi')
    return _serialize(root, unit['_raw'])


def _has_unsafe_css(raw):
    text = raw.decode('utf-8', 'replace')
    return '\\' in text or bool(re.search(r'@import|expression\s*\(|behavior\s*:|url\s*\(\s*["\']?(?:https?:|//|data:|javascript:)', text, re.I))


def _path_ref(document, value):
    url = urlsplit(value.strip())
    if url.scheme or url.netloc:
        return None
    if url.query:
        raise DomainError('EPUB export needs review: local URL queries are unsupported.')
    path = unquote(url.path)
    if '\\' in path or '\x00' in path:
        raise DomainError('EPUB export needs review: unsafe local link.')
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(document), path)) if path else document
    if resolved in ('..', '.') or resolved.startswith('../') or resolved.startswith('/') or ':' in resolved:
        raise DomainError('EPUB export needs review: unsafe local link.')
    return resolved, unquote(url.fragment)


def _validate_references(entries, media_types=None):
    media_types = media_types or {}
    def is_type(path, suffixes, media):
        return media_types.get(path, '').lower() in media or path.lower().endswith(suffixes)
    docs, anchors = {}, {}
    for path, raw in entries.items():
        if is_type(path, ('.xhtml', '.html', '.htm', '.svg', '.ncx'),
                   {'application/xhtml+xml', 'image/svg+xml', 'application/x-dtbncx+xml'}):
            root = _xml(raw)
            docs[path] = root
            ids = [el.get('id') for el in root.iter() if el.get('id')]
            names = [el.get('name') for el in root.iter() if el.get('name')]
            if len(ids) != len(set(ids)) or len(names) != len(set(names)):
                raise DomainError('EPUB export needs review: duplicate local anchor IDs.')
            anchors[path] = set(ids)
    for path, root in docs.items():
        for element in root.iter():
            local = element.tag.rsplit('}', 1)[-1].lower()
            if local in ACTIVE_ELEMENTS or local == 'foreignobject':
                raise DomainError('EPUB export needs review: active XHTML/SVG content is unsupported.')
            for name, value in element.attrib.items():
                local_attr = name.rsplit('}', 1)[-1].lower()
                if local_attr.startswith('on') or local_attr in {'style', 'srcset'}:
                    raise DomainError('EPUB export needs review: active or ambiguous markup is unsupported.')
                if local_attr not in URL_ATTRS:
                    continue
                try:
                    url = urlsplit(value.strip())
                except ValueError as exc:
                    raise DomainError('EPUB export needs review: malformed local link.') from exc
                is_anchor = local == 'a' and local_attr == 'href'
                if url.scheme or url.netloc:
                    if is_anchor and url.scheme.lower() in {'http', 'https', 'mailto', 'tel'} and not url.username:
                        continue
                    raise DomainError('EPUB export needs review: external or active resource links are unsupported.')
                ref = _path_ref(path, value)
                if ref is None:
                    continue
                destination, fragment = ref
                if destination not in entries:
                    raise DomainError('EPUB export needs review: a local resource or link is missing.')
                if fragment and destination in anchors and fragment not in anchors[destination]:
                    raise DomainError('EPUB export needs review: a local anchor target is missing.')
    for path, raw in entries.items():
        if is_type(path, ('.css',), {'text/css'}):
            if _has_unsafe_css(raw):
                raise DomainError('EPUB export needs review: active CSS references are unsupported.')
            css = raw.decode('utf-8', 'replace')
            matches = list(re.finditer(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', css, re.I))
            if len(matches) != len(re.findall(r'url\s*\(', css, re.I)):
                raise DomainError('EPUB export needs review: unsupported CSS resource syntax.')
            for match in matches:
                ref = _path_ref(path, match.group(1))
                if ref is None or ref[0] not in entries:
                    raise DomainError('EPUB export needs review: a local CSS resource is missing or external.')


def _set_metadata(package, title, edition_id):
    meta = package.find(OPF + 'metadata')
    if meta is None:
        meta = ET.Element(OPF + 'metadata')
        package.insert(0, meta)
    identifiers = meta.findall(DC + 'identifier')
    unique = package.get('unique-identifier')
    identifier = next((node for node in identifiers if node.get('id') == unique), None)
    if identifier is None:
        identifier = identifiers[0] if identifiers else ET.SubElement(meta, DC + 'identifier', {'id': 'translation-id'})
    if not identifier.get('id'):
        identifier.set('id', 'translation-id')
    package.set('unique-identifier', identifier.get('id'))
    identifier.text = edition_id
    titles = meta.findall(DC + 'title')
    if not titles:
        ET.SubElement(meta, DC + 'title').text = title
    elif not any((item.text or '').strip() for item in titles):
        titles[0].text = title
    languages = meta.findall(DC + 'language')
    if not languages:
        languages = [ET.SubElement(meta, DC + 'language')]
    for language in languages:
        language.text = 'vi'
    if package.get('version', '').startswith('3'):
        modified = next((item for item in meta.findall(OPF + 'meta') if item.get('property') == 'dcterms:modified'), None)
        if modified is None:
            modified = ET.SubElement(meta, OPF + 'meta', {'property': 'dcterms:modified'})
        modified.text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _generated_epub(title, chapters):
    pub_id = 'urn:uuid:' + str(uuid.uuid4())
    book = ET.Element('{' + 'http://www.idpf.org/2007/opf' + '}package', {'version': '3.0', 'unique-identifier': 'pub-id'})
    metadata = ET.SubElement(book, OPF + 'metadata')
    ET.SubElement(metadata, DC + 'identifier', {'id': 'pub-id'}).text = pub_id
    ET.SubElement(metadata, DC + 'title').text = title
    ET.SubElement(metadata, DC + 'language').text = 'vi'
    ET.SubElement(metadata, OPF + 'meta', {'property': 'dcterms:modified'}).text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    manifest, spine = ET.SubElement(book, OPF + 'manifest'), ET.SubElement(book, OPF + 'spine')
    ET.SubElement(manifest, OPF + 'item', {'id': 'nav', 'href': 'nav.xhtml', 'media-type': 'application/xhtml+xml', 'properties': 'nav'})
    chapter_paths, files = [], {}
    for ordinal, chapter in enumerate(chapters):
        filename = f'text/chapter-{ordinal + 1:04}.xhtml'
        chapter_paths.append(filename)
        identity = f'chapter-{ordinal + 1}'
        ET.SubElement(manifest, OPF + 'item', {'id': identity, 'href': filename, 'media-type': 'application/xhtml+xml'})
        ET.SubElement(spine, OPF + 'itemref', {'idref': identity})
        html = ET.Element(XHTML + 'html', {'lang': 'vi', XML + 'lang': 'vi'})
        head = ET.SubElement(html, XHTML + 'head')
        ET.SubElement(head, XHTML + 'title').text = chapter['title']
        body = ET.SubElement(html, XHTML + 'body')
        for _, _, paragraph in _paragraphs(chapter['text']):
            ET.SubElement(body, XHTML + 'p').text = paragraph
        files[filename] = ET.tostring(html, encoding='utf-8', xml_declaration=True)
    nav = ET.Element(XHTML + 'html', {'lang': 'vi', XML + 'lang': 'vi'})
    head = ET.SubElement(nav, XHTML + 'head')
    ET.SubElement(head, XHTML + 'title').text = 'Contents'
    body = ET.SubElement(nav, XHTML + 'body')
    toc = ET.SubElement(body, XHTML + 'nav', {'{http://www.idpf.org/2007/ops}type': 'toc'})
    ET.SubElement(toc, XHTML + 'h1').text = title
    listing = ET.SubElement(toc, XHTML + 'ol')
    for chapter, filename in zip(chapters, chapter_paths):
        item = ET.SubElement(listing, XHTML + 'li')
        ET.SubElement(item, XHTML + 'a', {'href': posixpath.relpath(filename, '.')}).text = chapter['title']
    files['nav.xhtml'] = ET.tostring(nav, encoding='utf-8', xml_declaration=True)
    opf = ET.tostring(book, encoding='utf-8', xml_declaration=True)
    container = (b'<?xml version="1.0" encoding="UTF-8"?>'
                 b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                 b'<rootfiles><rootfile full-path="package.opf" media-type="application/oebps-package+xml"/>'
                 b'</rootfiles></container>')
    files['package.opf'] = opf
    files[CONTAINER] = container
    return _zip(files)


def _zip(files, source_infos=None, comment=b''):
    if len(files) + 1 > MAX_ENTRIES or any(len(raw) > MAX_ENTRY for raw in files.values()) or sum(map(len, files.values())) > MAX_EXPANDED:
        raise DomainError('EPUB export exceeds the archive limits.')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', allowZip64=True) as archive:
        archive.comment = comment[:65535]
        mime = zipfile.ZipInfo(MIMETYPE)
        mime.compress_type = zipfile.ZIP_STORED
        mime.extra = b''
        archive.writestr(mime, b'application/epub+zip')
        for name, raw in files.items():
            if name == MIMETYPE:
                continue
            info = copy.copy(source_infos[name]) if source_infos and name in source_infos else zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED if len(raw) > 190 * max(1, len(zlib.compress(raw, 6))) else zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    result = output.getvalue()
    if len(result) > MAX_RAW:
        raise DomainError('EPUB export exceeds the 64 MiB output limit.')
    return result


def _source_epub(store, chapters, book):
    if not re.fullmatch(r'[0-9a-f]{64}', book['raw_hash']) or book['raw_path'] != f"sources/{book['raw_hash']}.epub":
        raise DomainError('Stored source EPUB path is invalid.')
    source_dir = store.data_dir.resolve() / 'sources'
    if source_dir.is_symlink():
        raise DomainError('Stored source directory is unsafe.')
    raw_path = source_dir / f"{book['raw_hash']}.epub"
    if raw_path.is_symlink() or not raw_path.is_file() or raw_path.stat().st_size > MAX_RAW:
        raise DomainError('Stored source EPUB is missing or exceeds the export limit.')
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != book['raw_hash']:
        raise DomainError('Stored source EPUB failed its checksum.')
    parsed = parse_epub(raw)
    mapping_path = source_dir / f"{book['raw_hash']}.{parsed['parser_version']}.mapping.json"
    if (mapping_path.is_symlink() or not mapping_path.is_file() or mapping_path.stat().st_size > MAX_BYTES or
            load_json(mapping_path.read_bytes()) != parsed):
        raise DomainError('Stored EPUB mapping is missing or inconsistent; reimport the source before export.')
    if [u['locator'] for u in parsed['units']] != list(dict.fromkeys(u['locator'] for u in parsed['units'])):
        raise DomainError('EPUB export needs review: duplicate spine locator.')
    with store._connect() as db:
        db_chapters = [dict(row) for row in db.execute(
            'SELECT ordinal,title,source_text FROM chapters WHERE book_id=? ORDER BY ordinal', (book['id'],))]
    nonempty = [u for u in parsed['units'] if not u['excluded_from_text']]
    if len(nonempty) != len(db_chapters):
        raise DomainError('Stored EPUB mapping no longer matches the chapter list.')
    for ordinal, (unit, chapter) in enumerate(zip(nonempty, db_chapters)):
        if unit['chapter_ordinal'] != ordinal or unit['text'] != chapter['source_text']:
            raise DomainError(f'Stored EPUB mapping does not match chapter {ordinal + 1}.')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [item.filename for item in archive.infolist()]
        if any(name.lower().endswith('signatures.xml') for name in names):
            raise DomainError('Signed EPUB cannot be modified; export as TXT or remove the signature first.')
        if any(name.lower() == 'meta-inf/encryption.xml' for name in names):
            raise DomainError('Encrypted EPUB cannot be modified; export as TXT.')
        infos = {item.filename: item for item in archive.infolist()}
        files = {name: archive.read(name) for name in names}
        package_path = parsed['package_path']
        package = _xml_preserving(files[package_path])
        if package.tag != OPF + 'package':
            raise DomainError('Source EPUB has an unsupported package document.')
        if not package.get('version', '').startswith(('2', '3')):
            raise DomainError('Source EPUB package version is unsupported; export as TXT.')
        media_types = {}
        for item in package.find(OPF + 'manifest'):
            resource = parsed['resources'].get(item.get('id'))
            if resource:
                media_types[resource['path']] = resource.get('media_type') or ''
            if item.get('media-type', '').lower() in ACTIVE_TYPES:
                raise DomainError('EPUB export needs review: active script or executable resources are unsupported.')
        for path, body in files.items():
            media_type = media_types.get(path, '').lower()
            if media_type in {'application/xhtml+xml', 'image/svg+xml', 'application/x-dtbncx+xml'} or path.lower().endswith(('.xhtml', '.html', '.htm', '.svg', '.ncx')):
                root = _xml(body)
                for node in root.iter():
                    local = node.tag.rsplit('}', 1)[-1].lower()
                    if local in ACTIVE_ELEMENTS or local == 'foreignobject':
                        raise DomainError('EPUB export needs review: active XHTML/SVG content is unsupported.')
                    if any(key.rsplit('}', 1)[-1].lower().startswith('on') for key in node.attrib):
                        raise DomainError('EPUB export needs review: event handlers are unsupported.')
            if (media_type == 'text/css' or path.lower().endswith('.css')) and _has_unsafe_css(body):
                raise DomainError('EPUB export needs review: active CSS references are unsupported.')
        for index, (unit, chapter) in enumerate(zip(nonempty, chapters), start=1):
            unit['_raw'] = files[unit['locator']]
            files[unit['locator']] = _align_unit(unit, chapter['text'], index)
        if package.get('version', '').startswith('3'):
            opf_manifest = package.find(OPF + 'manifest')
            if not any('nav' in item.get('properties', '').split() for item in opf_manifest.findall(OPF + 'item')):
                nav_path = posixpath.join(posixpath.dirname(package_path), 'nav-translation.xhtml')
                suffix = 2
                while nav_path in files:
                    nav_path = posixpath.join(posixpath.dirname(package_path), f'nav-translation-{suffix}.xhtml')
                    suffix += 1
                nav = ET.Element(XHTML + 'html', {'lang': 'vi', XML + 'lang': 'vi'})
                nav_head = ET.SubElement(nav, XHTML + 'head')
                ET.SubElement(nav_head, XHTML + 'title').text = 'Contents'
                nav_body = ET.SubElement(nav, XHTML + 'body')
                toc = ET.SubElement(nav_body, XHTML + 'nav', {'{http://www.idpf.org/2007/ops}type': 'toc'})
                ET.SubElement(toc, XHTML + 'h1').text = book['title']
                listing = ET.SubElement(toc, XHTML + 'ol')
                for unit, chapter in zip(nonempty, chapters):
                    li = ET.SubElement(listing, XHTML + 'li')
                    href = posixpath.relpath(unit['locator'], posixpath.dirname(nav_path) or '.')
                    ET.SubElement(li, XHTML + 'a', {'href': href}).text = chapter['title']
                files[nav_path] = ET.tostring(nav, encoding='utf-8', xml_declaration=True)
                identity = 'translation-nav'
                ids = {item.get('id') for item in opf_manifest.findall(OPF + 'item')}
                while identity in ids:
                    identity += '-new'
                ET.SubElement(opf_manifest, OPF + 'item', {
                    'id': identity,
                    'href': posixpath.relpath(nav_path, posixpath.dirname(package_path) or '.'),
                    'media-type': 'application/xhtml+xml', 'properties': 'nav'})
        _set_metadata(package, book['title'], 'urn:uuid:' + str(uuid.uuid4()))
        files[package_path] = _serialize(package, files[package_path])
        for item in files.values():
            if len(item) > MAX_ENTRY:
                raise DomainError('EPUB export exceeds the per-entry limit.')
        if sum(map(len, files.values())) > MAX_EXPANDED:
            raise DomainError('EPUB export exceeds the expanded size limit.')
        _validate_references(files, media_types)
        archive_comment = archive.comment
    result = _zip(files, infos, archive_comment)
    parse_epub(result)
    return result


def export_real_epub(store, job_id):
    chapters, _ = store._real_export_chapters(job_id)
    manifest = store.get_real_manifest(job_id)
    with store._connect() as db:
        book = dict(store._book(db, manifest['book_id']))
    if book['raw_path'].lower().endswith('.epub'):
        return _source_epub(store, chapters, book)
    if not book['raw_path'].lower().endswith('.txt'):
        raise DomainError('Unsupported source format for EPUB export; use TXT export.')
    return _generated_epub(book['title'], chapters)
