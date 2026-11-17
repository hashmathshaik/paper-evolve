import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recover_openalex import unpack_abstract,match_record,retry_seconds
class OpenAlexRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.record={'title':'A Study of Learning','year':2024,'source_url':'https://openreview.net/forum?id=abc'}
  self.work={'id':'https://openalex.org/W1','title':'A Study of Learning','publication_year':2024,'abstract_inverted_index':{'An':[0],'abstract':[1],'with':[2],'enough':[3],'genuine':[4],'scientific':[5],'content.':[6]},'locations':[],'authorships':[{'author':{'display_name':'Jane Smith'}}]}
 def test_retry_after_seconds(self):
  self.assertEqual(retry_seconds('120'),120)
 def test_retry_after_http_date(self):
  self.assertEqual(retry_seconds('Thu, 12 Nov 2026 00:02:00 GMT',current_time=1794441600),120)
 def test_retry_fallback_is_bounded(self):
  self.assertEqual(retry_seconds(None,10),300)
 def test_reconstruction(self):
  self.assertEqual(unpack_abstract(self.work['abstract_inverted_index']),'An abstract with enough genuine scientific content.')
 def test_incomplete_index_rejected(self):
  self.assertIsNone(unpack_abstract({'lost':[1]}))
 def test_exact_title_year_author(self):
  match,reason=match_record(self.record,[self.work],'Jane Smith, John Doe');self.assertEqual(match[2],'exact_title_year_author')
 def test_similar_title_rejected(self):
  work={**self.work,'title':'Reproducibility report for A Study of Learning'}
  self.assertIsNone(match_record(self.record,[work],'Jane Smith')[0])
 def test_wrong_author_rejected(self):
  self.assertIsNone(match_record(self.record,[self.work],'Another Author')[0])
 def test_ambiguous_record_rejected(self):
  other={**self.work,'id':'https://openalex.org/W2'}
  self.assertEqual(match_record(self.record,[self.work,other],'Jane Smith')[1],'ambiguous')
 def test_exact_id_allows_preprint_title_change(self):
  work={**self.work,'title':'Earlier preprint title','locations':[{'landing_page_url':'https://openreview.net/forum?id=abc'}]}
  self.assertEqual(match_record(self.record,[work],'')[0][2],'exact_openreview_id')
if __name__=='__main__':unittest.main()
