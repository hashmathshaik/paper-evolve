import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pipeline',ROOT/'scripts/voyage_pipeline.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class VoyagePipelineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.cache=p.Cache(Path(self.temp.name)/'cache.sqlite3');self.addCleanup(self.cache.db.close)
  self.config=p.load_config(ROOT/'config/voyage.json')
  self.records=p.read_records('research',limit=3)
 def response(self,payload):
  return {'data':[{'index':i,'embedding':[float(i+1)]+[.5]*(self.config['output_dimension']-1)} for i in reversed(range(len(payload['input'])))], 'usage':{'total_tokens':100}}
 def test_resume_and_changed_text(self):
  calls=[]
  def transport(payload,key):calls.append(payload);return self.response(payload)
  with redirect_stdout(io.StringIO()):
   self.assertEqual(p.run_embeddings(self.records,self.config,self.cache,'secret',transport,lambda _:None),3)
   self.assertEqual(p.run_embeddings(self.records,self.config,self.cache,'secret',transport,lambda _:None),0)
  self.assertEqual(len(calls),1)
  changed={**self.records[0],'text_hash':p.digest('new abstract')}
  self.assertIsNone(self.cache.get(changed,self.config))
  self.assertEqual(len(self.cache.get(self.records[0],self.config)),2048)
 def test_budget_stops_before_request(self):
  config={**self.config,'budget_usd':.00000001}
  with self.assertRaisesRegex(ValueError,'exceeds'):
   p.run_embeddings(self.records,config,self.cache,'secret',lambda *_:self.fail('No request allowed'))
 def test_retry_reserves_each_attempt(self):
  calls=[]
  def transport(payload,key):
   calls.append(1)
   if len(calls)==1:raise HTTPError(p.API_URL,429,'limited',{},None)
   return self.response(payload)
  with redirect_stdout(io.StringIO()):p.run_embeddings(self.records,self.config,self.cache,'secret',transport,lambda _:None)
  self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],2)
 def test_bad_response_never_cached(self):
  with self.assertRaisesRegex(ValueError,'Invalid embedding response'):
   p.run_embeddings(self.records,self.config,self.cache,'secret',lambda *_:{'data':[]},lambda _:None)
  self.assertIsNone(self.cache.get(self.records[0],self.config))
 def test_model_settings_invalidate_cache(self):
  with redirect_stdout(io.StringIO()):p.run_embeddings(self.records,self.config,self.cache,'secret',lambda payload,key:self.response(payload),lambda _:None)
  self.assertIsNone(self.cache.get(self.records[0],{**self.config,'output_dimension':1024}))
 def test_cosine_neighbors_not_evolution_edges(self):
  result=p.neighbors(self.records,[[1,0],[.9,.1],[0,1]],top_k=1)
  self.assertTrue(result)
  self.assertTrue(all(e['kind']=='conceptual_similarity' and e['evidence_status']=='unverified' and 'type' not in e for e in result))
 def test_quality_gate(self):
  with patch.dict('os.environ',{'VOYAGE_API_KEY':'not-sent'}):
   with self.assertRaisesRegex(ValueError,'Title-only'):
    p.main(['embed','--source','corpus','--limit','1','--cache',str(Path(self.temp.name)/'quality.sqlite3')])
 def test_exact_search_refuses_unbounded_work(self):
  with self.assertRaisesRegex(ValueError,'2,000'):
   p.neighbors([self.records[0]]*2001,[[1,0]]*2001,method='exact')
 def test_oversized_input_rejected_without_truncation(self):
  record={**self.records[0],'text':'x'*40000}
  with self.assertRaisesRegex(ValueError,'too long'):
   list(p.batches([record],self.config))

class QueueAdmissionTests(unittest.TestCase):
 def test_refresh_at_ten_thousand(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'))
  from embedding_queue import should_refresh
  self.assertTrue(should_refresh(34144,24144,20000))
  self.assertFalse(should_refresh(34143,24144,20000))
 def test_flush_small_remainder_when_caught_up(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'))
  from embedding_queue import should_refresh
  self.assertTrue(should_refresh(24500,24144,0))
  self.assertFalse(should_refresh(24144,24144,0))

if __name__=='__main__':unittest.main()
