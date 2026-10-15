import copy
import errno
import io
import json
import sys
from collections import UserDict
from pathlib import Path
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.bundles import DomainError, canonical_bytes, digest, load_json
from benchmarks.p0.runner import (CONFIG, MODELS, QWEN35, apply_model_profile, build_plan, input_ids,
                                  run, validate_corpus, validate_result, write_new)


class Tokenizer:
    chat_template = 'fake-chat-template'

    def encode(self, text, add_special_tokens=False):
        return list(text.encode('utf-8'))

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize and add_generation_prompt
        return self.encode(json.dumps(messages, ensure_ascii=False)) + [1]


class BatchEncodingTokenizer(Tokenizer):
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        return UserDict(input_ids=super().apply_chat_template(messages, tokenize, add_generation_prompt))


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

    def test_batch_encoding_input_ids_drive_plan_count_and_hash(self):
        tokenizer = BatchEncodingTokenizer()
        ids = input_ids(tokenizer, 'A small test.', 'Mira: Mira')
        plan = build_plan(corpus(), tokenizer, MODELS[0], 'a' * 40)
        chunk = plan['chunks'][0]
        actual_ids = input_ids(tokenizer, chunk['source_text'], plan['corpus']['glossary'])
        self.assertEqual(chunk['input_tokens'], len(actual_ids))
        self.assertEqual(chunk['input_hash'], digest(actual_ids))
        self.assertIsInstance(ids, list)

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

    def test_empty_raw_output_cannot_be_checkpointed_as_complete(self):
        def generate(_chunk):
            return {'translated_text': 'Bản dịch giả.', 'raw_output_ids': [], 'finish_reason': 'eos'}
        with self.assertRaises(DomainError):
            run(self.plan, self.output, generate, 1)
        self.assertEqual(list((self.output / 'results').glob('*.json')) if (self.output / 'results').exists() else [], [])

    def test_main_passes_configured_dtype_to_quantizer_and_model_loader(self):
        original_config = copy.deepcopy(CONFIG)
        corpus_path = Path(self.temp.name) / 'corpus.json'
        corpus_path.write_text(json.dumps(corpus()), encoding='utf-8')
        fp16, fp32 = object(), object()
        torch = types.ModuleType('torch')
        torch.float16, torch.float32 = fp16, fp32
        torch.cuda = types.SimpleNamespace(is_available=lambda: True, reset_peak_memory_stats=lambda: None,
            get_device_properties=lambda _index: types.SimpleNamespace(name='mock', total_memory=1),
            synchronize=lambda: None, max_memory_allocated=lambda: 0, max_memory_reserved=lambda: 0)
        torch.version = types.SimpleNamespace(cuda='mock')
        torch.backends = types.SimpleNamespace(cudnn=types.SimpleNamespace(version=lambda: 1))
        quant_args, model_args, plans = [], [], []
        tokenizer = types.SimpleNamespace(chat_template='template', init_kwargs={'revision': 'pin', '_commit_hash': 'a' * 40},
            encode=lambda text, add_special_tokens=False: [1] * len(text),
            apply_chat_template=lambda messages, tokenize, add_generation_prompt: [1] * sum(len(m['content']) for m in messages))
        model = types.SimpleNamespace(config=types.SimpleNamespace(max_position_embeddings=4096, _commit_hash='a' * 40),
                                      generation_config=types.SimpleNamespace(eos_token_id=0), eval=lambda: None)
        transformers = types.ModuleType('transformers')
        transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer)
        transformers.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **kw: model_args.append(kw) or model)
        transformers.BitsAndBytesConfig = lambda **kw: quant_args.append(kw) or kw
        transformers.set_seed = lambda _seed: None
        try:
            with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers}), \
                 patch('benchmarks.p0.runner.importlib.metadata.version', return_value='mock'), \
                 patch('benchmarks.p0.runner.run', side_effect=lambda plan, *_a, **_kw: plans.append(copy.deepcopy(plan))), \
                 redirect_stdout(io.StringIO()):
                for name, dtype in (('float16', fp16), ('float32', fp32)):
                    CONFIG.clear(); CONFIG.update(copy.deepcopy(original_config))
                    CONFIG['quantization']['bnb_4bit_compute_dtype'] = name
                    output = Path(self.temp.name) / name
                    with patch.object(sys, 'argv', ['runner', '--model', MODELS[1], '--revision', 'a' * 40,
                                                     '--corpus', str(corpus_path), '--output', str(output)]):
                        from benchmarks.p0.runner import main as runner_main
                        runner_main()
                    self.assertIs(quant_args[-1]['bnb_4bit_compute_dtype'], dtype)
                    self.assertIs(model_args[-1]['torch_dtype'], dtype)
                    self.assertEqual(plans[-1]['config']['quantization']['bnb_4bit_compute_dtype'], name)
            self.assertNotEqual(digest(plans[0]), digest(plans[1]))
        finally:
            CONFIG.clear(); CONFIG.update(original_config)

    def test_qwen35_profile_mapping_nested_context_and_snapshot(self):
        original = copy.deepcopy(CONFIG)
        qwen35_revision = 'b' * 40
        corpus_path = Path(self.temp.name) / 'corpus.json'
        corpus_path.write_text(json.dumps(corpus()), encoding='utf-8')
        template_kwargs = []
        tokenizer = types.SimpleNamespace(chat_template='template', init_kwargs={'revision': 'pin', '_commit_hash': qwen35_revision},
            encode=lambda text, add_special_tokens=False: [1] * len(text),
            apply_chat_template=lambda messages, tokenize, add_generation_prompt, **kwargs:
                template_kwargs.append(kwargs) or [1] * sum(len(m['content']) for m in messages))
        model = types.SimpleNamespace(config=types.SimpleNamespace(
            text_config=types.SimpleNamespace(max_position_embeddings=4096), _commit_hash=None),
            generation_config=types.SimpleNamespace(eos_token_id=0), eval=lambda: None)
        load_args, plans = [], []
        torch = types.ModuleType('torch')
        torch.float16 = object()
        torch.cuda = types.SimpleNamespace(is_available=lambda: True, reset_peak_memory_stats=lambda: None,
            get_device_properties=lambda _index: types.SimpleNamespace(name='mock', total_memory=1),
            synchronize=lambda: None, max_memory_allocated=lambda: 0, max_memory_reserved=lambda: 0)
        torch.version = types.SimpleNamespace(cuda='mock')
        torch.backends = types.SimpleNamespace(cudnn=types.SimpleNamespace(version=lambda: 1))
        transformers = types.ModuleType('transformers')
        transformers.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer)
        transformers.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *_a, **_kw:
            self.fail('Qwen3.5 must use its text-only model class'))
        transformers.Qwen3_5ForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **kw:
            load_args.append(kw) or (model, {'missing_keys': [], 'mismatched_keys': [], 'error_msgs': []}))
        hub = types.ModuleType('transformers.utils.hub')
        hub.cached_file = lambda _model, _name, revision: f'/cache/snapshots/{revision}/config.json'
        hub.extract_commit_hash = lambda path, _commit: path.split('/snapshots/')[1].split('/')[0]
        utils = types.ModuleType('transformers.utils')
        utils.hub = hub
        transformers.BitsAndBytesConfig = lambda **kw: kw
        transformers.set_seed = lambda _seed: None
        try:
            apply_model_profile(QWEN35)
            self.assertEqual(CONFIG['attention_implementation'], 'sdpa')
            self.assertEqual(CONFIG['quantization'], {'load_in_4bit': True, 'bnb_4bit_quant_type': 'nf4',
                'bnb_4bit_use_double_quant': True, 'bnb_4bit_compute_dtype': 'float16'})
            self.assertEqual(CONFIG['chat_template_kwargs'], {'enable_thinking': False})
            plan = build_plan(corpus(), tokenizer, QWEN35, qwen35_revision)
            self.assertEqual(plan['config'], CONFIG)
            self.assertNotEqual(plan['config'], original)
            self.assertTrue(template_kwargs)
            self.assertTrue(all(kwargs == {'enable_thinking': False} for kwargs in template_kwargs))
            with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers,
                                         'transformers.utils': utils, 'transformers.utils.hub': hub}), \
                 patch('benchmarks.p0.runner.importlib.metadata.version', return_value='mock'), \
                 patch('benchmarks.p0.runner.run', side_effect=lambda p, *_a, **_kw: plans.append(copy.deepcopy(p))), \
                 patch.object(sys, 'argv', ['runner', '--model', QWEN35, '--revision', qwen35_revision,
                                            '--corpus', str(corpus_path), '--output', str(self.output)]), \
                 redirect_stdout(io.StringIO()):
                from benchmarks.p0.runner import main as runner_main
                runner_main()
            self.assertEqual(load_args[0]['key_mapping'], {r'^model\.language_model\.': 'model.'})
            self.assertTrue(load_args[0]['output_loading_info'])
            self.assertEqual(plans[0]['config'], CONFIG)
            self.assertEqual(plans[0]['config']['context_tokens'], 4096)
            self.assertEqual(plans[0]['config']['generation'], {'max_new_tokens': 2048, 'do_sample': False})
            session = next((self.output / 'sessions').glob('*.json'))
            self.assertEqual(load_json(session.read_bytes())['actual_model_commit'], qwen35_revision)
            model.config._commit_hash = 'c' * 40
            with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers,
                                         'transformers.utils': utils, 'transformers.utils.hub': hub}), \
                 patch('benchmarks.p0.runner.importlib.metadata.version', return_value='mock'), \
                 patch.object(sys, 'argv', ['runner', '--model', QWEN35, '--revision', qwen35_revision,
                                            '--corpus', str(corpus_path), '--output', str(self.output)]), \
                 redirect_stdout(io.StringIO()), self.assertRaises(DomainError):
                runner_main()
        finally:
            CONFIG.clear(); CONFIG.update(original)

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
        notebook = json.loads(Path('notebooks/p0_benchmark.ipynb').read_text())
        bootstrap = next(c for c in notebook['cells'] if c['metadata'].get('p0_bootstrap'))
        source = ''.join(bootstrap['source'])
        temporary_root = Path(self.temp.name) / 'bootstrap'
        source = source.replace("Path('/content/p0-code')", 'Path(' + repr(str(temporary_root)) + ')')
        namespace = {}
        exec(compile(source, '<bootstrap>', 'exec'), namespace)
        for name, expected in namespace['SOURCES'].items():
            self.assertEqual((temporary_root / name).read_bytes(), expected.encode('utf-8'))
        code = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertIn('google.colab', code[0])
        self.assertIn('cuda.is_available', code[0])
        self.assertIn("'pip'", code[1])

    def test_notebook_code_syntax(self):
        for path in ('notebooks/p0_benchmark.ipynb', 'notebooks/p0_qwen25_benchmark.ipynb',
                     'notebooks/p0_qwen35_benchmark.ipynb'):
            notebook = json.loads(Path(path).read_text())
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    compile(''.join(cell['source']), '<notebook>', 'exec')

    def test_qwen35_notebook_bootstrap_and_profile_are_portable(self):
        from benchmarks.p0.build_notebook import ROOT, SOURCES, bootstrap_source
        notebook = json.loads(Path('notebooks/p0_qwen35_benchmark.ipynb').read_text())
        bootstrap = next(c for c in notebook['cells'] if c['metadata'].get('p0_bootstrap'))
        self.assertEqual(''.join(bootstrap['source']), bootstrap_source())
        source = ''.join(bootstrap['source'])
        temporary_root = Path(self.temp.name) / 'qwen35-bootstrap'
        source = source.replace("Path('/content/p0-code')", 'Path(' + repr(str(temporary_root)) + ')')
        exec(compile(source, '<bootstrap>', 'exec'), {})
        for name in SOURCES:
            self.assertEqual((temporary_root / name).read_bytes(), (ROOT / name).read_bytes())
        config = ''.join(notebook['cells'][6]['source'])
        self.assertIn("LIMIT = 1", config)
        self.assertIn('apply_model_profile(MODEL)', config)
        self.assertIn("transformers==5.3.0", ''.join(notebook['cells'][2]['source']))
