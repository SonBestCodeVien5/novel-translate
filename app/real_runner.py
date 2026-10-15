"""File-only resumable runner for immutable real-model v2 batches."""
import argparse
import errno
import uuid
import warnings
from pathlib import Path

from app import bundles
from app import real_bundles as real


def _atomic_write(path, raw):
    try:
        bundles.atomic_write(path, raw)
    except OSError as exc:
        # Drive FUSE may not support directory fsync; verify the published bytes.
        if exc.errno not in (errno.EINVAL, errno.ENOTSUP) or not Path(path).is_file() or Path(path).read_bytes() != raw:
            raise
        warnings.warn('Directory fsync is unsupported; published bytes passed readback, remote durability is unverified.', RuntimeWarning)


def run_manifest(manifest, output_dir, generate):
    real.validate_manifest(manifest)
    output_dir = Path(output_dir)
    manifest_path = output_dir / 'manifest.json'
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_manifest = real.canonical_bytes(manifest)
    if manifest_path.exists():
        if manifest_path.stat().st_size > bundles.MAX_BYTES or manifest_path.read_bytes() != raw_manifest:
            raise real.DomainError('Output directory belongs to a different manifest.')
    known = {chunk['chunk_id']: chunk for chunk in manifest['chunks']}
    # Check every checkpoint before starting generation; any unexpected JSON is suspicious.
    for path in output_dir.glob('*.json'):
        if path == manifest_path:
            continue
        if path.stem not in known or path.stat().st_size > bundles.MAX_BYTES:
            raise real.DomainError('Unexpected or oversized checkpoint file.')
        result = real.validate_result(bundles.load_json(path.read_bytes()), manifest)
        if result['chunk_id'] != path.stem:
            raise real.DomainError('Checkpoint filename does not match its chunk ID.')
    if not manifest_path.exists():
        _atomic_write(manifest_path, raw_manifest)
    completed = {p.stem for p in output_dir.glob('*.json') if p != manifest_path}
    produced = 0
    for chunk in manifest['chunks']:
        if chunk['chunk_id'] in completed:
            continue
        started = real.now()
        try:
            generated = generate(manifest, chunk)
        except Exception as exc:
            diagnostic = {'job_id': manifest['job_id'], 'manifest_hash': real.digest(manifest),
                          'chunk_id': chunk['chunk_id'], 'expected_input_hash': chunk['expected_input_hash'],
                          'status': 'failed', 'error_type': type(exc).__name__,
                          'started_at': started, 'completed_at': real.now()}
            _save_failure(output_dir, chunk, diagnostic)
            raise
        if type(generated) is not dict or generated.get('finish_reason') != 'eos':
            diagnostic = {'job_id': manifest['job_id'], 'manifest_hash': real.digest(manifest),
                          'chunk_id': chunk['chunk_id'], 'expected_input_hash': chunk['expected_input_hash'],
                          'status': 'failed', 'finish_reason': generated.get('finish_reason') if type(generated) is dict else 'invalid',
                          'started_at': started, 'completed_at': real.now()}
            if type(generated) is dict and type(generated.get('translated_text')) is str:
                diagnostic['translated_text'] = generated['translated_text']
            if type(generated) is dict and type(generated.get('output_tokens')) is int:
                diagnostic['output_tokens'] = generated['output_tokens']
            _save_failure(output_dir, chunk, diagnostic)
            raise real.DomainError('Generation was incomplete; diagnostic saved outside completed results.')
        result = real.make_result(manifest, chunk, generated, started, real.now())
        _atomic_write(output_dir / (chunk['chunk_id'] + '.json'), real.canonical_bytes(result))
        produced += 1
    return {'completed': len(completed) + produced, 'total': len(manifest['chunks'])}


def _save_failure(output_dir, chunk, diagnostic):
    attempt = diagnostic['completed_at'].replace(':', '').replace('-', '') + '-' + uuid.uuid4().hex
    _atomic_write(output_dir / 'failed' / (chunk['chunk_id'] + '-' + attempt + '.json'),
                  real.canonical_bytes(diagnostic))


