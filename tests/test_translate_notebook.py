import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from scripts.build_translate_notebook import SOURCES, bootstrap_source


def test_translate_notebook_bootstrap_matches_sources_and_is_clean():
    notebook = json.loads(Path('notebooks/translate.ipynb').read_text(encoding='utf-8'))
    bootstrap = next(cell for cell in notebook['cells'] if cell['metadata'].get('translate_bootstrap'))
    source = ''.join(bootstrap['source'])
    temp_root = Path(tempfile.mkdtemp())
    source = source.replace("Path('/content/novel-translate-code')", f"Path({str(temp_root / 'repo')!r})")
    namespace = {}
    loaded = sys.modules.pop('app.real_runner', None)
    try:
        exec(source, namespace)
    finally:
        if loaded is not None:
            sys.modules['app.real_runner'] = loaded
    assert namespace['SOURCE_HASHES'] == {
        name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in SOURCES}
    for cell in notebook['cells']:
        assert cell.get('outputs', []) == []
        assert cell.get('execution_count') is None
        if cell['cell_type'] == 'code':
            ast.parse(''.join(cell['source']))
    all_code = '\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code')
    assert "'transformers': '5.3.0'" in all_code and "'accelerate': '1.11.0'" in all_code
    assert "'bitsandbytes': '0.48.2'" in all_code
    assert 'sqlite' not in all_code.lower()
    assert 'LIMIT = None' in all_code and 'main(RUN_ARGS)' in all_code
