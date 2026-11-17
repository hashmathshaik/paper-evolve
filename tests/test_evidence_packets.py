import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import evidence_packets as E
from relation_core import validate

class SourcePackets(unittest.TestCase):
 def test_references_are_not_citing_paragraphs(self):
  text='A useful method paragraph. '*10+'\n\nReferences\n\n[1] The cited title. '+'x'*100
  self.assertEqual(len(E.paragraphs(text)),1)
 def test_numeric_reference_must_match_its_own_entry(self):
  text='Body\nReferences\n[1] Someone. Unrelated paper.\n[2] Author. Exact Source Title.\n[3] Last. Other.'
  self.assertEqual(E.reference_number(text,'Exact Source Title'),'2')
 def test_fulltext_review_cannot_publish_using_abstracts_alone(self):
  state={'paper_a':{'abstract':'Earlier method with an exact solver.'},'paper_b':{'abstract':'We extend the earlier method to a relaxed solver.'},'source_evidence':{'status':'ready','passages':[{'id':'b_citation_1','text':'We generalize Method A by relaxing its exact solver requirement.','url':'https://example.org/b.pdf','page':2,'document_sha256':'abc'}]}}
  result={'related':True,'basis':'explicit_statement','relations':[{'type':'Extends','confidence':.95}],'reason':'Generalizes method.','inherited':'Method A.','changed':'Relaxed solver.','evidence':[{'source':'a_abstract','quote':state['paper_a']['abstract']},{'source':'b_abstract','quote':state['paper_b']['abstract']}]}
  self.assertFalse(validate(result,state)['related'])
  result['evidence'].append({'source':'b_citation_1','quote':state['source_evidence']['passages'][0]['text']})
  checked=validate(result,state);self.assertTrue(checked['related']);self.assertEqual(checked['quality_tier'],'fulltext_supported_prediction')
  self.assertEqual(checked['evidence'][-1]['page'],2)
  state['source_evidence']['status']='needs_context';self.assertFalse(validate(result,state)['related'])
 def test_fabricated_fulltext_excerpt_cannot_pass(self):
  state={'paper_a':{'abstract':'A source abstract with a named method.'},'paper_b':{'abstract':'B source abstract.'},'source_evidence':{'status':'ready','passages':[]}}
  result={'related':True,'basis':'explicit_statement','relations':[{'type':'Challenges','confidence':1}],'reason':'Claim.','inherited':'Something.','changed':'Something else.','evidence':[{'source':'b_citation_1','quote':'A nonexistent critical passage with more than sixteen characters.'}]}
  self.assertFalse(validate(result,state)['related'])

if __name__=='__main__':unittest.main()
