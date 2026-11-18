import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import contribution_papers as N
import contribution_proposals as X


class AddedPapersAndVenues(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        base = [('Oracle gradients for convex games', 2019, 'https://papers.nips.cc/paper/2019/hash/aaa-Abstract.html', 'neurips'),
                ('Faster oracle gradients with momentum', 2022, 'https://proceedings.mlr.press/v162/bbb22a.html', 'icml'),
                ('Oracle gradients revisited', 2022, 'https://openreview.net/forum?id=ccc', 'iclr')]
        (self.root / 'evolve/generated/abstracts').mkdir(parents=True)
        (self.root / 'community/papers').mkdir(parents=True)
        (self.root / 'community/tasks').mkdir()
        (self.root / 'evolve/corpus.json').write_text(json.dumps(
            [{'t': t, 'v': v, 'y': y, 'u': u, 'mega': 'Optimization', 'topic': 'Oracle methods', 'leaf': 'Unclustered'} for t, y, u, v in base], separators=(',', ':')))
        (self.root / 'evolve/generated/abstracts/meta.json').write_text(json.dumps({'version': 1, 'total': 3, 'abstracts': 3, 'shard_size': 2, 'shards': 2}))
        for shard in range(2):
            rows = [{'url': u, 'abstract': f'We study {t.lower()} and report what changes.', 'source_url': u, 'retrieved_at': '2026-01-01T00:00:00+00:00'}
                    for t, y, u, v in base[shard * 2:shard * 2 + 2]]
            (self.root / f'evolve/generated/abstracts/{shard:03d}.json').write_text(json.dumps(rows))
        (self.root / 'community/venues.json').write_bytes((ROOT / 'community/venues.json').read_bytes())
        self.paper = {'title': 'Oracle  gradients for vision transformers', 'year': 2024, 'venue': 'cvpr',
                      'url': 'https://openaccess.thecvf.com/content/CVPR2024/html/Oracle_CVPR_2024_paper.html',
                      'abstract': 'We carry oracle gradients over to vision transformers and show that the estimator stays unbiased under patch dropout.'}
        self.listed = self.root / 'my-papers.json'

    def submit(self, *papers):
        self.listed.write_text(json.dumps(list(papers)))
        return N.submit(self.listed, 'Ada Reviewer', 'Some agent / model', self.root)

    def test_new_venue_and_paper_flow_from_submission_to_published_collection(self):
        with self.assertRaisesRegex(ValueError, "venue 'cvpr' is not registered"):
            self.submit(self.paper)
        N.add_venue('cvpr', 'CVPR', ['openaccess.thecvf.com'], self.root)
        with self.assertRaisesRegex(ValueError, 'already registered'):
            N.add_venue('cvpr', 'CVPR', ['openaccess.thecvf.com'], self.root)
        made = self.submit(self.paper)
        self.assertEqual((made['papers'], made['venues'], made['pushed']), (1, ['cvpr'], False))
        self.assertIn(f"git add -- {made['output']} community/venues.json", made['commands'])
        saved = json.loads((self.root / made['output']).read_text())['papers'][0]
        self.assertEqual((saved['title'], saved['topic'], saved['abstract_source_url']), ('Oracle gradients for vision transformers', 'Unclustered', self.paper['url']))
        self.assertEqual(N.check(self.root), 1)
        with self.assertRaisesRegex(ValueError, 'Already in the collection'):
            self.submit(self.paper)  # a submission still waiting for review blocks its duplicate
        before = (self.root / 'evolve/corpus.json').read_text()
        result = N.apply(self.root)
        self.assertEqual(result, {'applied_files': 1, 'papers': 1, 'total': 4})
        after = (self.root / 'evolve/corpus.json').read_text()
        self.assertTrue(after.startswith(before[:-1] + ','))  # existing rows are untouched, the new one is appended
        row = json.loads(after)[3]
        self.assertEqual((row['v'], row['topic'], row['mega'], row['src']), ('cvpr', 'Unclustered', 'Unclustered', 'community'))
        meta = json.loads((self.root / 'evolve/generated/abstracts/meta.json').read_text())
        self.assertEqual((meta['total'], meta['shards']), (4, 2))
        self.assertEqual(json.loads((self.root / 'evolve/generated/abstracts/001.json').read_text())[1]['url'], self.paper['url'])
        near = json.loads((self.root / 'evolve/generated/additions.json').read_text())['entries']['3']['s']
        self.assertIsInstance(near, list)  # three papers are too few to share rare words; the larger case is tested below
        self.assertEqual((N.check(self.root), len(list((self.root / 'community/papers/applied').glob('*.json')))), (0, 1))
        self.assertEqual(N.apply(self.root)['papers'], 0)
        # The added paper can be connected straight away, with its venue named from the registry.
        pack = json.loads((self.root / X.propose('Oracle gradients for convex games', 'oracle gradients vision transformers', self.root)['path']).read_text())
        self.assertEqual(pack['tasks'][0]['state']['paper_b']['venue'], 'CVPR')
        X.verify('proposal-' + pack['tasks'][0]['id'][5:], pack, self.root)

    def test_submissions_are_rejected_for_duplicates_wrong_hosts_and_weak_records(self):
        N.add_venue('cvpr', 'CVPR', ['openaccess.thecvf.com'], self.root)
        cases = [({'title': 'Oracle Gradients for Convex Games', 'year': 2019}, 'Already in the collection'),
                 ({'url': 'https://example.com/paper.html'}, 'public HTTPS page on openaccess.thecvf.com'),
                 ({'url': self.paper['url'] + '?token=abc'}, 'public HTTPS page'),
                 ({'abstract': 'Too short to be a real abstract.'}, 'full published abstract'),
                 ({'year': 1700}, 'year is out of range'),
                 ({'topic': 'A topic nobody defined'}, 'unknown topic'),
                 ({'abstract_source_url': 'https://example.com/copy'}, 'abstract source must be a public page'),
                 ({'retrieved_at': 'yesterday'}, 'ISO timestamp')]
        for change, message in cases:
            with self.assertRaisesRegex(ValueError, message):
                self.submit({**self.paper, **change})
        with self.assertRaisesRegex(ValueError, 'Each paper needs title'):
            self.submit({**self.paper, 'authors': 'x'})
        for identity, name, hosts in [('CVPR', 'CVPR', ['openaccess.thecvf.com']), ('eccv', 'ECCV', ['https://www.ecva.net/papers']), ('x', 'X', ['x.org'])]:
            with self.assertRaises(ValueError):
                N.add_venue(identity, name, hosts, self.root)
        self.assertEqual(sorted(N.registry(self.root))[:2], ['acl', 'cvpr'])  # a rejected venue leaves the registry as it was
        self.assertEqual(self.submit({**self.paper, 'topic': 'Oracle methods'})['papers'], 1)

    def test_wording_neighbours_match_a_plain_bm25_reference_and_assign_a_topic(self):
        import math
        import lexical_neighbours as L
        texts = ['graph neural networks for molecules', 'molecule generation with graph diffusion', 'bandit regret bounds under delay',
                 'regret minimisation for linear bandits', 'graph networks and molecules molecules', 'protein folding with diffusion']
        index = L.Index()
        for text in texts:index.add(text)
        query = 'graph networks for molecule and molecules design'
        # Slow reference: BM25 written out per paper, over the same query terms.
        counts = [L.collections.Counter(L.terms(t)) for t in texts]
        average, n = sum(sum(c.values()) for c in counts) / len(texts), len(texts)
        idf = lambda term: math.log(1 + (n - sum(term in c for c in counts) + .5) / (sum(term in c for c in counts) + .5))
        wanted = [t for t in set(L.terms(query)) if 0 < sum(t in c for c in counts) <= max(2, L.COMMON * n)]
        reference = {i: sum(idf(t) * c[t] * (L.K1 + 1) / (c[t] + L.K1 * (1 - L.B + L.B * sum(c.values()) / average)) for t in wanted if t in c) for i, c in enumerate(counts)}
        ceiling = sum(idf(t) * (L.K1 + 1) for t in wanted)
        expected = sorted(((round(s / ceiling, 3), i) for i, s in reference.items() if s), reverse=True)[:3]
        self.assertEqual([(score, i) for i, score in index.nearest(query, 3)], expected)
        self.assertEqual(index.nearest(query, 1)[0][0], 4)
        # Topic: a paper filed without one takes the topic most of its nearest papers share.
        rows = [{'t': f'Spectral clustering of sparse graphs, part {i}', 'v': 'icml', 'y': 2020, 'u': f'https://proceedings.mlr.press/v119/p{i}.html',
                 'mega': 'Graphs', 'topic': 'Graph clustering', 'leaf': 'Unclustered'} for i in range(8)]
        # Words found in over a fifth of the collection are ignored, so the cluster has to be a minority of it.
        rows += [{'t': f'Unrelated filler study {i}', 'v': 'icml', 'y': 2021, 'u': f'https://proceedings.mlr.press/v139/f{i}.html',
                  'mega': 'Optimization', 'topic': 'Oracle methods', 'leaf': 'Unclustered'} for i in range(40)]
        rows += json.loads((self.root / 'evolve/corpus.json').read_text())
        (self.root / 'evolve/corpus.json').write_text(json.dumps(rows, separators=(',', ':')))
        shard = [{'url': r['u'], 'abstract': r['t'] + (' with eigenvector methods and community detection guarantees.' if r['topic'] == 'Graph clustering' else ' about something else entirely.')} for r in rows]
        (self.root / 'evolve/generated/abstracts/meta.json').write_text(json.dumps({'version': 1, 'total': len(rows), 'abstracts': len(rows), 'shard_size': 100, 'shards': 1}))
        (self.root / 'evolve/generated/abstracts/000.json').write_text(json.dumps(shard))
        (self.root / 'evolve/generated/abstracts/001.json').unlink()
        N.add_venue('cvpr', 'CVPR', ['openaccess.thecvf.com'], self.root)
        self.submit({**self.paper, 'title': 'Spectral clustering of sparse graphs with eigenvector guarantees',
                     'abstract': 'We revisit spectral clustering of sparse graphs and prove community detection guarantees for eigenvector methods under weak assumptions.'})
        N.apply(self.root)
        added = json.loads((self.root / 'evolve/corpus.json').read_text())[-1]
        self.assertEqual((added['topic'], added['mega']), ('Graph clustering', 'Graphs'))


if __name__ == '__main__':
    unittest.main()
