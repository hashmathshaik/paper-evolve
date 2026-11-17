import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from relation_review_policy import load_policy,apply_policy
class ReviewedPublication(unittest.TestCase):
 def test_quarantine_survives_new_predictions_without_mutating_cache(self):
  result={'types':{'Challenges':.99},'basis':'explicit_statement'}
  p={('a','b'):{'action':'withhold'}}
  self.assertIsNone(apply_policy('a','b',result,p));self.assertEqual(result['types'],{'Challenges':.99})
 def test_inference_correction_does_not_claim_human_review(self):
  result={'basis':'explicit_statement'}
  p={('a','b'):{'action':'infer_basis','review_id':'test','reason':'Indirect attribution.'}}
  corrected=apply_policy('a','b',result,p)
  self.assertEqual(corrected['basis'],'contribution_comparison');self.assertFalse(corrected['assistant_review']['human_verified'])
  self.assertEqual(result['basis'],'explicit_statement')
 def test_audited_problem_pairs_are_actually_withheld(self):
  policies=load_policy();withheld=[p for p in policies.values() if p['action']=='withhold']
  self.assertEqual(len(withheld),4)
if __name__=='__main__':unittest.main()
