import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import contribution_sources as S
import contribution_workspace as W
import community_edges as C
import test_contribution_system as fixtures


class ResearchContributions(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ContributionSystem();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare();self.work=self.f.workspace;self.task=self.f.task
        self.a='Our original oracle method provides exact optimization through a reusable estimator.'
        self.b='We extend the original oracle method with a relaxed estimator for larger problems.'
        self.pages={'a':['Original oracle '+('A background sentence. '*60),self.a],
                    'b':['Relaxed oracle '+('B background sentence. '*60),self.b]}
        self.pdf=b'%PDF-1.4\nfixture document bytes'

    def fetch(self,side):
        return S.fetch_papers(self.work,self.task['id'],side,url='https://aclanthology.org/fixture-'+side+'.pdf',
                              fetch=lambda url:(self.pdf+side.encode(),url),extractor=lambda p:(self.pages[side],'fixture extractor'))

    def cite(self,side,quote=None,page=2):
        self.fetch(side);path=self.work/'quote.txt';path.write_text(quote or getattr(self,side))
        with patch.object(S,'extract',return_value=(self.pages[side],'fixture extractor')):
            return S.cite(self.work,self.task['id'],side,page,'citation' if side=='b' else 'passage',path)

    def material(self):
        self.cite('a');self.cite('b')
        return W.load(self.work)[2]['submission']['decisions'][0]['source_material']

    def test_full_paper_quotes_extend_evidence_without_mutating_original_pack(self):
        original=C.digest(C.read_json(self.work/'pack.json'));material=self.material()
        envelope=W.load(self.work)[2];row=envelope['submission']['decisions'][0]
        row['decision']={**copy.deepcopy(self.f.decision),'evidence':[
            {'source':'a_passage_research_1','quote':self.a},{'source':'b_citation_research_1','quote':self.b}]}
        (self.work/'submission.json').write_text(json.dumps(envelope))
        rows=W.check(self.work)
        self.assertTrue(rows[0]['result']['related']);self.assertIn('contributor_retrieved',rows[0]['result']['research_provenance'])
        self.assertEqual(rows[0]['result']['evidence'][1]['page'],2)
        self.assertEqual(C.digest(C.read_json(self.work/'pack.json')),original)
        self.assertEqual(row['task_sha256'],self.task['sha256'])
        output=self.f.root/'community/submissions/research.json';W.export(self.work,output,self.f.root)
        self.assertIn('source_material',C.read_json(output)['submission']['decisions'][0])

    def test_cite_reextracts_and_rejects_fabrication_wrong_page_or_changed_pdf(self):
        with self.assertRaises(ValueError):self.cite('b','This statement never appeared in the PDF.')
        with self.assertRaises(ValueError):self.cite('b',page=1)
        result=self.fetch('a');Path(result['documents'][0]['pdf']).write_bytes(b'changed')
        quote=self.work/'quote.txt';quote.write_text(self.a)
        with self.assertRaisesRegex(ValueError,'changed after extraction'):
            S.cite(self.work,self.task['id'],'a',2,'passage',quote)

    def test_offline_validation_rejects_tampered_excerpt_wrong_paper_and_reserved_ids(self):
        original=self.material()
        for field,value in [('text','Made up source statement.'),('paper_id','different-paper'),('id','a_passage_1'),('url','https://evil.example/paper.pdf')]:
            material=copy.deepcopy(original);material['passages'][0][field]=value
            material['sha256']=S.digest({k:v for k,v in material.items() if k!='sha256'})
            with self.assertRaises(ValueError):S.augment(self.task,material)

    def test_new_source_cannot_override_a_paper_identity_or_task_fingerprint(self):
        material=self.material();material['passages'][0]['paper_title']='Different paper'
        material['sha256']=S.digest({k:v for k,v in material.items() if k!='sha256'})
        with self.assertRaises(ValueError):S.augment(self.task,material)

    def test_incomplete_packet_requires_both_source_sides_and_a_citation(self):
        material=self.material();task=copy.deepcopy(self.task);task['state']['source_evidence']={'status':'needs_context','passages':[]}
        only_b={**material,'passages':[material['passages'][1]]};only_b['sha256']=S.digest({k:v for k,v in only_b.items() if k!='sha256'})
        self.assertEqual(S.augment(task,only_b)['source_evidence']['status'],'needs_context')
        self.assertEqual(S.augment(task,material)['source_evidence']['status'],'ready')

    def test_fetch_checks_title_and_pdf_content_before_registration(self):
        with self.assertRaises(ValueError):
            S.fetch_papers(self.work,self.task['id'],'a',url='https://arxiv.org/pdf/test',fetch=lambda u:(b'<html>Not a paper</html>',u))
        with self.assertRaisesRegex(ValueError,'title does not match|text/title does not match'):
            S.fetch_papers(self.work,self.task['id'],'a',url='https://arxiv.org/pdf/test',fetch=lambda u:(self.pdf,u),extractor=lambda p:(['Wrong title '+'text '*400],'fixture'))

    def test_cached_paper_reuse_verifies_bytes_and_does_not_redownload(self):
        first=self.fetch('a')
        index=json.loads((self.work/'research/index.json').read_text());identity=index[self.task['id']+':a']
        before=json.loads((self.work/'research/documents'/(identity+'.json')).read_text())['retrieved_at']
        result=S.fetch_papers(self.work,self.task['id'],'a',fetch=lambda _:self.fail('Cached source requested again'),extractor=lambda p:(self.pages['a'],'fixture extractor'))
        self.assertTrue(result['documents'][0]['cached'])
        self.assertEqual(json.loads((self.work/'research/documents'/(identity+'.json')).read_text())['retrieved_at'],before)

    def test_accepted_research_preserves_provenance_without_human_verification(self):
        self.material();envelope=W.load(self.work)[2]
        row=envelope['submission']['decisions'][0]
        row['decision']={**copy.deepcopy(self.f.decision),'evidence':[{'source':'a_passage_research_1','quote':self.a},{'source':'b_citation_research_1','quote':self.b}]}
        approved=self.f.root/'community/approved/research.json'
        C.accept(self.f.pack,envelope['submission'],approved,'Assistant reviewer','assistant','Checked the source excerpts; separate published-source verification is still required.')
        records=[{'id':side,'title':self.f.state['paper_'+side]['title'],'year':self.f.state['paper_'+side]['year'],'source_url':self.f.fixture.papers[side]['source_url']} for side in ('a','b')]
        corpus=self.f.root/'corpus.json';corpus.write_text(json.dumps(records))
        overlay=C.export_static(self.f.root/'overlay.json',corpus,approved.parent)
        evidence=overlay['entries']['0']['c'][0][-1]
        self.assertFalse(evidence['human_verified'])
        self.assertIn('contributor_retrieved',evidence['research_provenance'])

    def test_url_and_redirect_rules_reject_private_or_credential_destinations(self):
        for url in ['https://127.0.0.1/x.pdf','http://arxiv.org/pdf/test','https://key@arxiv.org/pdf/test','https://arxiv.org/pdf/test?token=secret','https://arxiv.org:8443/pdf/test']:
            with self.assertRaises(ValueError):S.official_url(url)
        with self.assertRaises(ValueError):S.Redirects().redirect_request(None,None,302,'redirect',{},'https://127.0.0.1/private')
        self.assertEqual(S.pdf_url('https://aclanthology.org/P18-1001.pdf'),'https://aclanthology.org/P18-1001.pdf')
        self.assertEqual(S.pdf_url('https://arxiv.org/abs/1234.56789'),'https://arxiv.org/pdf/1234.56789')

    def test_api_receives_researched_evidence_and_recovers_it_after_interruption(self):
        material=self.material();path=self.work/'submission.json';envelope=C.read_json(path)
        envelope['submission']['contributor']['method']='api';path.write_text(json.dumps(envelope))
        decision=copy.deepcopy(self.f.decision);decision['evidence']=[{'source':'a_passage_research_1','quote':self.a},{'source':'b_citation_research_1','quote':self.b}]
        def response(params):
            prompt=json.loads(params['messages'][1]['content']);self.assertTrue(any(p['id']=='b_citation_research_1' for p in prompt['state']['source_evidence']['passages']))
            raw=self.f.response(params);raw['choices'][0]['message']['content']=json.dumps(decision);return raw
        result=self.f.api(response);self.assertEqual(result['valid_decisions'],1)
        envelope=C.read_json(path);envelope['submission']['decisions']=[];path.write_text(json.dumps(envelope))
        self.f.api(lambda _:self.fail('Completed research request repeated'))
        self.assertEqual(C.read_json(path)['submission']['decisions'][0]['source_material'],material)
        self.assertTrue(W.check(self.work)[0]['result']['related'])


if __name__=='__main__':unittest.main()
