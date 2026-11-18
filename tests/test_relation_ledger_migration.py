import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts/pipeline'))
from relation_core import Ledger
from project_budget import configure, configure_edges
from migrate_relation_ledger import migrate


class LedgerMigration(unittest.TestCase):
    def test_migration_keeps_every_charge_reservation_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, archive = root / 'old.sqlite3', root / 'relations.sqlite3', root / 'archive.sqlite3'
            ledger = Ledger(source, 30)
            configure(ledger, 50, {'preparation': 17.5}, 2)
            configure_edges(ledger, 30)
            ledger.reserve('finished', 'a', 'b', 'old-provider', {'evidence': 'kept'}, .5)
            ledger.finish('finished', {'related': False}, {'tokens': 42}, .25)
            ledger.reserve('uncertain', 'c', 'd', 'qwen', {}, .75)
            ledger.finish('uncertain', None, {}, .75, 'unknown')
            before = ledger.project_snapshot()
            ledger.db.close()
            report = migrate(source, target, archive)
            self.assertFalse(source.exists())
            self.assertTrue(archive.exists())
            self.assertEqual(report['calls'], 2)
            resumed = Ledger(target, 500)
            self.assertEqual(resumed.spent(), 1)
            self.assertEqual(resumed.project_snapshot()['relation_ceiling_usd'], 30)
            self.assertFalse(resumed.reserve('uncertain', 'c', 'd', 'qwen', {}, .01))
            self.assertEqual(json.loads(resumed.db.execute("SELECT state FROM calls WHERE id='finished'").fetchone()[0]), {'evidence': 'kept'})
            self.assertFalse(resumed.reserve('over-budget', 'e', 'f', 'qwen', {}, 29.01))

    def test_existing_destination_never_overwrites_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Ledger(root / 'source.sqlite3', 30)
            original.db.close()
            target = root / 'target.sqlite3'
            target.write_text('do not replace')
            with self.assertRaises(ValueError):
                migrate(root / 'source.sqlite3', target, root / 'archive.sqlite3')
            self.assertEqual(target.read_text(), 'do not replace')

    def test_shared_core_has_no_provider_client_or_credential_loader(self):
        import relation_core as core
        self.assertFalse(hasattr(core, 'load_key'))
        self.assertFalse(hasattr(core, 'classify'))
        root = Path(__file__).parents[1]
        for path in (root / 'scripts').glob('*.py'):
            source = path.read_text()
            self.assertNotIn('api.anthropic.com', source, str(path))
            self.assertNotIn('ANTHROPIC_API_KEY', source, str(path))


if __name__ == '__main__':
    unittest.main()
