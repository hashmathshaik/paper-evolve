import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import edge_priority as P


class CitationExpansion(unittest.TestCase):
    def setUp(self):
        self.papers = {
            'a': {'title': 'Original method', 'year': 2018, 'source_url': 'a'},
            'b': {'title': 'Later development', 'year': 2020, 'source_url': 'b'},
            'copy': {'title': 'Original method!', 'year': 2021, 'source_url': 'copy'},
            'sameyear': {'title': 'Contemporary work', 'year': 2020, 'source_url': 'sameyear'},
        }
        self.cites = ({'a': 'sa', 'b': 'sb', 'copy': 'sc', 'sameyear': 'ss'},
                      {'sb': {'sa', 'ss', 'outside'}, 'sc': {'sa'}, 'sa': {'sb'}},
                      {'a': 'oa', 'b': 'ob'}, {'ob': {'oa'}})

    def test_union_deduplicates_providers_and_excludes_versions_and_bad_chronology(self):
        self.assertEqual(P.citation_pairs(self.papers, self.cites, {}), {('a', 'b')})

    def test_citing_context_can_supply_a_link_missing_from_reference_cache(self):
        cites = (self.cites[0], {}, {}, {})
        self.assertEqual(P.citation_pairs(self.papers, cites, {('sb', 'sa'): (['quote'], [], False)}),
                         {('a', 'b')})

    def test_expanded_ranking_includes_outside_knn_and_never_requeues_known_pairs(self):
        class Ledger:
            db = sqlite3.connect(':memory:')
        ledger = Ledger()
        ledger.db.executescript('CREATE TABLE calls(a,b,status,result); CREATE TABLE screens(a,b,decision);')
        self.addCleanup(ledger.db.close)
        with tempfile.TemporaryDirectory() as root, patch.object(P.S, 'setup'), \
                patch('community_edges.load_approved', return_value={}), patch.object(P.H, 'ROOT', Path(root)):
            self.assertEqual(P.rank_candidates(self.papers, {}, self.cites, {}, ledger, limit=0), [])
            rows = P.rank_candidates(self.papers, {}, self.cites, {}, ledger, limit=0, scope='expanded')
            self.assertEqual([(r['a'], r['b']) for r in rows], [('a', 'b')])
            self.assertTrue(rows[0]['citation_backed'])
            ledger.db.execute("INSERT INTO calls VALUES ('a','b','unknown',NULL)")
            self.assertEqual(P.rank_candidates(self.papers, {}, self.cites, {}, ledger, limit=0, scope='expanded'), [])
            self.papers['c'] = {'title': 'Another development', 'year': 2022, 'source_url': 'c'}
            self.cites[0]['c'] = 'sd'
            self.cites[1]['sd'] = {'sa'}
            ledger.db.execute('DELETE FROM calls')
            self.assertEqual(len(P.rank_candidates(self.papers, {}, self.cites, {}, ledger, limit=0, scope='expanded')), 2)
            self.assertEqual(len(P.rank_candidates(self.papers, {}, self.cites, {}, ledger, limit=1, scope='expanded')), 1)


if __name__ == '__main__':
    unittest.main()
