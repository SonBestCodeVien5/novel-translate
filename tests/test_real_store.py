import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import real_runner
from app.bundles import canonical_bytes, digest, fake_result, now
from app.core import DomainError, Store
from app.real_bundles import MODELS, default_snapshot, make_result, provenance
from scripts import real_batch


class TinyTokenizer:
    chat_template = 'tiny-chat-template-v1'

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
        return [ord(char) for char in ''.join(message['content'] for message in messages)]


class RealStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = Store(self.path)
        self.raw = ('Chapter 1\n' + 'A sentence. ' * 150).encode()
        self.chapters = self.store.preview_txt(self.raw, 'Example')
        self.book = self.store.import_txt(self.raw, 'Example', self.chapters)
        self.fake_job = self.store.create_job(self.book)
        self.fake_manifest = self.store.get_manifest(self.fake_job)
        self.store.import_result(canonical_bytes(fake_result(self.fake_manifest, self.fake_manifest['chunks'][0])))
        first = self.store.get_book(self.book)['chapters'][0]['chunks'][0]
        self.store.save_revision(first['id'], 'Manual text remains current.', 0, first['base_result_hash'])
        model = 'Qwen/Qwen3-4B-Instruct-2507'
        revision = MODELS[model]
        self.tokenizer = TinyTokenizer()
        self.snapshot = default_snapshot(model, revision, 'tiny-chat-template-v1')
        self.job = self.store.create_real_job(self.book, self.tokenizer, self.snapshot)
        self.manifest = self.store.get_real_manifest(self.job)

    def result(self, chunk):
        stamp = now()
        return make_result(self.manifest, chunk,
                           {'translated_text': 'Kết quả tổng hợp.', 'output_tokens': 3,
                            'finish_reason': 'eos', 'provenance': provenance(self.manifest)}, stamp, stamp)

    @staticmethod
    def resign(result):
        result['checksum'] = digest({key: value for key, value in result.items() if key != 'checksum'})
        return result

    def test_restart_idempotence_conflict_and_fake_revision_isolation(self):
        chunks = self.manifest['chunks']
        self.assertGreater(len(chunks), 1)
        raw = canonical_bytes(self.result(chunks[0]))
        self.assertEqual(self.store.import_real_result(raw), 'imported')
        self.assertEqual(self.store.import_real_result(raw), 'duplicate')
        conflict = self.result(chunks[0])
        conflict['translated_text'] = 'Khác.'
        with self.assertRaises(DomainError):
            self.store.import_real_result(canonical_bytes(self.resign(conflict)))
        self.store = Store(self.path)
        job = self.store.get_real_job(self.job)
        self.assertEqual((job['completed'], job['total']), (1, len(chunks)))
        self.assertEqual(self.store.get_book(self.book)['jobs'][0]['id'], self.fake_job)
        first = self.store.get_book(self.book)['chapters'][0]['chunks'][0]
        self.assertEqual(first['edited_text'], 'Manual text remains current.')
        self.assertEqual(first['translated_text'].splitlines()[0], '[FAKE — NOT REAL TRANSLATION]')

    def test_rejects_truncated_wrong_provenance_and_mutated_source(self):
        result = self.result(self.manifest['chunks'][0])
        raw = canonical_bytes(result)
        for broken in (raw[:-7],):
            with self.assertRaises(DomainError):
                self.store.import_real_result(broken)
        wrong = copy.deepcopy(result)
        wrong['provenance']['model_revision'] = 'wrong'
        with self.assertRaises(DomainError):
            self.store.import_real_result(canonical_bytes(self.resign(wrong)))
        with self.store._connect() as db:
            db.execute('UPDATE chapters SET source_text=source_text || ? WHERE id=?',
                       ('changed', self.manifest['chunks'][0]['chapter_id']))
        with self.assertRaises(DomainError):
            self.store.import_real_result(raw)

    def test_crash_after_result_insert_recovers_from_durable_file(self):
        result = self.result(self.manifest['chunks'][0])
        raw = canonical_bytes(result)

        def crash(_db):
            raise RuntimeError('simulated interruption')

        self.store._after_real_result_insert = crash
        with self.assertRaises(RuntimeError):
            self.store.import_real_result(raw)
        self.assertEqual(self.store.get_real_job(self.job)['completed'], 0)
        path = self.path / 'real-results' / self.job / (result['chunk_id'] + '.json')
        self.assertEqual(path.read_bytes(), raw)
        self.store = Store(self.path)
        self.assertEqual(self.store.import_real_result(raw), 'imported')
        self.assertEqual(self.store.get_real_job(self.job)['completed'], 1)

    def test_results_import_out_of_order_and_schema_migration_is_repeatable(self):
        results = [self.result(chunk) for chunk in self.manifest['chunks']]
        for result in reversed(results):
            self.assertEqual(self.store.import_real_result(canonical_bytes(result)), 'imported')
        self.assertEqual(self.store.get_real_job(self.job)['status'], 'completed')
        self.store = Store(self.path)
        self.assertEqual(self.store.get_real_job(self.job)['completed'], len(results))
        with self.store._connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM results').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM real_jobs').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM real_results').fetchone()[0], len(results))

    def test_real_revision_conflict_late_import_and_job_scoped_official_export(self):
        chunk = self.manifest['chunks'][0]
        self.store.save_real_revision(self.job, chunk['chunk_id'], 'Edit before result', 0, None, False)
        result = self.result(chunk)
        self.store.import_real_result(canonical_bytes(result))
        state = self.store.get_real_job(self.job)['chunks'][0]
        self.assertEqual(state['revision']['edited_text'], 'Edit before result')
        self.assertTrue(state['stale'])
        self.assertIn('Edit before result', self.store.export_real_txt(self.job, draft=True))
        with self.assertRaises(DomainError):
            self.store.export_real_txt(self.job)
        with self.assertRaises(DomainError):
            self.store.save_real_revision(self.job, chunk['chunk_id'], 'Stale tab', 0, result['checksum'], True)
        self.store.save_real_revision(self.job, chunk['chunk_id'], 'Approved edit', 1, result['checksum'], True)
        with self.assertRaises(DomainError):
            self.store.export_real_txt(self.job)
        for other in self.manifest['chunks'][1:]:
            out = self.result(other)
            self.store.import_real_result(canonical_bytes(out))
            self.store.save_real_revision(self.job, other['chunk_id'], 'Approved', 0, out['checksum'], True)
        self.assertIn('Approved edit', self.store.export_real_txt(self.job))
        second = self.store.create_real_job(self.book, self.tokenizer, self.snapshot)
        with self.assertRaises(DomainError):
            self.store.export_real_txt(second)

    def test_real_runner_files_import_into_store_and_resume_after_restart(self):
        def generate(manifest, chunk):
            return {'translated_text': 'Bản dịch fixture.', 'output_tokens': 3, 'finish_reason': 'eos',
                    'provenance': provenance(manifest)}

        output = self.path / 'runner-output'
        self.assertEqual(real_runner.run_manifest(self.manifest, output, generate)['completed'],
                         len(self.manifest['chunks']))
        self.store = Store(self.path)
        files = sorted(output.glob('*.json'))
        self.assertEqual(len(files), len(self.manifest['chunks']) + 1)  # manifest plus one result per chunk
        for path in reversed(files):
            if path.name != 'manifest.json':
                self.assertEqual(self.store.import_real_result(path.read_bytes()), 'imported')
        self.store = Store(self.path)
        self.assertEqual(self.store.get_real_job(self.job)['status'], 'completed')
        self.assertEqual(self.store.import_real_result(next(p.read_bytes() for p in files if p.name != 'manifest.json')),
                         'duplicate')

    def test_cli_export_guards_and_status_redacts_source(self):
        model = 'Qwen/Qwen3-4B-Instruct-2507'
        revision = MODELS[model]
        output = self.path / 'manifest.json'

        def invoke(rev=revision, out=output):
            stdout, stderr = StringIO(), StringIO()
            args = ['export', '--data-dir', str(self.path), '--book-id', self.book,
                    '--model', model, '--revision', rev, '--output', str(out)]
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = real_batch.main(args)
            return code, stdout.getvalue(), stderr.getvalue()

        code, _, error = invoke(rev='wrong-pin')
        self.assertEqual(code, 1)
        self.assertIn('pinned revision', error)
        self.assertFalse(output.exists())

        with patch('app.real_bundles.load_tokenizer', side_effect=ImportError('missing transformers')):
            code, _, error = invoke()
        self.assertEqual(code, 1)
        self.assertIn('transformers==4.57.3', error)
        self.assertFalse(output.exists())

        output.write_bytes(b'preserve unrelated file')
        code, _, error = invoke()
        self.assertEqual(code, 1)
        self.assertIn('already exists', error)
        self.assertEqual(output.read_bytes(), b'preserve unrelated file')

        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(real_batch.main(['status', '--data-dir', str(self.path), '--job-id', self.job]), 0)
        self.assertNotIn('A sentence.', stdout.getvalue())
        self.assertIn('"completed": 0', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
