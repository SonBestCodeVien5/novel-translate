import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.core import Store, DomainError
from app.epub import parse_epub


def epub(overrides=None):
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OPS/book.opf': b'<package xmlns="http://www.idpf.org/2007/opf"><metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Invented book</dc:title></metadata><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="z" href="z.xhtml" media-type="application/xhtml+xml"/><item id="i" href="image.png" media-type="image/png"/><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="z"/><itemref idref="cover"/><itemref idref="a"/></spine></package>',
        'OPS/a.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Second</h1><p>A bird.</p></body></html>',
        'OPS/z.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>First</h1><p>A <em>small</em> bird.<br/>Next line &amp; more.<img src="image.png"/></p><script>ignore()</script></body></html>',
        'OPS/cover.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="image.png"/></body></html>',
        'OPS/image.png': b'fake synthetic image',
    }
    files.update(overrides or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


class EpubTests(unittest.TestCase):
    def test_order_mapping_raw_restart_and_manual_preserved(self):
        raw = epub()
        parsed = parse_epub(raw)
        self.assertEqual([u['title'] for u in parsed['units']], ['First', 'Spine item 2', 'Second'])
        self.assertEqual(parsed['units'][0]['text'], 'First\n\nA small bird.\nNext line & more.')
        self.assertTrue(parsed['units'][1]['excluded_from_text'])
        unit = parsed['units'][0]
        node = next(n for n in unit['text_nodes'] if n['original'] == 'small')
        self.assertEqual(unit['text'][node['start']:node['end']], 'small')
        self.assertTrue(unit['blocks'])
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            book = store.import_epub(raw)
            job = store.create_job(book)
            manifest = store.get_manifest(job)
            self.assertEqual(''.join(c['source_text'] for c in manifest['chunks']),
                             ''.join(u['text'] for u in parsed['units']))
            chunk = store.get_book(book)['chapters'][0]['chunks'][0]
            store.save_revision(chunk['id'], 'Manual correction', 0, None)
            store = Store(temp)
            self.assertEqual(store.import_epub(raw, 'New title ignored'), book)
            self.assertEqual(store.get_book(book)['chapters'][0]['chunks'][0]['edited_text'], 'Manual correction')
            self.assertEqual(len(store.list_books()), 1)
            prefix = Path(temp) / 'sources' / hashlib.sha256(raw).hexdigest()
            self.assertEqual(prefix.with_suffix('.epub').read_bytes(), raw)
            mapping = json.loads(next((Path(temp) / 'sources').glob('*.mapping.json')).read_bytes())
            self.assertEqual(mapping, parsed)
            changed = epub({'OPS/a.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>New source</p></body></html>'})
            self.assertNotEqual(store.import_epub(changed), book)
            self.assertEqual(len(store.list_books()), 2)

    def test_invalid_inputs_do_not_mutate_books(self):
        cases = [b'invalid', epub({'../bad': b'x'}), epub({'/bad': b'x'}),
                 epub({'OPS/z.xhtml': b'<html'}),
                 epub({'OPS/z.xhtml': b'<!DOCTYPE html [<!ENTITY x "bad">]><html/>'}),
                 epub({'OPS/z.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"/>'}),
                 epub({'META-INF/encryption.xml': b'<encryption/>'}),
                 epub({'OPS/book.opf': b'<package xmlns="http://www.idpf.org/2007/opf"><manifest/><spine><itemref idref="missing"/></spine></package>'}),
                 epub({'OPS/book.opf': b'<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="x" href="https://example.org/x"/></manifest><spine><itemref idref="x"/></spine></package>'})]
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            for raw in cases:
                with self.subTest(size=len(raw)), self.assertRaises(DomainError):
                    store.import_epub(raw)
                self.assertEqual(store.list_books(), [])
                self.assertEqual(list((Path(temp) / 'sources').iterdir()), [])
        for limit in ['MAX_RAW', 'MAX_ENTRY', 'MAX_EXPANDED']:
            with patch('app.epub.' + limit, 10), self.assertRaises(DomainError):
                parse_epub(epub())

    def test_external_doctype_is_offline_and_internal_subset_is_rejected(self):
        xhtml = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Invented text</p></body></html>'
        raw = epub({'OPS/z.xhtml': b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">' + xhtml})
        self.assertEqual(parse_epub(raw)['units'][0]['text'], 'Invented text')
        for prefix in [b'<!DOCTYPE html []>', b'<!DOCTYPE html [<!ENTITY x "bad">]>']:
            with self.assertRaises(DomainError):
                parse_epub(epub({'OPS/z.xhtml': prefix + xhtml}))

    def test_duplicate_symlink_and_ratio(self):
        for kind in ['duplicate', 'symlink', 'ratio']:
            stream = io.BytesIO(epub())
            with zipfile.ZipFile(stream, 'a') as archive:
                if kind == 'duplicate':
                    with self.assertWarns(UserWarning):
                        archive.writestr('mimetype', b'other')
                elif kind == 'symlink':
                    info = zipfile.ZipInfo('symlink')
                    info.external_attr = 0o120777 << 16
                    archive.writestr(info, b'target')
                else:
                    archive.writestr('bomb', b'x' * 100000, compress_type=zipfile.ZIP_DEFLATED)
            with self.subTest(kind=kind), self.assertRaises(DomainError):
                parse_epub(stream.getvalue())
