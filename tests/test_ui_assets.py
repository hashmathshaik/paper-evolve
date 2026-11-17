import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from ui_assets import version_ui

class UIVersions(unittest.TestCase):
 def test_real_edits_refresh_all_references_without_version_churn(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'evolve').mkdir()
   (root/'index.html').write_text('<script src="evolve/app.js?v=old"></script>')
   (root/'evolve/app.js').write_text('import "./reader.js?v=other";')
   (root/'evolve/reader.js').write_text('export const content="first";')
   first=version_ui(root)
   self.assertIn('?v='+first,(root/'index.html').read_text())
   self.assertIn('?v='+first,(root/'evolve/app.js').read_text())
   self.assertEqual(first,version_ui(root))
   (root/'evolve/reader.js').write_text('export const content="second";')
   second=version_ui(root)
   self.assertNotEqual(first,second)
   self.assertIn('?v='+second,(root/'index.html').read_text())
   self.assertEqual(second,version_ui(root))
