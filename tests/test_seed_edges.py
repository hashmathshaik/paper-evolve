import json
import sys
import unittest
from io import BytesIO
from urllib.error import HTTPError
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts/pipeline'))
import seed_edges as S
import test_qwen_relations as fixtures


class QwenSeed(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QwenProvider()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger = self.fixture.ledger
        self.proposal = {'a': 'a', 'b': 'b', 'state': self.fixture.state,
                         'result': {'related': True, 'types': {'Extends': .95}}}
        self.ledger.db.execute("INSERT INTO calls VALUES ('proposal','a','b',?,?,?,0,'seed_proposed',NULL,NULL)",
                               (S.G.MODEL, json.dumps(self.fixture.state), json.dumps(self.proposal['result'])))
        self.ledger.db.commit()

    def response(self, params):
        # The verifier has source text but does not receive the prior decision.
        self.assertEqual(params['model'], 'qwen3.7-plus')
        prompt = json.loads(params['messages'][1]['content'])
        self.assertNotIn('types', prompt['pairs'][0])
        self.assertNotIn('proposal', prompt['pairs'][0])
        raw = self.fixture.response(params)
        decision = json.loads(raw['choices'][0]['message']['content'])
        raw['model'] = 'qwen3.7-plus'
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': [{**decision, 'pair_id': 'p0'}]})
        return raw

    def test_qwen_only_blind_verification_publishes_agreed_source_backed_type(self):
        verdict = S.verify_proposal(self.ledger, self.proposal, self.response)
        self.assertEqual(verdict['status'], 'verified')
        self.assertEqual(verdict['accepted'], 1)
        record = json.loads(self.ledger.db.execute("SELECT result FROM calls WHERE status='complete'").fetchone()[0])
        self.assertEqual(record['verification']['review_model'], 'qwen3.7-plus')
        self.assertFalse(record['verification']['human_verified'])
        self.assertAlmostEqual(self.ledger.spent(), .0016)

    def test_disagreement_remains_unpublished(self):
        self.proposal['result']['types'] = {'Transfers': .95}
        verdict = S.verify_proposal(self.ledger, self.proposal, self.response)
        self.assertEqual(verdict['accepted'], 0)
        record = json.loads(self.ledger.db.execute("SELECT result FROM calls WHERE status='complete'").fetchone()[0])
        self.assertFalse(record['related'])
        self.assertEqual(record['types'], {})

    def test_unready_sources_and_budget_limit_never_call_verifier(self):
        self.proposal['state']['source_evidence']['status'] = 'needs_context'
        with self.assertRaises(ValueError):
            S.verify_proposal(self.ledger, self.proposal, lambda _: self.fail('Missing source sent'))
        self.proposal['state']['source_evidence']['status'] = 'ready'
        self.ledger.budget = .00001
        verdict = S.verify_proposal(self.ledger, self.proposal, lambda _: self.fail('Over budget'))
        self.assertEqual(verdict['status'], 'budget_limited')

    def test_pending_proposal_itself_is_not_a_published_comparison(self):
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='complete'").fetchone()[0], 0)
        group = S.G.reserve_group(self.ledger, [('a', 'b', self.fixture.state)], 1)
        self.assertEqual(group, 'cached')

    def test_gateway_timeout_is_held_and_quarantined_without_stopping_other_pairs(self):
        def gateway(_):raise HTTPError('https://example.org',504,'Gateway Timeout',{},None)
        result=S.process_review(self.ledger,('verify',self.proposal),lambda:False,review_transport=gateway)
        self.assertEqual(result['quarantined_requests'],1)
        self.assertNotIn('halt',result)
        self.assertGreater(self.ledger.spent(),0)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='group_unknown'").fetchone()[0],1)
        resumed=S.verify_proposal(self.ledger,self.proposal,lambda _:self.fail('Uncertain request resent'))
        self.assertEqual(resumed['status'],'cached')

    def test_authentication_error_remains_a_global_stop(self):
        def unauthorized(_):raise HTTPError('https://example.org',401,'Unauthorized',{},None)
        result=S.process_review(self.ledger,('verify',self.proposal),lambda:False,review_transport=unauthorized)
        self.assertEqual(result['halt'],'provider_http_401')
        self.assertEqual(self.ledger.spent(),0)

    def test_provider_content_rejection_skips_pair_without_stopping_queue(self):
        def filtered(_):
            body = json.dumps({'error': {'code': 'data_inspection_failed', 'message': 'private request text'}}).encode()
            raise HTTPError('https://example.org',400,'Bad Request',{},BytesIO(body))
        result=S.process_review(self.ledger,('verify',self.proposal),lambda:False,review_transport=filtered)
        self.assertNotIn('halt',result)
        self.assertEqual(result['quarantined_requests'],1)
        self.assertEqual(result['accepted_predictions'],0)
        usage=self.ledger.db.execute("SELECT usage FROM calls WHERE status='group_rejected'").fetchone()[0]
        self.assertIn('data_inspection_failed',usage)
        self.assertNotIn('private request text',usage)
        self.assertEqual(self.ledger.spent(),0)


if __name__ == '__main__':
    unittest.main()
