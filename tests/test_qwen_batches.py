import json
import io
from urllib.error import HTTPError
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts/pipeline'))
import qwen_batches as B
import test_qwen_relations as fixtures
from project_budget import configure


class QwenBatches(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QwenProvider()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger = self.fixture.ledger
        self.state = self.fixture.state
        self.work = Path(self.fixture.tmp.name) / 'batches'
        self.work.mkdir()
        self.patch_work = patch.object(B, 'WORK', self.work)
        self.patch_work.start()
        self.addCleanup(self.patch_work.stop)
        self.patch_pause = patch.object(B, 'PAUSE', Path(self.fixture.tmp.name) / 'paused')
        self.patch_pause.start()
        self.addCleanup(self.patch_pause.stop)
        self.patch_region = patch.object(B, 'base_url', return_value=B.SINGAPORE)
        self.patch_region.start()
        self.addCleanup(self.patch_region.stop)
        def state_for_pair(a, b, *_):
            state = json.loads(json.dumps(self.state))
            state['paper_a']['title'] = a
            state['paper_b']['title'] = b
            return state
        self.patch_state = patch.object(B.Q.C, 'make_state', side_effect=state_for_pair)
        self.patch_state.start()
        self.addCleanup(self.patch_state.stop)
        configure(self.ledger, 1, {}, 0)
        B.setup(self.ledger)

    def prepare(self, n=1):
        return B.prepare(self.ledger, [(f'a{i}', f'b{i}') for i in range(n)], {}, {}, {}, n)

    def row(self, local):
        identity = json.loads(self.ledger.db.execute('SELECT requests FROM qwen_batches WHERE id=?', (local,)).fetchone()[0])[0]
        return {'custom_id': identity, 'response': {'status_code': 200, 'body': self.fixture.response({})}}

    def test_bounds_and_project_budget_limit_batch_admission(self):
        state = json.loads(json.dumps(self.state))
        state['paper_a']['title'], state['paper_b']['title'] = 'a0', 'b0'
        bound = B.bound_for(B.payload(state))
        configure(self.ledger, bound * 1.5, {}, 0)
        local = self.prepare(10)
        ids = json.loads(self.ledger.db.execute('SELECT requests FROM qwen_batches WHERE id=?', (local,)).fetchone()[0])
        self.assertEqual(len(ids), 1)
        self.assertAlmostEqual(self.ledger.spent(), bound)
        self.assertLessEqual(self.ledger.spent(), bound * 1.5)

    def test_discounted_usage_is_billed_once_and_result_is_decoded(self):
        local = self.prepare()
        row = self.row(local)
        self.assertTrue(B.ingest(self.ledger, row, {row['custom_id']}))
        self.assertAlmostEqual(self.ledger.spent(), .0000625)
        self.assertFalse(B.ingest(self.ledger, row, {row['custom_id']}))
        self.assertAlmostEqual(self.ledger.spent(), .0000625)
        self.assertIsNone(self.prepare())
        result = json.loads(self.ledger.db.execute('SELECT result FROM calls').fetchone()[0])
        self.assertEqual(result['provider'], 'modelstudio')
        self.assertEqual(result['inference_method'], 'batch')

    def test_ambiguous_submission_retains_budget_and_never_resubmits(self):
        local = self.prepare()
        before = self.ledger.spent()
        sent = []
        def transport(path, **kwargs):
            sent.append(path)
            if path == '/files':
                return {'id': 'file-test'}
            raise TimeoutError()
        with self.assertRaises(RuntimeError):
            B.submit(self.ledger, local, transport)
        with self.assertRaises(RuntimeError):
            B.submit(self.ledger, local, lambda *_args, **_kw: self.fail('resubmitted'))
        self.assertEqual(sent, ['/files', '/batches'])
        self.assertEqual(self.ledger.spent(), before)

    def test_missing_result_rows_keep_reservations(self):
        local = self.prepare(2)
        B.set_job(self.ledger, local, 'in_progress', provider_id='batch-test')
        row = self.row(local)
        def transport(path, **kwargs):
            if path.startswith('/batches/'):
                return {'status': 'completed', 'output_file_id': 'file-test'}
            return (json.dumps(row) + '\n').encode()
        with self.assertRaises(RuntimeError):
            B.collect(self.ledger, transport)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='reserved'").fetchone()[0], 1)

    def test_payload_uses_selected_model_and_bounded_thinking(self):
        p = B.payload(self.state)
        self.assertEqual(p['model'], 'qwen3.7-flash')
        self.assertEqual(p['max_completion_tokens'], 3072)
        self.assertEqual(p['thinking_budget'], 1024)
        self.assertNotIn('reasoning_effort', p)

    def test_beijing_prices_and_dedicated_key_requirement(self):
        with patch.object(B, 'base_url', return_value=B.BEIJING):
            self.assertEqual(B.price(B.MODEL, 2000), (.028, .110))
            with patch.object(B.Q, 'local', return_value=None):
                with self.assertRaises(RuntimeError):
                    B.connection()

    def test_untrusted_batch_endpoint_is_rejected(self):
        self.patch_region.stop()
        with patch.object(B.Q, 'local', return_value='https://example.org/v1'):
            with self.assertRaises(ValueError):
                B.base_url()

    def test_known_unsupported_model_is_not_submitted_again(self):
        local = self.prepare()
        identity = self.row(local)['custom_id']
        self.ledger.finish(identity, None, {}, 0, 'batch_rejected', 'The provided model is not supported by the Batch API.')
        with self.assertRaises(RuntimeError):
            B.require_available(self.ledger, B.MODEL)

    def test_pair_claim_is_atomic_across_workers_with_different_ids(self):
        path = self.ledger.db.execute('PRAGMA database_list').fetchone()[2]
        barrier = threading.Barrier(2, timeout=5)
        def claim(identity):
            local = B.Q.C.Ledger(path, 1)
            try:
                barrier.wait()
                return local.reserve(identity, 'same-a', 'same-b', B.MODEL, self.state, .01, unique_pair=True)
            finally:
                local.db.close()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(claim, ['batch-claim', 'other-worker-claim']))
        self.assertEqual(sum(results), 1)
        self.assertAlmostEqual(self.ledger.spent(), .01)

    def test_billing_rejection_releases_budget_and_explicit_restart_can_resume(self):
        local = self.prepare()
        def rejected(path, **kwargs):
            if path == '/files':
                return {'id': 'file-test'}
            raise HTTPError('https://example.org', 400, 'billing', {}, io.BytesIO(
                b'{"error":{"message":"Access denied, please make sure your account is in good standing."}}'))
        with self.assertRaises(RuntimeError):
            B.submit(self.ledger, local, rejected)
        self.assertEqual(self.ledger.spent(), 0)
        restarted = self.prepare()
        self.assertIsNotNone(restarted)
        self.assertNotEqual(local, restarted)
        self.assertGreater(self.ledger.spent(), 0)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM qwen_batches').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
