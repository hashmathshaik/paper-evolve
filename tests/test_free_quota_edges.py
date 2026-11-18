import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts/pipeline'))
import free_quota_edges as F
import test_qwen_relations as fixtures


class FreeQuotaEdges(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QwenProvider()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger = self.fixture.ledger
        self.state = self.fixture.state
        F.setup(self.ledger)

    def test_all_seven_models_have_portable_payload(self):
        for model in F.MODELS:
            params = F.payload(self.state, model)
            self.assertEqual(params['model'], model)
            self.assertEqual(params['response_format'], {'type': 'json_object'})
            if model.startswith('qwen'):
                self.assertEqual(params['thinking_budget'], 1024)
                self.assertNotIn('reasoning_effort', params)
            else:
                self.assertEqual(params['reasoning_effort'], 'low')
                self.assertNotIn('thinking_budget', params)
            self.assertIn('schema', params['messages'][0]['content'])

    def test_completed_pair_not_resent_when_switching_model(self):
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'kimi-k3', self.fixture.response), 'accepted')
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'glm-5.3', lambda _: self.fail('duplicate')), 'cached')
        self.assertEqual(self.ledger.spent(), 0)
        row = json.loads(self.ledger.db.execute('SELECT result FROM calls').fetchone()[0])
        self.assertEqual(row['provider'], 'modelstudio')
        self.assertTrue(row['free_quota_only'])

    def test_exhausted_model_releases_pair_for_next_model(self):
        def exhausted(_):
            raise HTTPError('https://example.org', 403, 'quota', {}, io.BytesIO(b'{"error":{"code":"AllocationQuota.FreeTierOnly"}}'))
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'kimi-k3', exhausted), 'quota_exhausted')
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'glm-5.3', self.fixture.response), 'accepted')
        self.assertEqual(self.ledger.spent(), 0)

    def test_unknown_outcome_not_resent_on_another_model(self):
        def unknown(_):
            raise TimeoutError()
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'kimi-k3', unknown), 'unknown')
        self.assertEqual(F.review(self.ledger, 'a', 'b', self.state, 'glm-5.3', lambda _: self.fail('resent')), 'cached')

    def test_abstract_fallback_is_labeled_and_requires_both_sources(self):
        state = {k: v for k, v in self.state.items() if k != 'source_evidence'}
        def response(params):
            self.assertIn('one b_abstract option', params['messages'][0]['content'])
            raw = self.fixture.response(params)
            decision = json.loads(raw['choices'][0]['message']['content'])
            decision['evidence_ids'] = ['a_abstract:0', 'b_abstract:0']
            raw['choices'][0]['message']['content'] = json.dumps(decision)
            return raw
        self.assertEqual(F.review(self.ledger, 'a', 'b', state, 'kimi-k3', response), 'accepted')
        result = json.loads(self.ledger.db.execute('SELECT result FROM calls').fetchone()[0])
        self.assertEqual(result['quality_tier'], 'abstract_only_prediction')

    def test_expired_or_unprotected_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'models.json'
            now = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
            config = {'verified_at': now.isoformat(), 'region': 'ap-southeast-1', 'models': [
                {'model': 'kimi-k3', 'expires': '2026-11-16', 'remaining_tokens': 1000000, 'stop_on_exhaust': False}]}
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                F.load_config(path, now)
            config['models'][0]['stop_on_exhaust'] = True
            path.write_text(json.dumps(config))
            self.assertEqual(len(F.load_config(path, now)), 1)
            with self.assertRaises(ValueError):
                F.load_config(path, datetime(2026, 11, 16, tzinfo=timezone.utc))

    def test_seven_workers_claim_each_pair_only_once(self):
        path = self.ledger.db.execute('PRAGMA database_list').fetchone()[2]
        def run(model):
            ledger = F.Q.C.Ledger(path, 50)
            try:
                return F.review(ledger, 'a', 'b', self.state, model, self.fixture.response)
            finally:
                ledger.db.close()
        with ThreadPoolExecutor(7) as pool:
            results = list(pool.map(run, F.MODELS))
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(results.count('cached'), 6)

    def test_singleton_array_decodes_without_changing_evidence(self):
        content = self.fixture.response({})['choices'][0]['message']['content']
        wrapped = json.dumps([json.loads(content)])
        result = F.decode(wrapped, self.state)
        self.assertTrue(result['singleton_array_unwrapped'])
        self.assertEqual(result['types'], {'Extends': .95})
        with self.assertRaises(ValueError):
            F.decode(json.dumps([json.loads(content), json.loads(content)]), self.state)

    def test_recovery_reuses_saved_output_without_a_new_request(self):
        def malformed(params):
            raw = self.fixture.response(params)
            raw['choices'][0]['message']['content'] = json.dumps([json.loads(raw['choices'][0]['message']['content'])])
            return raw
        # Simulate an earlier parser that rejected the same saved singleton JSON.
        F.review(self.ledger, 'a', 'b', self.state, 'kimi-k3', malformed)
        identity = self.ledger.db.execute('SELECT id FROM calls').fetchone()[0]
        content = malformed({})['choices'][0]['message']['content']
        self.ledger.db.execute('INSERT INTO free_invalid_output VALUES (?,?)', (identity, json.dumps(content)))
        self.ledger.db.execute("UPDATE calls SET status='invalid',result=NULL,error='Invalid output: AttributeError' WHERE id=?", (identity,))
        self.ledger.db.commit()
        result = F.recover_saved(self.ledger, 'kimi-k3')
        self.assertEqual(result, {'recovered': 1, 'accepted': 1, 'new_requests': 0})
        self.assertEqual(self.ledger.spent(), 0)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM calls').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
