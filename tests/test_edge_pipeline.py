import json
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts/pipeline'))
import edge_pipeline as P
import seed_edges as S
import test_qwen_relations as fixtures
from project_budget import configure_edges


class ParallelEdgePipeline(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QwenProvider()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger = self.fixture.ledger
        self.path = self.ledger.db.execute('PRAGMA database_list').fetchone()[2]
        self.rows = [{'a': f'a{i}', 'b': f'b{i}'} for i in range(8)]

    def state(self, row):
        state = json.loads(json.dumps(self.fixture.state))
        state['paper_a']['title'] = row['a']
        state['paper_b']['title'] = row['b']
        return state

    def source(self, row):return row, self.state(row)

    def factory(self):return S.P.H.Ledger(self.path, self.ledger.budget)

    def response(self, params):
        raw = self.fixture.response(params)
        decision = json.loads(raw['choices'][0]['message']['content'])
        raw['model'] = params['model']
        raw['choices'][0]['message']['content'] = json.dumps({'decisions': [{**decision, 'pair_id': 'p0'}]})
        return raw

    def test_eight_real_review_pipelines_overlap_without_changing_evidence_checks(self):
        barrier = threading.Barrier(8, timeout=5)
        def proposal(params):
            barrier.wait()
            return self.response(params)
        def process(ledger, job, stop):
            return S.process_review(ledger, job, stop, proposal, self.response)
        events = list(P.events(self.rows, [], self.source, process, self.factory,
                               workers=8, source_workers=2))
        results = [r for r in events if r['kind'] == 'model']
        self.assertEqual(sum(r.get('reviewed', 0) for r in results), 8)
        self.assertEqual(sum(r.get('accepted_predictions', 0) for r in results), 8)
        self.assertFalse(any(r.get('halt') for r in results))
        self.assertAlmostEqual(self.ledger.spent(), 8 * (.000125 + .0016))
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='seed_proposed'").fetchone()[0], 8)

    def test_slow_first_pdf_does_not_block_a_ready_second_paper(self):
        release = threading.Event()
        def source(row):
            if row['a'] == 'a0' and not release.wait(5):raise RuntimeError('Head-of-line source blocking')
            return self.source(row)
        def process(ledger, job, stop):
            if job[1][0][0] == 'a1':release.set()
            return {'reviewed': 1}
        events = list(P.events(self.rows[:2], [], source, process, self.factory,
                               workers=2, source_workers=2))
        self.assertTrue(release.is_set())
        self.assertFalse(any(r['kind'] == 'source_error' for r in events))
        self.assertEqual(sum(r.get('reviewed', 0) for r in events), 2)

    def test_duplicate_pair_is_sent_only_once_across_connections(self):
        counts = {S.G.MODEL: 0, S.REVIEW_MODEL: 0}
        lock = threading.Lock()
        def transport(params):
            with lock:counts[params['model']] += 1
            return self.response(params)
        def process(ledger, job, stop):return S.process_review(ledger, job, stop, transport, transport)
        events = list(P.events([self.rows[0]] * 16, [], self.source, process, self.factory,
                               workers=8, source_workers=4))
        self.assertEqual(counts, {S.G.MODEL: 1, S.REVIEW_MODEL: 1})
        self.assertEqual(sum(r.get('accepted_predictions', 0) for r in events), 1)

    def test_parallel_budget_limit_drains_unknown_requests_without_overbooking(self):
        state = self.state(self.rows[0])
        params = S.G.payload([('a0', 'b0', state)])
        upper = len(json.dumps(params, ensure_ascii=False).encode()) + 8192
        pin, pout = S.G.Q.price(S.G.MODEL, upper)
        bound = (upper * pin + (S.G.MAX_OUTPUT + 16) * pout) / 1e6
        configure_edges(self.ledger, bound * 2 + .0000001)
        release = threading.Event()
        sent = []
        def unknown(params):
            sent.append(params)
            if not release.wait(5):raise AssertionError('Budget stop did not drain admitted calls')
            raw = self.response(params)
            raw['usage'] = {}
            return raw
        def process(ledger, job, stop):return S.process_review(ledger, job, stop, unknown, self.response)
        outcomes = []
        for event in P.events(self.rows, [], self.source, process, self.factory,
                               workers=8, source_workers=4):
            outcomes.append(event)
            if event.get('halt') == 'budget_limited':release.set()
        self.assertTrue(release.is_set())
        self.assertEqual(len(sent), 2)
        self.assertAlmostEqual(self.ledger.spent(), 2 * bound)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='reserved'").fetchone()[0], 0)

    def test_operator_pause_stops_admission_and_accounts_for_inflight_work(self):
        stopping = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        calls = []
        def process(ledger, job, stop):
            a, b, state = job[1][0]
            self.assertTrue(ledger.reserve(a, a, b, 'qwen', state, .1))
            with lock:
                calls.append(a)
                if len(calls) == 2:
                    stopping.set()
                    release.set()
            if not release.wait(5):raise AssertionError('In-flight work was not drained')
            ledger.finish(a, {'related': False}, {}, .01)
            return {'reviewed': 1}
        list(P.events(self.rows, [], self.source, process, self.factory,
                      workers=2, source_workers=2, should_stop=stopping.is_set))
        self.assertEqual(len(calls), 2)
        self.assertAlmostEqual(self.ledger.spent(), .02)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='reserved'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
