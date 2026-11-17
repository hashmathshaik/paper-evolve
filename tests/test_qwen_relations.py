import json,sys,tempfile,unittest,threading
from urllib.error import HTTPError
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import qwen_relations as Q

class QwenProvider(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.ledger=Q.C.Ledger(Path(self.tmp.name)/'ledger.db',1);Q.S.setup(self.ledger)
  self.state={'paper_a':{'title':'A','abstract':'Original Method A uses an exact oracle.'},'paper_b':{'title':'B','abstract':'We generalize Method A to relaxed oracles.'},'source_evidence':{'status':'ready','passages':[{'id':'b_citation_1','text':'We generalize Method A to relaxed oracles.','url':'https://example.org/b.pdf','page':3,'document_sha256':'hash'}]}}
  self.ledger.db.execute('INSERT INTO screens VALUES (?,?,?,?,?)',('a','b',Q.S.fingerprint(self.state),json.dumps({'passed':True,'audit':False}),'test'));self.ledger.db.commit()
 def response(self,params):
  result={'related':True,'basis':'explicit_statement','relations':[{'type':'Extends','confidence':.95}],'reason':'Generalizes A.','inherited':'Method A.','changed':'Relaxed oracle.','evidence_ids':['a_abstract:0','b_citation_1:0']}
  return {'model':'qwen3.7-flash-2026-07-15','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':2000,'completion_tokens':500}}
 def test_gated_qwen_review_is_cached_and_billed_once(self):
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,self.response),'accepted')
  amount=self.ledger.spent();self.assertAlmostEqual(amount,.000535)
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,lambda _:self.fail('duplicate call')),'cached')
  self.assertEqual(amount,self.ledger.spent())
 def test_missing_source_never_calls_provider(self):
  self.state['source_evidence']['status']='needs_context'
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,lambda _:self.fail('ungated call')),'needs_evidence_or_screen')
 def test_missing_usage_retains_reservation(self):
  raw=self.response({});raw['usage']={}
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,lambda _:raw),'invalid')
  self.assertGreater(self.ledger.spent(),0)
 def test_output_limit_fails_closed_and_accounts_for_reasoning_tokens(self):
  raw=self.response({});raw['choices'][0]['finish_reason']='length';raw['usage']['completion_tokens']=2000
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,lambda _:raw),'invalid')
  self.assertAlmostEqual(self.ledger.spent(),.00124)
 def test_unknown_quote_id_fails_closed(self):
  raw=json.loads(self.response({})['choices'][0]['message']['content']);raw['evidence_ids']=['invented']
  with self.assertRaises(ValueError):Q.decode(raw,self.state)
 def test_context_tier_bound_is_never_underpriced(self):
  self.assertEqual(Q.price('qwen3.7-flash',32001),(.1,.4))
  self.assertEqual(Q.price('qwen3.7-flash',256001),(.2,.8))
 def test_reasoning_and_total_output_are_bounded(self):
  p=Q.payload(self.state,Q.DEFAULT)
  self.assertTrue(p['enable_thinking']);self.assertEqual(p['max_completion_tokens'],3072)
  self.assertEqual(p['thinking_budget'],1024);self.assertEqual(p['response_format']['type'],'json_schema')

 def parallel_states(self,n):
  states={}
  for i in range(n):
   state=json.loads(json.dumps(self.state));state['paper_a']['title']=f'A {i}'
   pair=(f'a{i}',f'b{i}');states[pair]=state
   self.ledger.db.execute('INSERT INTO screens VALUES (?,?,?,?,?)',(*pair,Q.S.fingerprint(state),json.dumps({'passed':True,'audit':False}),'test'))
  self.ledger.db.commit();return states

 def test_sixteen_provider_requests_really_overlap(self):
  states=self.parallel_states(16);barrier=threading.Barrier(16,timeout=5)
  def transport(params):
   barrier.wait();return self.response(params)
  outcomes=list(Q.parallel_reviews(self.ledger,list(states),lambda a,b:states[a,b],Q.DEFAULT,16,lambda:False,transport=transport))
  self.assertEqual(outcomes,['accepted']*16)
  self.assertAlmostEqual(self.ledger.spent(),16*.000535)

 def test_parallel_budget_limit_drains_inflight_and_counts_reservations(self):
  from project_budget import configure
  states=self.parallel_states(32)
  body=json.dumps(Q.payload(next(iter(states.values())),Q.DEFAULT),ensure_ascii=False).encode()
  pin,pout=Q.price(Q.DEFAULT,len(body)+8192)
  bound=((len(body)+8192)*pin+(Q.MAX_OUTPUT+16)*pout)/1e6
  configure(self.ledger,bound*2+.000001,{},0)
  release=threading.Event()
  def transport(params):
   if not release.wait(5):raise AssertionError('In-flight requests were not drained')
   raw=self.response(params);raw['usage']={};return raw
  outcomes=[]
  for outcome in Q.parallel_reviews(self.ledger,list(states),lambda a,b:states[a,b],Q.DEFAULT,16,lambda:False,transport=transport):
   outcomes.append(outcome)
   if outcome=='budget_limited':release.set()
  self.assertEqual(outcomes.count('invalid'),2)
  self.assertIn('budget_limited',outcomes)
  self.assertLessEqual(self.ledger.spent(),bound*2+.000001)
  self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM calls WHERE status='reserved'").fetchone()[0],0)

 def test_duplicate_parallel_pair_is_only_sent_once(self):
  outcomes=list(Q.parallel_reviews(self.ledger,[('a','b')]*32,lambda a,b:self.state,Q.DEFAULT,16,lambda:False,transport=self.response))
  self.assertEqual(outcomes.count('accepted'),1);self.assertEqual(outcomes.count('cached'),31)
  self.assertAlmostEqual(self.ledger.spent(),.000535)

 def test_known_unbilled_rate_limit_can_resume(self):
  def limited(_):raise HTTPError('https://example.org',429,'rate limit',{},None)
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,limited),'rate_limited')
  self.assertEqual(self.ledger.spent(),0)
  self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,self.response),'accepted')
  self.assertAlmostEqual(self.ledger.spent(),.000535)

 def test_shutdown_does_not_admit_new_requests(self):
  outcomes=list(Q.parallel_reviews(self.ledger,[('a','b')],lambda a,b:self.state,Q.DEFAULT,4,lambda:True,transport=lambda _:self.fail('sent after shutdown')))
  self.assertEqual(outcomes,[])

 def test_user_pause_blocks_direct_real_provider_calls(self):
  from unittest.mock import patch
  with patch.object(Q.C.J,'E',Path(self.tmp.name)):
   (Path(self.tmp.name)/'QWEN_PAUSED').touch()
   self.assertEqual(Q.review(self.ledger,'a','b',self.state,Q.DEFAULT),'paused')
   self.assertEqual(self.ledger.spent(),0)

if __name__=='__main__':unittest.main()
