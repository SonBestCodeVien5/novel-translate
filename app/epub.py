"""Bounded, offline EPUB import. One XHTML spine item is one source unit."""
import hashlib
import io
import posixpath
import re
import stat
import zipfile
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from .bundles import DomainError

PARSER_VERSION = 'epub-spine-1'
MAX_RAW = 64 * 1024 * 1024
MAX_ENTRY = 8 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'
OPF = '{http://www.idpf.org/2007/opf}'
XHTML = '{http://www.w3.org/1999/xhtml}'
BLOCKS = {'p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'pre', 'tr', 'dt', 'dd', 'nav', 'header', 'footer'}


def _path(value, base=''):
    url = urlsplit(value)
    if url.scheme or url.netloc or url.query or url.fragment:
        raise DomainError('EPUB references must be local archive paths.')
    decoded = unquote(url.path)
    if not decoded or decoded.startswith('/') or '\\' in decoded or '\x00' in decoded:
        raise DomainError('Unsafe EPUB path.')
    resolved = posixpath.normpath(posixpath.join(base, decoded))
    if resolved == '..' or resolved.startswith('../') or ':' in resolved:
        raise DomainError('Unsafe EPUB path.')
    return resolved


def _xml(raw):
    # XML declarations can select UTF-16; inspect decoded markup before parsing.
    probe = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    if '\x00' in probe or re.search(r'<!\s*ENTITY\b', probe, re.I):
        raise DomainError('EPUB entity declarations and unsupported XML encodings are forbidden.')
    declarations = re.findall(r'<!\s*DOCTYPE\b[^>]*>', probe, re.I)
    if any('[' in declaration for declaration in declarations):
        raise DomainError('EPUB internal DTD subsets are forbidden.')
    # ElementTree never resolves external DTDs; ordinary XHTML doctypes are safe.
    return ET.fromstring(raw)


def _body(root):
    if root.tag != XHTML + 'html':
        raise DomainError('Spine documents must be XHTML.')
    bodies = root.findall(XHTML + 'body')
    if len(bodies) != 1:
        raise DomainError('XHTML must have exactly one body.')
    out, nodes, blocks = [], [], []
    size = 0

    def append(value):
        nonlocal size
        out.append(value)
        size += len(value)

    def boundary(value):
        if out and not ''.join(out[-2:]).endswith(value):
            append(value)

    def text(value, locator, field):
        if not value:
            return
        normalized = re.sub(r'\s+', ' ', value)
        if not out or out[-1].endswith((' ', '\n')):
            normalized = normalized.lstrip(' ')
        start = size
        append(normalized)
        nodes.append({'locator': locator, 'field': field, 'original': value, 'start': start, 'end': size})

    def walk(element, locator):
        local = element.tag.removeprefix(XHTML)
        if local in {'script', 'style'}:
            return
        start = size
        if local in BLOCKS:
            boundary('\n\n')
            start = size
        if local == 'br':
            boundary('\n')
        text(element.text, locator, 'text')
        for index, child in enumerate(element):
            child_locator = locator + '/' + str(index)
            walk(child, child_locator)
            text(child.tail, child_locator, 'tail')
        if local in BLOCKS:
            blocks.append({'locator': locator, 'tag': local, 'start': start, 'end': size})
            boundary('\n\n')

    walk(bodies[0], 'body')
    joined = ''.join(out)
    left = len(joined) - len(joined.lstrip())
    source = joined.strip()
    for entry in nodes + blocks:
        entry['start'] = max(0, min(len(source), entry['start'] - left))
        entry['end'] = max(entry['start'], min(len(source), entry['end'] - left))
    heading = next((e for e in bodies[0].iter() if e.tag in {XHTML + 'h1', XHTML + 'h2'}), None)
    title = re.sub(r'\s+', ' ', ''.join(heading.itertext())).strip() if heading is not None else ''
    return source, title[:300], nodes, blocks


def parse_epub(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_RAW:
        raise DomainError('EPUB must contain between 1 byte and 64 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise DomainError('EPUB archive exceeds limits.')
            names = set()
            for entry in entries:
                name = entry.filename
                if (entry.orig_filename != name or _path(name.rstrip('/')) != name.rstrip('/') or name in names or
                        stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1 or
                        entry.file_size > MAX_ENTRY or entry.file_size > max(1, entry.compress_size) * 200):
                    raise DomainError('Unsafe or oversized EPUB archive entry.')
                names.add(name)
                # Check every resource CRC, without extracting or retaining expanded assets.
                archive.read(entry)
            if 'META-INF/encryption.xml' in names:
                raise DomainError('Encrypted EPUB resources are unsupported.')
            if archive.read('mimetype') != b'application/epub+zip':
                raise DomainError('Invalid EPUB mimetype.')
            container = _xml(archive.read('META-INF/container.xml'))
            if container.tag != CONTAINER + 'container':
                raise DomainError('Invalid EPUB container namespace.')
            roots = container.findall(CONTAINER + 'rootfiles/' + CONTAINER + 'rootfile')
            if len(roots) != 1 or roots[0].get('media-type') != 'application/oebps-package+xml':
                raise DomainError('EPUB must have one supported package.')
            package_path = _path(roots[0].get('full-path', ''))
            package = _xml(archive.read(package_path))
            if package.tag != OPF + 'package':
                raise DomainError('Invalid EPUB package namespace.')
            manifest, spine = package.find(OPF + 'manifest'), package.find(OPF + 'spine')
            if manifest is None or spine is None or not len(spine):
                raise DomainError('EPUB manifest and spine are required.')
            resources = {}
            for item in manifest:
                identity = item.get('id')
                path = _path(item.get('href', ''), posixpath.dirname(package_path))
                if item.tag != OPF + 'item' or not identity or identity in resources or path not in names:
                    raise DomainError('Invalid or missing EPUB manifest resource.')
                resources[identity] = {'path': path, 'media_type': item.get('media-type'), 'properties': item.get('properties', '')}
            units = []
            for ordinal, ref in enumerate(spine):
                resource = resources.get(ref.get('idref'))
                if ref.tag != OPF + 'itemref' or resource is None or resource['media_type'] != 'application/xhtml+xml':
                    raise DomainError('Invalid or unsupported EPUB spine resource.')
                source, title, nodes, blocks = _body(_xml(archive.read(resource['path'])))
                units.append({'ordinal': ordinal, 'locator': resource['path'], 'idref': ref.get('idref'),
                              'linear': ref.get('linear', 'yes'), 'nav': 'nav' in resource['properties'].split(),
                              'title': title or f'Spine item {ordinal + 1}', 'text': source,
                              'source_hash': hashlib.sha256(source.encode()).hexdigest(),
                              'text_nodes': nodes, 'blocks': blocks, 'excluded_from_text': not bool(source)})
            chapter_ordinal = 0
            for unit in units:
                unit['chapter_ordinal'] = chapter_ordinal if unit['text'] else None
                if unit['text']:
                    chapter_ordinal += 1
            if not any(unit['text'] for unit in units):
                raise DomainError('EPUB has no textual spine content.')
            metadata = package.find(OPF + 'metadata')
            title = metadata.find('{http://purl.org/dc/elements/1.1/}title') if metadata is not None else None
            return {'parser_version': PARSER_VERSION, 'package_path': package_path,
                    'title': (title.text or '').strip()[:300] if title is not None else '',
                    'resources': resources, 'units': units}
    except (zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeError, ValueError, RuntimeError, NotImplementedError, RecursionError) as exc:
        raise DomainError('Malformed or unsupported EPUB archive/XML.') from exc
