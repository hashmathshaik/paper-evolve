import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import qwen_grouped_edges as G
import test_qwen_relations as fixtures
from project_budget import configure_edges


class GroupAccounting(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QwenProvider()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger = self.fixture.ledger

    def group(self):
        return G.reserve_group(self.ledger, [('a', 'b', self.fixture.state), ('c', 'd', self.fixture.state)], 1)

    def response(self, params):
        raw = self.fixture.response(params)
        decision = json.loads(raw['choices'][0]['message']['content'])
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': [{**decision, 'pair_id': 'p1'}, {**decision, 'pair_id': 'p0'}]})
        return raw

    def test_shuffled_decisions_charge_parent_once_and_keep_exact_pair_evidence(self):
        group = self.group()
        result = G.review_group(self.ledger, group, self.response)
        self.assertEqual((result['valid'], result['accepted']), (2, 2))
        self.assertAlmostEqual(self.ledger.spent(), .000125)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='complete' AND cost=0").fetchone()[0], 2)
        self.assertEqual(G.reserve_group(self.ledger, [('a', 'b', self.fixture.state)], 1), 'cached')

    def test_duplicate_or_unknown_pair_ids_accept_nothing(self):
        group = self.group()
        raw = self.response({})
        rows = json.loads(raw['choices'][0]['message']['content'])['decisions']
        rows[1]['pair_id'] = rows[0]['pair_id']
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': rows})
        result = G.review_group(self.ledger, group, lambda _: raw)
        self.assertEqual(result['valid'], 0)
        self.assertGreater(self.ledger.spent(), 0)

    def test_missing_pair_is_invalid_without_losing_valid_sibling(self):
        group = self.group()
        raw = self.response({})
        rows = json.loads(raw['choices'][0]['message']['content'])['decisions']
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': rows[:1]})
        result = G.review_group(self.ledger, group, lambda _: raw)
        self.assertEqual(result['valid'], 1)
        self.assertEqual(self.ledger.db.execute("SELECT status FROM calls WHERE a='a'").fetchone()[0], 'invalid')

    def test_ambiguous_timeout_keeps_bound_and_prevents_duplicate_retry(self):
        group = self.group()
        def timeout(_):
            raise TimeoutError()
        result = G.review_group(self.ledger, group, timeout)
        self.assertEqual(result['status'], 'group_unknown')
        self.assertAlmostEqual(self.ledger.spent(), group['bound'])
        self.assertEqual(G.reserve_group(self.ledger, [('a', 'b', self.fixture.state)], 1), 'cached')

    def test_persisted_edge_ceiling_applies_to_resumed_group_worker(self):
        configure_edges(self.ledger, .00001)
        self.assertEqual(self.group(), 'budget_limited')
        self.assertEqual(self.ledger.spent(), 0)

    def test_cache_discount_is_charged_only_for_reported_hits(self):
        group = self.group()
        raw = self.response({})
        raw['usage']['prompt_tokens_details'] = {'cached_tokens': 1000}
        G.review_group(self.ledger, group, lambda _: raw)
        self.assertAlmostEqual(self.ledger.spent(), .000101)

    def test_no_cross_pair_or_invented_source_ids(self):
        group = self.group()
        raw = self.response({})
        rows = json.loads(raw['choices'][0]['message']['content'])['decisions']
        rows[0]['evidence_ids'] = ['a_abstract:0', 'b_citation_99:0']
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': rows})
        result = G.review_group(self.ledger, group, lambda _: raw)
        self.assertEqual(result['valid'], 1)

    def test_truncated_numeric_loop_is_quarantined_and_fully_billed(self):
        group = self.group()
        raw = self.response({})
        raw['choices'][0]['finish_reason'] = 'length'
        raw['usage']['completion_tokens'] = 8195
        result = G.review_group(self.ledger, group, lambda _: raw)
        self.assertEqual(result['valid'], 0)
        self.assertAlmostEqual(self.ledger.spent(), (2000 * .03 + 8195 * .13) / 1e6)
        self.assertIn('Truncated', result['diagnostics']['response'])
        confidence = group['params']['response_format']['json_schema']['schema']['properties']['decisions']['items']['properties']['relations']['items']['properties']['confidence']
        self.assertIn('enum', confidence)


if __name__ == '__main__':
    unittest.main()
