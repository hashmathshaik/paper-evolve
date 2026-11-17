import json,unittest
from pathlib import Path
D=json.loads((Path(__file__).parents[1]/'evolve/research.json').read_text())
class ResearchIntegrity(unittest.TestCase):
 def test_endpoints_and_time(self):
  papers={p['id']:p for p in D['papers']};cs={c['id']:c for c in D['contributions']}
  for e in D['edges']:
   a,b=(papers[cs[e[k]]['paper_id']] for k in ('source','target'))
   self.assertLess(a['date'],b['date'])
   self.assertIn(e['status'],['explicit','inferred','unverified'])
   if e['status']=='explicit':self.assertTrue(any(v['passage'] and v['url'].startswith('https://') for v in e['evidence']))
 def test_similarity_is_separate(self):
  ids={p['id'] for p in D['papers']};connected=set()
  for e in D['similarities']:
   self.assertIn(e['a'],ids);self.assertIn(e['b'],ids);self.assertGreaterEqual(e['score'],0);self.assertLessEqual(e['score'],1);connected.update([e['a'],e['b']])
  self.assertEqual(ids,connected)
 def test_contributions_and_versions(self):
  for p in D['papers']:
   self.assertTrue(p['versions']);self.assertTrue(p['retrieved_at']);self.assertTrue(any(c['paper_id']==p['id'] for c in D['contributions']))
if __name__=='__main__':unittest.main()
