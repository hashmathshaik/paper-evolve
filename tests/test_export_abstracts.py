import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from export_abstracts import export,public_url

class ReaderExport(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.corpus=self.root/'corpus.json';self.cache=self.root/'cache.db';self.out=self.root/'abstracts'
  self.corpus.write_text(json.dumps([{'u':f'https://example.org/{i}'} for i in range(3)]))
  with sqlite3.connect(self.cache) as db:
   db.execute('CREATE TABLE abstracts(url,abstract,retrieved_at,endpoint)')
   for i in range(3):db.execute('INSERT INTO abstracts VALUES (?,?,?,?)',(f'https://example.org/{i}',f'Abstract {i}: '+'Research evidence. '*5,'2026-11-14','https://api.example.org/works/123?api_key=secret'))
 def test_ordered_shards_preserve_exact_text_without_credentials(self):
  result=export(self.corpus,self.cache,self.out,2)
  self.assertEqual(result['abstracts'],3);self.assertEqual(result['shards'],2)
  rows=json.loads((self.out/'000.json').read_text())+json.loads((self.out/'001.json').read_text())
  self.assertEqual([r['url'] for r in rows],[f'https://example.org/{i}' for i in range(3)])
  self.assertEqual(rows[2]['abstract'],'Abstract 2: '+('Research evidence. '*5).strip())
  self.assertTrue(all(r['source_url']=='https://api.example.org/works/123' for r in rows))
  self.assertNotIn('secret',''.join(p.read_text() for p in self.out.glob('*.json')))
 def test_missing_abstract_does_not_publish_a_partial_collection(self):
  with sqlite3.connect(self.cache) as db:db.execute('DELETE FROM abstracts WHERE url=?',('https://example.org/1',))
  with self.assertRaises(ValueError):export(self.corpus,self.cache,self.out,2)
  self.assertFalse(self.out.exists())
 def test_private_or_unsafe_source_urls_are_not_exported(self):
  self.assertEqual(public_url('https://user:password@example.org/x'),'')
  self.assertEqual(public_url('javascript:alert(1)'),'')
  self.assertEqual(public_url('https://example.org/x?token=secret#private'),'https://example.org/x')
  self.assertEqual(public_url('https://openreview.net/forum?id=paper123&api_key=secret'),'https://openreview.net/forum?id=paper123')
  self.assertEqual(public_url('https://huggingface.co/datasets/team/papers/resolve/main/data.parquet'),'https://huggingface.co/datasets/team/papers/blob/main/data.parquet')

if __name__=='__main__':unittest.main()
