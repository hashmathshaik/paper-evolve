import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import community_edges as C
import contribution_workspace as W
import contribution_api as A
import contribution_packs as P
import test_community_edges as fixtures


class ContributionSystem(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in P.PORTABLE:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        self.fixture = fixtures.CommunityReviews()
        self.fixture.setUp()
        self.state = copy.deepcopy(self.fixture.state)
        self.state['source_evidence'] = {'status': 'ready', 'passages': [
            {'id': 'b_citation_1', 'text': self.state['paper_b']['abstract'], 'url': 'https://example.org/b.pdf',
             'page': 2, 'document_sha256': 'a' * 64}]}
        self.task = C.make_task('a', 'b', self.state, self.fixture.papers)
        self.pack = {'version': C.VERSION, 'topic': 'Oracle methods', 'area': 'Optimization', 'tasks': [self.task]}
        self.pack_path = self.root / 'community/tasks/oracle-001.json'
        self.pack_path.parent.mkdir(exist_ok=True)
        self.pack_path.write_text(json.dumps(self.pack))
        self.decision = copy.deepcopy(self.fixture.decision)
        self.decision['evidence'][1]['source'] = 'b_citation_1'
        P.catalog(self.root)
        self.workspace = self.root / 'work/contributions/test'

    def prepare(self, method='assistant'):
        return W.prepare(self.pack_path, self.workspace, 'Researcher', 'Exact model/version', method, root=self.root)

    def fill(self):
        path = self.workspace / 'submission.json'
        envelope = json.loads(path.read_text())
        envelope['submission']['decisions'][0]['decision'] = self.decision
        path.write_text(json.dumps(envelope))

    def api(self, transport, **options):
        with patch.object(W, 'ROOT', self.root):
            return A.run(self.workspace, options.pop('base', 'https://api.example.org/v1'),
                         options.pop('model', 'fixture-model'), 'NO_REAL_KEY', options.pop('input_rate', .1),
                         .2, options.pop('budget', 1), limit=10, transport=transport, **options)

    def response(self, _):
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.decision)}}],
                'usage': {'prompt_tokens': 1000, 'completion_tokens': 200}}

    def test_agent_workspace_export_is_portable_validated_and_separate_from_acceptance(self):
        self.prepare()
        for name in ('pack.json', 'PROMPT.md', 'AGENTS.md', 'CLAUDE.md', 'decision.schema.json'):
            self.assertTrue((self.workspace / name).exists())
        with self.assertRaises(ValueError):W.check(self.workspace)  # Blank template is not a decision.
        self.fill()
        output = self.root / 'community/submissions/researcher.json'
        result = W.export(self.workspace, output, self.root)
        self.assertEqual(result['positive_edges'], 1)
        self.assertFalse(result['published'])
        self.assertEqual(C.load_approved(self.root / 'community/approved'), {})
        with self.assertRaises(FileExistsError):W.export(self.workspace, output, self.root)
        catalog = P.catalog(self.root)
        self.assertEqual(catalog['packs'][0]['available_tasks'], 0)
        with self.assertRaises(ValueError):
            W.prepare(self.pack_path, self.root / 'another', 'Name', 'Model', root=self.root)

    def test_evidence_tampering_and_workspace_overwrite_are_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):self.prepare()
        path = self.workspace / 'pack.json'
        pack = json.loads(path.read_text());pack['tasks'][0]['state']['paper_a']['abstract'] += ' changed'
        path.write_text(json.dumps(pack))
        with self.assertRaises(ValueError):W.load(self.workspace)

    def test_fabricated_quote_never_exports(self):
        self.prepare();self.decision['evidence'][1]['quote'] = 'The paper never actually said this.';self.fill()
        with self.assertRaises(ValueError):W.export(self.workspace, self.root / 'out.json', self.root)

    def test_api_uses_same_submission_schema_and_does_not_resend_completed_tasks(self):
        self.prepare('api')
        first = self.api(self.response)
        self.assertEqual(first['valid_decisions'], 1)
        self.assertAlmostEqual(first['spent_or_reserved_usd'], .00014)
        self.assertEqual(len(W.check(self.workspace)), 1)
        second = self.api(lambda _: self.fail('Completed request was repeated'))
        self.assertEqual(second['requests'], 0)
        self.assertEqual(second['spent_or_reserved_usd'], first['spent_or_reserved_usd'])

    def test_api_reserves_before_request_and_obeys_cumulative_budget(self):
        self.prepare('api')
        result = self.api(lambda _: self.fail('Over-budget request sent'), budget=.000001)
        self.assertEqual(result['phase'], 'budget_limited')
        self.assertEqual(result['spent_or_reserved_usd'], 0)

    def test_unknown_outcome_is_held_and_never_automatically_retried(self):
        self.prepare('api')
        def timeout(_):raise TimeoutError()
        first = self.api(timeout)
        self.assertEqual(first['phase'], 'uncertain_request')
        self.assertGreater(first['spent_or_reserved_usd'], 0)
        second = self.api(lambda _: self.fail('Unknown request resent'))
        self.assertEqual(second['phase'], 'complete_with_unresolved')
        self.assertEqual(first['spent_or_reserved_usd'], second['spent_or_reserved_usd'])

    def test_missing_usage_preserves_reservation_and_invalid_output_is_billed(self):
        self.prepare('api')
        raw = self.response({});raw['usage'] = []
        result = self.api(lambda _: raw)
        self.assertEqual(result['phase'], 'uncertain_usage')
        self.assertGreater(result['spent_or_reserved_usd'], 0)

    def test_truncated_or_fabricated_api_output_never_enters_submission(self):
        self.prepare('api')
        raw = self.response({});raw['choices'][0]['finish_reason'] = 'length'
        result = self.api(lambda _: raw)
        self.assertEqual(result['invalid'], 1)
        self.assertAlmostEqual(result['spent_or_reserved_usd'], .00014)
        self.assertEqual(W.load(self.workspace)[2]['submission']['decisions'], [])

    def test_api_rejection_has_no_error_body_or_secret_in_local_outputs(self):
        self.prepare('api')
        def rejected(_):raise HTTPError('https://api.example.org',401,'Unauthorized',{},BytesIO(b'private-key-and-request-data'))
        result = self.api(rejected)
        self.assertEqual(result['phase'], 'provider_http_401')
        self.assertEqual(result['spent_or_reserved_usd'], 0)
        self.assertNotIn('private-key-and-request-data', (self.workspace / 'api-status.json').read_text())
        self.api(lambda _: self.fail('Rejected identity automatically resent'))

    def test_api_missing_sources_abstains_without_spending(self):
        self.pack['tasks'][0] = C.make_task('a', 'b', self.fixture.state, self.fixture.papers)
        self.pack_path.write_text(json.dumps(self.pack));P.catalog(self.root);self.prepare('api')
        result = self.api(lambda _: self.fail('Missing-source task sent to API'))
        self.assertEqual(result['source_missing'], 1)
        self.assertEqual(result['spent_or_reserved_usd'], 0)
        self.assertFalse(W.check(self.workspace)[0]['result']['related'])

    def test_agent_workspace_never_accidentally_runs_api(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'method api'):self.api(lambda _: self.fail('Agent workspace sent'))

    def test_second_api_process_cannot_send_from_same_workspace(self):
        self.prepare('api')
        with (self.workspace / 'api.lock').open('a+') as handle:
            A.claim_workspace(handle)
            with self.assertRaisesRegex(ValueError, 'already using'):
                self.api(lambda _: self.fail('Concurrent request sent'))

    def test_model_or_rate_changes_cannot_mix_results_or_reset_spending(self):
        self.prepare('api');self.api(self.response)
        with self.assertRaises(ValueError):self.api(self.response, model='different-model')
        with self.assertRaises(ValueError):self.api(self.response, input_rate=99)

    def test_completed_ledger_decision_recovers_after_submission_write_interruption(self):
        self.prepare('api');self.api(self.response)
        path = self.workspace / 'submission.json';doc = json.loads(path.read_text());doc['submission']['decisions'] = [];path.write_text(json.dumps(doc))
        self.api(lambda _: self.fail('Recovery must use settled ledger result'))
        self.assertEqual(len(W.check(self.workspace)), 1)

    def test_config_never_accepts_credentials_in_url_or_negative_nonfinite_rates(self):
        self.prepare('api')
        for base in ('http://remote.example/v1','https://key@example.org/v1','https://example.org/v1?key=secret'):
            with self.assertRaises(ValueError):self.api(self.response, base=base)
        for rate in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):self.api(self.response, input_rate=rate)

    def test_project_env_is_never_used_for_contributor_credentials(self):
        self.prepare('api')
        (self.root / '.env').write_text('PAPER_EVOLVE_API_KEY=not-authorized-for-this-route\n')
        with patch.object(W, 'ROOT', self.root), patch.dict(A.os.environ, {}, clear=True), patch.object(A, 'send', side_effect=AssertionError('Network request sent')):
            with self.assertRaisesRegex(ValueError, 'environment variable'):
                A.run(self.workspace, 'https://api.example.org/v1', 'fixture', 'PAPER_EVOLVE_API_KEY', .1, .2, 1)

    def test_provider_key_variables_are_used_only_for_their_own_host(self):
        env = {'OPENAI_API_KEY': 'openai-key', 'OPENROUTER_API_KEY': 'router-key', 'PAPER_EVOLVE_API_KEY': 'generic-key'}
        self.assertEqual(A.api_key('https://api.openai.com/v1', environment=env), ('openai-key', 'OPENAI_API_KEY'))
        self.assertEqual(A.api_key('https://openrouter.ai/api/v1', environment=env), ('router-key', 'OPENROUTER_API_KEY'))
        self.assertEqual(A.api_key('https://dashscope-intl.aliyuncs.com/compatible-mode/v1', environment={'DASHSCOPE_API_KEY': 'q'}), ('q', 'DASHSCOPE_API_KEY'))
        # An unlisted or look-alike host never receives a provider key; only the generic variable applies.
        self.assertEqual(A.api_key('https://api.example.org/v1', environment=env), ('generic-key', 'PAPER_EVOLVE_API_KEY'))
        self.assertEqual(A.api_key('https://notopenai.com/v1', environment={'OPENAI_API_KEY': 'openai-key'}), ('', 'PAPER_EVOLVE_API_KEY'))
        self.assertEqual(A.api_key('https://api.openai.com.evil.example/v1', environment={'OPENAI_API_KEY': 'openai-key'})[0], '')
        self.assertEqual(A.api_key('https://api.openai.com/v1', environment={'PAPER_EVOLVE_API_KEY': 'generic-key'}), ('generic-key', 'PAPER_EVOLVE_API_KEY'))
        self.assertEqual(A.api_key('https://api.openai.com/v1', 'MY_KEY', {'OPENAI_API_KEY': 'openai-key'}), ('', 'MY_KEY'))
        self.prepare('api')
        with patch.object(W, 'ROOT', self.root), patch.dict(A.os.environ, {}, clear=True), patch.object(A, 'send', side_effect=AssertionError('Network request sent')):
            with self.assertRaisesRegex(ValueError, 'Set the OPENAI_API_KEY or PAPER_EVOLVE_API_KEY environment variable'):
                A.run(self.workspace, 'https://api.openai.com/v1', 'fixture', None, .1, .2, 1)

    def test_real_local_http_adapter_runs_cli_then_exports_valid_api_contribution(self):
        self.prepare('api')
        captured = []
        response = self.response({})
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):pass
            def do_POST(handler):
                body = json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
                captured.append((handler.path, body, handler.headers.get('Authorization')))
                data = json.dumps(response).encode()
                handler.send_response(200);handler.send_header('Content-Type','application/json')
                handler.send_header('Content-Length',str(len(data)));handler.end_headers();handler.wfile.write(data)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        env = {**A.os.environ, 'PAPER_EVOLVE_API_KEY': 'fixture-local-only-key'}
        command = [sys.executable, '-I', 'paper_evolve.py', 'api', '--workspace', str(self.workspace),
                   '--base-url', f'http://127.0.0.1:{server.server_port}/v1', '--model', 'fixture-model',
                   '--input-rate', '.1', '--output-rate', '.2', '--budget', '1']
        result = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['valid_decisions'], 1)
        self.assertEqual(captured[0][0], '/v1/chat/completions')
        self.assertEqual(captured[0][1]['model'], 'fixture-model')
        self.assertEqual(captured[0][2], 'Bearer fixture-local-only-key')
        self.assertEqual(len(W.check(self.workspace)), 1)
        for name in ('api-status.json', 'submission.json', 'api.sqlite3'):
            self.assertNotIn(b'fixture-local-only-key', (self.workspace / name).read_bytes())

    def test_catalog_accepts_new_evidence_revision_but_rejects_duplicate_snapshots(self):
        self.prepare();self.fill()
        W.export(self.workspace, self.root / 'community/submissions/first.json', self.root)
        updated = copy.deepcopy(self.state);updated['paper_b']['abstract'] += ' A more detailed abstract.'
        revised = {**self.pack, 'tasks': [C.make_task('a','b',updated,self.fixture.papers)]}
        revision = self.pack_path.with_name('oracle-revision-002.json');revision.write_text(json.dumps(revised))
        catalog = P.catalog(self.root)
        self.assertEqual([p['available_tasks'] for p in catalog['packs']], [0,1])
        self.pack_path.with_name('duplicate.json').write_text(json.dumps(self.pack))
        with self.assertRaises(ValueError):P.catalog(self.root)

    def test_downloaded_bundle_runs_without_repo_cache_env_or_dependencies(self):
        (self.root / '.env').write_text('DO_NOT_COPY=private-value\n')
        P.bundles(self.root)
        archive = self.root / 'community/bundles/paper-evolve-oracle-001.zip'
        before = archive.read_bytes();P.bundles(self.root);self.assertEqual(before, archive.read_bytes())
        unpacked = self.root / 'download'
        with zipfile.ZipFile(archive) as zipped:
            self.assertFalse(any('.env' in p or 'sqlite' in p or '/work/' in p for p in zipped.namelist()))
            zipped.extractall(unpacked)
        bundle = unpacked / 'paper-evolve-oracle-001'
        command = [sys.executable, '-I', 'paper_evolve.py', 'start', '--pack', 'oracle-001', '--name', 'Researcher', '--tool', 'Agent/version']
        proc = subprocess.run(command, cwd=bundle, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        work = bundle / 'work/contributions/oracle-001'
        doc = json.loads((work / 'submission.json').read_text());doc['submission']['decisions'][0]['decision'] = self.decision;(work / 'submission.json').write_text(json.dumps(doc))
        proc = subprocess.run([sys.executable, '-I', 'paper_evolve.py', 'export', '--workspace', str(work), '--output', 'community/submissions/researcher.json'], cwd=bundle, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(json.loads(proc.stdout)['published'])
