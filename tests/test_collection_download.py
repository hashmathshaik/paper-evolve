import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_collection import acl_collection,parse_acl
class CollectionDownloadTests(unittest.TestCase):
 def test_modern_collection_not_volume(self):
  self.assertEqual(acl_collection('https://aclanthology.org/2024.acl-long.1/'),'2024.acl')
 def test_old_collection(self):
  self.assertEqual(acl_collection('https://aclanthology.org/P18-1001/'),'P18')
 def test_legacy_identity_and_markup(self):
  abstract='This abstract includes <i>scientific</i> text and preserves its meaning.'
  rows=parse_acl('<collection id="P18"><volume id="1"><paper id="1"><abstract>'+abstract+'</abstract></paper></volume></collection>')
  self.assertIn('https://aclanthology.org/P18-1001/',rows);self.assertIn('scientific text',rows['https://aclanthology.org/P18-1001/'])
 def test_missing_abstract_is_not_fabricated(self):
  self.assertEqual(parse_acl('<collection id="2024.acl"><volume id="long"><paper id="1"><title>A paper</title></paper></volume></collection>'),{})
if __name__=='__main__':unittest.main()
