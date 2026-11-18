import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import community_edges as C
import contribution_agent as G
import contribution_packs as P
import contribution_proposals as X
import contribution_workspace as W


class ProposedPairsAndAgentRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in P.PORTABLE:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        papers = [('Oracle gradients for convex games', 2019, 'https://papers.nips.cc/paper/2019/hash/aaa-Abstract.html'),
                  ('Faster oracle gradients with momentum', 2022, 'https://proceedings.mlr.press/v162/bbb22a.html'),
                  ('Oracle gradients revisited', 2022, 'https://openreview.net/forum?id=ccc')]
        (self.root / 'evolve/generated/abstracts').mkdir(parents=True)
        (self.root / 'evolve/corpus.json').write_text(json.dumps(
            [{'t': t, 'y': y, 'u': u, 'v': 'x', 'mega': 'Optimization', 'topic': 'Oracle methods', 'leaf': ''} for t, y, u in papers]))
        (self.root / 'evolve/generated/abstracts/meta.json').write_text(json.dumps({'shard_size': 2}))
        for shard in range(2):
            rows = [{'url': u, 'abstract': f'We study {t.lower()} and report what changes.'} for t, y, u in papers[shard * 2:shard * 2 + 2]]
            (self.root / f'evolve/generated/abstracts/{shard:03d}.json').write_text(json.dumps(rows))
        (self.root / 'community/tasks').mkdir(parents=True, exist_ok=True)

    def test_proposal_is_rebuilt_from_public_files_and_tampering_is_rejected(self):
        made = X.propose('oracle gradients convex games', 'https://proceedings.mlr.press/v162/bbb22a.html', self.root)
        path = self.root / made['path']
        pack = C.read_json(path)
        task = pack['tasks'][0]
        self.assertEqual((made['earlier']['year'], made['later']['year']), (2019, 2022))
        self.assertEqual(task['state']['paper_b']['venue'], 'ICML')
        self.assertEqual(task['state']['source_evidence'], {'status': 'needs_context', 'passages': [], 'documents': {}})
        X.verify(path.stem, pack, self.root)
        self.assertEqual(W.resolve_pack(made['pack'], self.root), path)  # found although the catalog predates it
        with self.assertRaisesRegex(ValueError, 'already a task'):
            X.propose(made['earlier']['id'], made['later']['id'], self.root)
        with self.assertRaisesRegex(ValueError, 'earlier year'):
            X.propose('Faster oracle gradients with momentum', 'Oracle gradients revisited', self.root)
        with self.assertRaisesRegex(ValueError, '3 papers match'):
            X.propose('oracle gradients', 'Oracle gradients revisited', self.root)
        # A proposed pair can become a positive edge only through registered full-paper excerpts.
        import contribution_sources as S
        stamp = {'retrieved_at': '2026-01-01T00:00:00+00:00', 'extraction': 'pdftotext', 'acquired_via': 'public_download', 'document_sha256': 'a' * 64}
        quotes = {'a_passage_research_1': ('a', 3, 'We introduce oracle gradients, an estimator for convex games.'),
                  'b_citation_research_1': ('b', 2, 'We extend the oracle gradients of prior work with a momentum term.')}
        passages = [{'id': key, 'paper_id': task[side], 'paper_title': task['state']['paper_' + side]['title'],
                     'origin_url': task['sources'][side]['url'], 'url': task['sources'][side]['url'], 'page': page,
                     'text': text, 'text_sha256': S.sha(text.encode()), **stamp} for key, (side, page, text) in quotes.items()]
        material = {'version': S.VERSION, 'passages': passages}
        material['sha256'] = S.digest(material)
        decision = {'related': True, 'basis': 'explicit_statement', 'relations': [{'type': 'Extends', 'confidence': .9}],
                    'reason': 'The later paper states that it extends the earlier estimator.', 'inherited': 'The oracle gradient estimator.',
                    'changed': 'A momentum term.', 'evidence': [{'source': key, 'quote': text} for key, (_, _, text) in quotes.items()]}
        submission = {'version': C.VERSION, 'contributor': {'name': 'Ada', 'tool': 'Reader', 'method': 'manual'},
                      'decisions': [{'task_id': task['id'], 'task_sha256': task['sha256'], 'decision': decision, 'source_material': material}]}
        self.assertEqual(C.validate_submission(pack, submission)[0]['result']['types'], {'Extends': .9})
        del submission['decisions'][0]['source_material']
        with self.assertRaises(ValueError):C.validate_submission(pack, submission)  # abstracts alone cannot carry it
        task['state']['paper_a']['abstract'] = 'We prove the later paper copied everything.'
        task['sha256'] = C.digest({k: v for k, v in task.items() if k != 'sha256'})
        C.task_index(pack)  # internally consistent, so only the corpus comparison can catch it
        with self.assertRaisesRegex(ValueError, 'differs from the public corpus'):
            X.verify(path.stem, pack, self.root)

    def test_one_command_run_reviews_validates_and_stages_pack_with_submission(self):
        made = X.propose('Oracle gradients for convex games', 'Oracle gradients revisited', self.root)
        calls = []

        def agent(argv, cwd=None, timeout=None, **_):
            calls.append(argv)
            path = Path(cwd) / 'submission.json'
            envelope = json.loads(path.read_text())
            if len(calls) > 1:  # first pass leaves the template blank, so the runner must ask for a repair
                for row in envelope['submission']['decisions']:
                    row['decision']['reason'] = 'Neither abstract states a contribution link, and no full text was read.'
                path.write_text(json.dumps(envelope))
            return SimpleNamespace(returncode=0)

        summary = G.run([made['pack']], 'Ada Reviewer', template='some-agent --dir {workspace} {prompt}', root=self.root, execute=agent)
        row = summary['packs'][0]
        self.assertEqual((row['validated'], row['positive_edges'], len(calls)), (1, 0, 2))
        self.assertEqual(calls[0][:3], ['some-agent', '--dir', row['workspace']])
        self.assertIn('The last check failed with', calls[1][3])
        self.assertEqual(row['files'][0], made['path'])
        self.assertTrue((self.root / row['files'][1]).exists())
        self.assertIn('git add -- ' + ' '.join(row['files']), summary['commands'])
        self.assertFalse(summary['pushed'] or summary['pull_request_created'])
        again = G.run([made['pack']], 'Ada Reviewer', template='some-agent {prompt}', root=self.root, execute=agent)
        self.assertEqual((again['packs'][0]['validated'], len(calls)), (1, 2))  # a finished workspace is not reviewed twice

    def test_agents_get_only_the_research_commands(self):
        prefix = G.tool_prefix(self.root)
        claude = G.command('claude', self.root, 'PROMPT', prefix, 'some-model')
        allowed = claude[claude.index('--allowedTools') + 1:claude.index('--model')]
        self.assertEqual([a for a in allowed if a.startswith('Bash')], [f'Bash({prefix} {name}:*)' for name in ('fetch', 'cite', 'check')])
        self.assertNotIn('bypassPermissions', claude)
        codex = G.command('codex', self.root, 'PROMPT', prefix)
        self.assertEqual(codex[codex.index('-s') + 1], 'workspace-write')
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', codex)
        for name in ('push', ' pr ', ' api '):
            self.assertNotIn(name, G.instructions(prefix).split('only commands you may run')[1].split('fetch writes')[0])


if __name__ == '__main__':
    unittest.main()
