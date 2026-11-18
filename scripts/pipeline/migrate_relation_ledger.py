"""Move a stopped worker's SQLite ledger without changing history or budgets."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def fingerprint(db):
    result = hashlib.sha256()
    for line in db.iterdump():
        result.update(line.encode())
        result.update(b'\n')
    return result.hexdigest()


def migrate(source, destination, archive):
    source, destination, archive = map(Path, (source, destination, archive))
    if not source.is_file():
        raise ValueError('Source ledger is missing.')
    if destination.exists() or archive.exists() or source.resolve() == destination.resolve():
        raise ValueError('Refusing to overwrite an existing ledger or archive.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.migration.sqlite3')
    if temporary.exists():
        raise ValueError('A previous migration needs reconciliation.')
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
        before = fingerprint(original)
        with sqlite3.connect(temporary) as copied:
            original.backup(copied)
            if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or fingerprint(copied) != before:
                raise ValueError('Ledger contents failed migration verification.')
            rows, cost = copied.execute('SELECT count(*),COALESCE(SUM(cost),0) FROM calls').fetchone()
            budgets = {name: copied.execute('SELECT * FROM ' + name).fetchall()
                       for name in ('project_budget', 'relation_budget')}
    temporary.replace(destination)
    # Keep the original file and any SQLite sidecars for recovery. The new
    # ledger is a standalone SQLite backup and does not depend on these files.
    source.rename(archive)
    for suffix in ('-wal', '-shm'):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists():sidecar.rename(Path(str(archive) + suffix))
    report = {'source_archive': str(archive), 'destination': str(destination),
              'content_sha256': before, 'calls': rows, 'cost_or_reservations_usd': cost,
              'budgets': budgets}
    destination.with_suffix('.migration.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--destination', type=Path, required=True)
    ap.add_argument('--archive', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(migrate(args.source.resolve(), args.destination.resolve(), args.archive.resolve())))


if __name__ == '__main__':
    main()
