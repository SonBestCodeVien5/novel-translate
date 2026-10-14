import copy
import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.bundles import DomainError, canonical_bytes, digest, load_json
from benchmarks.p0.runner import CONFIG, MODELS, build_plan, input_ids, run, validate_corpus, validate_result, write_new


class Tokenizer:
    chat_template = 'fake-chat-template'

    def encode(self, text, add_special_tokens=False):
        return list(text.encode('utf-8'))

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize and add_generation_prompt
        return self.encode(json.dumps(messages, ensure_ascii=False)) + [1]


def corpus():
    return {'schema_version': 1, 'corpus_id': 'small-original-fixture',
            'provenance': 'Original fictional test text written for this test.', 'glossary': 'Mira: Mira',
            'chapters': [{'id': f'ch{i:02d}', 'title': 'Test', 'tags': ['dialogue'],
                          'text': 'Mira looked up. “Hello!”\n\n' + 'A cloud drifted. ' * 80} for i in range(1, 6)]}


class P0Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'run'
        self.plan = build_plan(corpus(), Tokenizer(), MODELS[0], 'a' * 40)
        self.calls = 0

    def generate(self, chunk):
        self.calls += 1
        return {'translated_text': 'Bản dịch giả.', 'raw_output_ids': [10, 2], 'finish_reason': 'eos'}

    def test_exact_coverage_and_actual_budgets(self):
        for chapter in self.plan['corpus']['chapters']:
            chunks = [c for c in self.plan['chunks'] if c['chapter_id'] == chapter['id']]
            self.assertEqual(''.join(c['source_text'] for c in chunks), chapter['text'])
            end = 0
            for chunk in chunks:
                self.assertEqual(chunk['source_start'], end)
                end = chunk['source_end']
                self.assertEqual(chunk['source_text'], chapter['text'][chunk['source_start']:end])
                self.assertLessEqual(len(Tokenizer().encode(chunk['source_text'])), CONFIG['source_tokens'])
                self.assertLessEqual(chunk['input_tokens'] + CONFIG['generation']['max_new_tokens'], CONFIG['context_tokens'])
        broken = corpus(); broken['glossary'] = 'x' * 2100
        with self.assertRaises(DomainError):
            build_plan(broken, Tokenizer(), MODELS[0], 'a' * 40)

    def test_resume_preserves_machine_and_manual_files(self):
        run(self.plan, self.output, self.generate, 1)
        first = next((self.output / 'results').glob('*.json'))
        raw = first.read_bytes()
        manual = self.output / 'manual.txt'; manual.write_text('human correction')
        result = run(self.plan, self.output, self.generate)
        self.assertEqual(self.calls, len(self.plan['chunks']))
        self.assertEqual(result['technical_complete'], len(self.plan['chunks']))
        self.assertFalse(result['quality_approved'])
        self.assertEqual(first.read_bytes(), raw)
        self.assertEqual(manual.read_text(), 'human correction')

    def test_resume_results_link_to_their_actual_session(self):
        first_session, second_session = 'a' * 32, 'b' * 32
        run(self.plan, self.output, self.generate, 1, session_id=first_session)
        run(self.plan, self.output, self.generate, 1, session_id=second_session)
        results = [load_json(p.read_bytes()) for p in sorted((self.output / 'results').glob('*.json'))]
        self.assertEqual([r['session_id'] for r in results], [first_session, second_session])
        unknown = self.output / 'unknown'
        run(self.plan, unknown, self.generate, 1)
        result = load_json(next((unknown / 'results').glob('*.json')).read_bytes())
        self.assertIsNone(result['session_id'])
        result['session_id'] = 'invented'
        result['checksum'] = digest({k: v for k, v in result.items() if k != 'checksum'})
        with self.assertRaises(DomainError):
            validate_result(result, self.plan['chunks'][0], digest(self.plan))

    def test_changed_source_and_config_conflict(self):
        run(self.plan, self.output, self.generate, 1)
        for field in ('corpus', 'config', 'template'):
            altered = copy.deepcopy(self.plan)
            altered[field] = {'changed': True}
            with self.assertRaises(DomainError):
                run(altered, self.output, self.generate)
        self.assertEqual(self.calls, 1)

    def test_corrupt_json_checksum_and_stale_input(self):
        run(self.plan, self.output, self.generate, 1)
        path = next((self.output / 'results').glob('*.json'))
        original = path.read_bytes()
        for modification in ('json', 'checksum', 'input'):
            result = load_json(original)
            if modification == 'json':
                path.write_bytes(b'{')
            else:
                if modification == 'checksum':
                    result['translated_text'] += 'changed'
                else:
                    result['input_hash'] = '0' * 64
                    result['checksum'] = digest({k: v for k, v in result.items() if k != 'checksum'})
                path.write_bytes(canonical_bytes(result))
            with self.assertRaises(DomainError):
                run(self.plan, self.output, self.generate)
        self.assertEqual(self.calls, 1)

    def test_incomplete_empty_and_error_stop_and_cannot_resume_skip(self):
        for index, payload in enumerate(({'translated_text': 'partial', 'raw_output_ids': [10], 'finish_reason': 'max_tokens'},
                                         {'translated_text': '', 'raw_output_ids': [2], 'finish_reason': 'eos'}, None)):
            output = self.output / str(index)
            def generate(chunk):
                if payload is None:
                    raise RuntimeError('simulated OOM')
                return payload
            with self.assertRaises(DomainError):
                run(self.plan, output, generate)
            files = list((output / 'results').glob('*.json'))
            self.assertEqual(len(files), 1)
            result = load_json(files[0].read_bytes())
            self.assertIn(result['status'], ('needs_review', 'failed'))
            with self.assertRaises(DomainError):
                run(self.plan, output, self.generate)
        self.assertEqual(self.calls, 0)

    def test_drive_unsupported_directory_fsync_verifies_readback(self):
        import os
        original = os.fsync
        count = 0
        def fsync(descriptor):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError(errno.EINVAL, 'directory fsync unsupported')
            return original(descriptor)
        with patch('benchmarks.p0.runner.os.fsync', side_effect=fsync):
            write_new(self.output / 'check.json', {'checksum': 'test'})
        self.assertEqual(load_json((self.output / 'check.json').read_bytes()), {'checksum': 'test'})

    def test_smoke_scope_and_whole_chapter_measurements(self):
        sample = corpus()
        sample.update(schema_version=2, mode='smoke')
        sample['chapters'] = sample['chapters'][:2]
        plan = build_plan(sample, Tokenizer(), MODELS[0], 'a' * 40)
        result = run(plan, self.output, self.generate)
        self.assertEqual(result['mode'], 'smoke')
        self.assertFalse(result['benchmark_complete'])
        self.assertFalse(result['quality_approved'])
        for chapter, measurement in zip(sample['chapters'], plan['chapter_measurements']):
            tokens = len(input_ids(Tokenizer(), chapter['text'], sample['glossary']))
            self.assertEqual(measurement['full_input_tokens'], tokens)
            self.assertEqual(measurement['exceeds_context'], tokens + 2048 > 4096)
        for mode in ('full', True, 'other'):
            sample['mode'] = mode
            with self.assertRaises(DomainError):
                validate_corpus(sample)
        sample['mode'] = 'smoke'; sample['unknown'] = 1
        with self.assertRaises(DomainError):
            validate_corpus(sample)

    def test_portable_notebook_bootstrap_matches_sources_and_runs_offline(self):
        from benchmarks.p0.build_notebook import SOURCES, ROOT, refresh
        notebook = json.loads(Path('notebooks/p0_benchmark.ipynb').read_text())
        self.assertEqual(refresh(copy.deepcopy(notebook)), notebook)
        bootstrap = next(c for c in notebook['cells'] if c['metadata'].get('p0_bootstrap'))
        source = ''.join(bootstrap['source'])
        temporary_root = Path(self.temp.name) / 'bootstrap'
        source = source.replace("Path('/content/p0-code')", 'Path(' + repr(str(temporary_root)) + ')')
        namespace = {}
        exec(compile(source, '<bootstrap>', 'exec'), namespace)
        for name in SOURCES:
            self.assertEqual((temporary_root / name).read_bytes(), (ROOT / name).read_bytes())
        code = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertIn('google.colab', code[0])
        self.assertIn('cuda.is_available', code[0])
        self.assertIn("'pip'", code[1])

    def test_notebook_code_syntax(self):
        notebook = json.loads(Path('notebooks/p0_benchmark.ipynb').read_text())
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                compile(''.join(cell['source']), '<notebook>', 'exec')
