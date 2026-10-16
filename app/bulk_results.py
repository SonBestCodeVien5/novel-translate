"""Bounded bulk result container inspection; importing remains Store-owned."""
import io
import stat
import zipfile

from app.core import DomainError

MAX_FILES = 100
MAX_FILE = 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def inspect_zip(raw):
    """Preflight every ZIP member before returning any result bytes."""
    if not isinstance(raw, bytes) or len(raw) > MAX_TOTAL:
        raise DomainError('ZIP upload exceeds 32 MiB.', 413)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 201:
                raise DomainError('ZIP contains too many entries.', 413)
            names, results, expanded = set(), [], 0
            file_count = 0
            for entry in entries:
                name = entry.filename
                parts = name.rstrip('/').split('/')
                if (not name or entry.orig_filename != name or name in names or name.startswith('/') or '\\' in name or
                        any(part in {'', '.', '..'} for part in parts) or
                        stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1):
                    raise DomainError('ZIP has duplicate, unsafe, encrypted, or symbolic entries.')
                kind = stat.S_IFMT(entry.external_attr >> 16)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise DomainError('ZIP contains a non-regular file.')
                names.add(name)
                if entry.is_dir():
                    continue
                file_count += 1
                if file_count > MAX_FILES + 1:
                    raise DomainError('ZIP contains too many files.', 413)
                expanded += entry.file_size
                if (expanded > MAX_TOTAL or entry.file_size > MAX_FILE or
                        entry.file_size > max(1, entry.compress_size) * 200):
                    raise DomainError('ZIP expanded size or compression ratio exceeds limits.', 413)
                data = archive.read(entry)  # CRC check; never extract to disk.
                if name == 'manifest.json':
                    continue
                if not name.lower().endswith('.json'):
                    raise DomainError('ZIP may contain only result JSON files and manifest.json.')
                results.append((name, data))
            if not results or len(results) > MAX_FILES:
                raise DomainError('ZIP must contain 1 to 100 result JSON files.')
            return results
    except DomainError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise DomainError('Malformed or unsupported ZIP archive.') from exc


def check_upload_total(files):
    if not files or len(files) > MAX_FILES or sum(len(raw) for _, raw in files) > MAX_TOTAL:
        raise DomainError('Upload must contain at most 100 files and 32 MiB.', 413)
