import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import community_edges as C


class CommunityReviews(unittest.TestCase):
    def setUp(self):
        self.state = {'paper_a': {'title': 'Original oracle', 'year': 2020, 'abstract': 'Our method uses an exact optimization oracle.'},
                      'paper_b': {'title': 'Relaxed oracle', 'year': 2022, 'abstract': 'We generalize the original oracle method to relaxed optimization.'}}
        self.papers = {'a': {'source_url': 'https://example.org/a'}, 'b': {'source_url': 'https://example.org/b'}}
        self.task = C.make_task('a', 'b', self.state, self.papers)
        self.pack = {'version': C.VERSION, 'tasks': [self.task]}
        self.decision = {'related': True, 'basis': 'explicit_statement', 'relations': [{'type': 'Extends', 'confidence': .95}],
                         'reason': 'Explicitly generalizes the oracle method.', 'inherited': 'Oracle optimization.', 'changed': 'Relaxed oracle.',
                         'evidence': [{'source': 'a_abstract', 'quote': self.state['paper_a']['abstract']},
                                      {'source': 'b_abstract', 'quote': self.state['paper_b']['abstract']}]}
        self.submission = {'version': C.VERSION, 'contributor': {'name': 'Contributor', 'tool': 'local-model/version', 'method': 'local_model'},
                           'decisions': [{'task_id': self.task['id'], 'task_sha256': self.task['sha256'], 'decision': self.decision}]}

    def test_valid_local_review_needs_no_credentials_or_network(self):
        rows = C.validate_submission(self.pack, self.submission)
        self.assertTrue(rows[0]['result']['related'])
        self.assertNotIn('human_verified', rows[0]['result'])

    def test_tampered_snapshot_or_stale_submission_fails_closed(self):
        pack = copy.deepcopy(self.pack)
        pack['tasks'][0]['state']['paper_a']['abstract'] += ' Modified.'
        with self.assertRaises(ValueError):
            C.validate_submission(pack, self.submission)
        self.submission['decisions'][0]['task_sha256'] = 'stale'
        with self.assertRaises(ValueError):
            C.validate_submission(self.pack, self.submission)

    def test_one_fabricated_quote_invalidates_whole_decision(self):
        self.decision['evidence'].append({'source': 'b_abstract', 'quote': 'This quotation was never in the paper.'})
        with self.assertRaises(ValueError):
            C.validate_submission(self.pack, self.submission)

    def test_duplicate_tasks_and_one_sided_edges_are_rejected(self):
        self.submission['decisions'] *= 2
        with self.assertRaises(ValueError):
            C.validate_submission(self.pack, self.submission)
        self.submission['decisions'] = self.submission['decisions'][:1]
        self.decision['evidence'] = self.decision['evidence'][:1]
        with self.assertRaises(ValueError):
            C.validate_submission(self.pack, self.submission)

    def test_revival_requires_explicit_link_and_finite_non_boolean_score(self):
        self.decision['relations'][0]['type'] = 'Revives'
        self.decision['basis'] = 'contribution_comparison'
        with self.assertRaises(ValueError):
            C.validate_submission(self.pack, self.submission)
        self.decision['basis'] = 'explicit_statement'
        for value in (True, float('nan'), 1.1, .4):
            self.decision['relations'][0]['confidence'] = value
            with self.assertRaises(ValueError):
                C.validate_submission(self.pack, self.submission)

    def test_acceptance_is_separate_and_assistant_review_is_not_human_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(C.load_approved(directory), {})
            C.accept(self.pack, self.submission, Path(directory) / 'accepted.json', 'Codex', 'assistant', 'Checked both quoted sources.')
            row = C.load_approved(directory)['a', 'b']
            self.assertFalse(row['result']['human_verified'])
            self.assertEqual(row['result']['community_review']['contributor']['method'], 'local_model')
            with self.assertRaises(FileExistsError):
                C.accept(self.pack, self.submission, Path(directory) / 'accepted.json', 'Codex', 'assistant', 'Duplicate.')

    def test_static_overlay_publishes_correction_without_private_cache(self):
        from voyage_pipeline import read_records
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [{'id': k, 'title': self.state['paper_' + k]['title'], 'year': self.state['paper_' + k]['year'], 'source_url': self.papers[k]['source_url']} for k in ('a', 'b')]
            corpus = root / 'corpus.json'
            corpus.write_text(json.dumps(records))
            approved = root / 'approved'
            C.accept(self.pack, self.submission, approved / 'accepted.json', 'Reviewer', 'human', 'Read the source documents.')
            overlay = C.export_static(root / 'community.json', corpus, approved)
            self.assertEqual(overlay['entries']['0']['overrides'], [1])
            self.assertEqual(overlay['meta']['positive_edges'], 1)
            self.assertTrue(overlay['entries']['0']['c'][0][-1]['human_verified'])
            # A reviewed abstention can withdraw an existing paid prediction.
            self.decision.update(related=False, basis='insufficient_evidence', relations=[], inherited='', changed='')
            (approved / 'accepted.json').unlink()
            C.accept(self.pack, self.submission, approved / 'negative.json', 'Reviewer', 'human', 'The passages do not establish inheritance.')
            overlay = C.export_static(root / 'community.json', corpus, approved)
            self.assertEqual(overlay['meta']['positive_edges'], 0)
            self.assertEqual(overlay['entries']['0']['overrides'], [1])


if __name__ == '__main__':
    unittest.main()
