import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/pipeline'))
import relation_screen as S
import qwen_relations as Q
from relation_core import Ledger

class TwoStageFlow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.ledger=Ledger(Path(self.temp.name)/'test.db',1);S.setup(self.ledger)
        self.state={'paper_a':{'title':'A','abstract':'Earlier source abstract.','year':2020},'paper_b':{'title':'B','abstract':'Later source abstract.','year':2021},'citing_sentence':'','source_evidence':{'status':'ready','passages':[]}}
    def screen(self,passed=True,audit=False):
        self.ledger.db.execute('INSERT OR REPLACE INTO screens VALUES (?,?,?,?,?)',('a','b',S.fingerprint(self.state),json.dumps({'passed':passed,'audit':audit}),'test'));self.ledger.db.commit()
    def prepare(self):
        def response(params):
            result={'related':False,'basis':'insufficient_evidence','relations':[],'reason':'No explicit inheritance.','inherited':'','changed':'','evidence_ids':[]}
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],
                    'usage':{'prompt_tokens':2000,'completion_tokens':300}}
        return Q.review(self.ledger,'a','b',self.state,Q.DEFAULT,response)
    def test_unscreened_and_rejected_pairs_never_reach_provider(self):
        self.assertEqual(self.prepare(),'needs_evidence_or_screen')
        self.screen(False,False);self.assertEqual(self.prepare(),'needs_evidence_or_screen')
        self.assertEqual(self.ledger.spent(),0)
    def test_positive_and_sampled_negative_pass_and_resume_deduplicates(self):
        self.screen(False,True);self.assertEqual(self.prepare(),'abstained')
        self.assertEqual(self.prepare(),'cached')
    def test_canceled_unbilled_request_can_resume_without_losing_history(self):
        self.ledger.reserve('canceled','a','b','qwen',{},.2)
        self.ledger.finish('canceled',None,{},0,'batch_canceled')
        self.assertTrue(self.ledger.reserve('canceled','a','b','qwen',{},.2))
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM canceled_history').fetchone()[0],1)
    def test_cached_positives_do_not_allow_unbounded_negative_audits(self):
        pairs=[]
        for i in range(100):
            pair=(str(i),'b');pairs.append(pair)
            state={**self.state,'paper_a':{**self.state['paper_a'],'title':str(i)}}
            self.ledger.db.execute('INSERT INTO screens VALUES (?,?,?,?,?)',(*pair,S.fingerprint(state),json.dumps({'passed':False,'audit':True}),'test'))
        self.ledger.db.commit()
        rows,_=S.eligible(self.ledger,pairs)
        self.assertEqual(len(rows),1)
    def test_changed_abstract_invalidates_screen(self):
        self.screen();self.state['paper_a']['abstract']='Changed source text.'
        self.assertEqual(self.prepare(),'needs_evidence_or_screen')
    def test_both_models_share_spending_cap(self):
        self.assertTrue(self.ledger.reserve('screen','a','b','jev',{},.8))
        self.assertFalse(self.ledger.reserve('review','c','d','qwen',{},.3))
    def test_audit_sampling_is_deterministic_and_not_all_rejects(self):
        answers={k:{'noul':.1} for k in ['related',*S.H.J.TYPES]}
        sampled=[i for i in range(1000) if S.decision(str(i),'b',answers)['audit']]
        self.assertTrue(20<len(sampled)<90)
        self.assertEqual(sampled,[i for i in range(1000) if S.decision(str(i),'b',answers)['audit']])
    def test_topic_similarity_does_not_pass_related_gate(self):
        answers={k:{'noul':.99} for k in ['related',*S.H.J.TYPES]};answers['related']['noul']=.1
        self.assertFalse(S.decision('a','b',answers)['passed'])

if __name__=='__main__':unittest.main()
