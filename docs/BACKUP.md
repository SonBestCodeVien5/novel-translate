# Local backup and restore

The backup contains `library.sqlite3` plus files in `sources`, `batches`,
`results`, `rejected`, `real-batches`, and `real-results`. Credentials, logs,
Colab CLI state, prior backups, and other user directories are excluded.

Create a version 1 ZIP outside the data directory:

```sh
.venv/bin/python scripts/backup.py create --data-dir data --output /safe/path/library.zip
```

Restore only into a path that does not already exist:

```sh
.venv/bin/python scripts/backup.py restore --archive /safe/path/library.zip --target /safe/path/restored-data
```

The archive manifest lists each file's relative path, byte size, and SHA-256.
Creation holds a SQLite writer lock and snapshots through SQLite's backup API,
then checks database integrity, source hashes, and stored batch and result
references. It accepts the six-table v1 schema, or the same schema with all four
real-job tables and an optional `book_glossaries` table. A partial real-job table
group, unknown table, trigger, or view is rejected. Backups preserve the source
schema without migrating it; opening a restored v1 library with the app applies
the app's additive schema creation. Restore verifies every file before publishing
the new directory, then runs SQLite integrity and foreign-key checks. Existing
targets and outputs are never overwritten.

Limits: 100,000 archive entries, 512 MiB per entry and compressed archive, and
2 GiB total expanded data. Version 1 does not include unrelated files in `data`
or guarantee a backup when the source database or a referenced app asset is
already missing or inconsistent.

Atomic no-overwrite restore currently requires Linux `renameat2`; on platforms
without that syscall, restore fails closed without publishing the target.