def huggingface_generate(manifest, chunk):
    """Load the exact pinned model on CUDA and run one frozen input."""
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    snap = manifest['snapshot']
    if not torch.cuda.is_available():
        raise real.DomainError('A CUDA GPU is required; CPU fallback is disabled.')
    cache_key = real.digest(snap)
    cached = getattr(huggingface_generate, '_cache', None)
    if cached is None or cached[0] != cache_key:
        tokenizer, tokenizer_commit = real.load_tokenizer(snap['tokenizer_id'], snap['tokenizer_revision'])
        if getattr(tokenizer, 'chat_template', None) != snap['template']:
            raise real.DomainError('Loaded tokenizer template differs from frozen snapshot.')
        if tokenizer_commit != snap['tokenizer_revision']:
            raise real.DomainError('Loaded tokenizer commit does not match snapshot.')
        messages = real._messages(chunk['source_text'], snap)
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        if ids != chunk['input_ids']:
            raise real.DomainError('Loaded tokenizer input IDs differ from frozen batch.')
        dtype = getattr(torch, snap['quantization']['bnb_4bit_compute_dtype'])
        quant = BitsAndBytesConfig(**{**snap['quantization'], 'bnb_4bit_compute_dtype': dtype})
        model = AutoModelForCausalLM.from_pretrained(snap['model_id'], revision=snap['model_revision'],
            trust_remote_code=False, quantization_config=quant, torch_dtype=dtype,
            attn_implementation=snap['parameters']['attention_implementation'], device_map={'': 0})
        model.eval()
        if getattr(model.config, '_commit_hash', None) != snap['model_revision']:
            raise real.DomainError('Loaded model commit does not match snapshot.')
        huggingface_generate._cache = (cache_key, tokenizer, model)
    else:
        _, tokenizer, model = cached
        ids = tokenizer.apply_chat_template(real._messages(chunk['source_text'], snap), tokenize=True,
                                            add_generation_prompt=True)
        if ids != chunk['input_ids']:
            raise real.DomainError('Loaded tokenizer input IDs differ from frozen batch.')
    if getattr(model.config, 'max_position_embeddings', 0) < real.TOTAL_TOKENS:
        raise real.DomainError('Pinned model context is below the frozen total token budget.')
    input_ids = torch.tensor([chunk['input_ids']], dtype=torch.long, device='cuda:0')
    attention_mask = torch.ones_like(input_ids)
    torch.manual_seed(snap['parameters']['seed'])
    with torch.inference_mode():
        output = model.generate(input_ids=input_ids, attention_mask=attention_mask,
                                max_new_tokens=snap['parameters']['max_new_tokens'],
                                do_sample=False, pad_token_id=tokenizer.pad_token_id)
    new_ids = output[0, input_ids.shape[1]:]
    eos = model.generation_config.eos_token_id
    eos = [eos] if type(eos) is int else eos
    finish = 'eos' if len(new_ids) and int(new_ids[-1]) in eos else 'max_tokens'
    if finish != 'eos':
        return {'translated_text': tokenizer.decode(new_ids, skip_special_tokens=True),
                'output_tokens': len(new_ids), 'finish_reason': finish, 'provenance': {}}
    return {'translated_text': tokenizer.decode(new_ids, skip_special_tokens=True),
            'output_tokens': len(new_ids), 'finish_reason': 'eos', 'provenance': real.provenance(manifest)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.manifest.open('rb') as stream:
            raw = stream.read(bundles.MAX_BYTES + 1)
        if len(raw) > bundles.MAX_BYTES:
            parser.error('manifest exceeds maximum size')
        manifest = bundles.load_json(raw)
    except OSError as exc:
        parser.error(f'cannot read manifest: {exc}')
    content_root = Path('/content')
    if content_root.exists():
        drive_root = content_root / 'drive' / 'MyDrive'
        if not drive_root.is_dir() or not args.output_dir.resolve().is_relative_to(drive_root.resolve()):
            parser.error('On Colab, output must be under mounted /content/drive/MyDrive')
    run_manifest(manifest, args.output_dir, huggingface_generate)


if __name__ == '__main__':
    main()
