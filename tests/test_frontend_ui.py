import subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
JSC=Path('/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc')
class FrontendText(unittest.TestCase):
 @unittest.skipUnless(JSC.exists(),'JavaScriptCore is needed for the standalone browser-helper check')
 def test_real_formatting_helpers_and_bundled_math_reject_executable_content(self):
  result=subprocess.run([str(JSC),str(ROOT/'assets/vendor/katex/katex.min.js'),str(ROOT/'tests/frontend-ui.mjs')],capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('Frontend text and math checks passed.',result.stdout)
