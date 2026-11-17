import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import contribution_repository as R
import contribution_workspace as W
import test_contribution_system as fixtures


class RepositoryContributions(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ContributionSystem()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.workspace = self.fixture.workspace

    def test_explicit_and_pages_build_identity_produce_only_expected_github_links(self):
        self.assertEqual(R.project(self.root, {})['repository_url'], '')
        self.assertEqual(R.project(self.root, {'GITHUB_REPOSITORY':'research/paper-evolve'})['fork_url'], 'https://github.com/research/paper-evolve/fork')
        path = self.root / 'community/project.json'
        path.write_text(json.dumps({'repository':'owner/official'}))
        self.assertEqual(R.project(self.root, {'GITHUB_REPOSITORY':'fork/other'})['repository'], 'owner/official')
        path.write_text(json.dumps({'repository':'https://key@untrusted.example/project'}))
        with self.assertRaises(ValueError):R.project(self.root, {})

    def test_clone_does_not_reoffer_submitted_tasks_when_catalog_is_stale(self):
        self.fixture.prepare();self.fixture.fill()
        W.export(self.workspace, self.root / 'community/submissions/reviewed.json', self.root)
        self.assertEqual(W.manifest(self.root)['packs'][0]['available_tasks'], 1)
        self.assertEqual(W.manifest(self.root, refresh=True)['packs'][0]['available_tasks'], 0)
        with self.assertRaisesRegex(ValueError,'No available tasks'):
            W.prepare(self.fixture.pack_path, self.root/'new-workspace','Name','Model',root=self.root)

    def test_pr_plan_exports_once_and_stages_only_submission_without_git_actions(self):
        self.fixture.prepare();self.fixture.fill()
        with patch.dict(R.os.environ, {}, clear=True):
            result = R.prepare_pr(self.workspace, root=self.root)
            again = R.prepare_pr(self.workspace, root=self.root)
        self.assertEqual(result['output'], again['output'])
        self.assertEqual(len(list((self.root/'community/submissions').glob('*.json'))), 1)
        self.assertFalse(result['pushed']);self.assertFalse(result['pull_request_created'])
        self.assertFalse((self.root/'.git').exists())
        self.assertEqual([c for c in result['commands'] if c.startswith('git add')], ['git add -- '+result['output']])
        self.assertNotIn('work/', (self.workspace/'PULL_REQUEST.md').read_text())
        self.assertNotIn('git add .', (self.workspace/'GIT_STEPS.md').read_text())

    def test_pr_reuses_an_identical_manual_export_and_rejects_escaping_output(self):
        self.fixture.prepare();self.fixture.fill()
        output=self.root/'community/submissions/existing.json'
        W.export(self.workspace,output,self.root)
        result=R.prepare_pr(self.workspace,root=self.root)
        self.assertEqual(result['output'],'community/submissions/existing.json')
        with self.assertRaises(ValueError):R.prepare_pr(self.workspace,self.root/'outside.json',self.root)
        pack=json.loads(self.fixture.pack_path.read_text());pack['description']='Modified committed pack'
        self.fixture.pack_path.write_text(json.dumps(pack))
        with self.assertRaisesRegex(ValueError,'differs from the workspace'):
            R.prepare_pr(self.workspace,root=self.root)

    @unittest.skipUnless(shutil.which('git'), 'Git is required for the actual clone round trip.')
    def test_fresh_git_clone_runs_agent_workflow_without_private_caches(self):
        source=self.root
        (source/'.gitignore').write_text('work/\n__pycache__/\n.env\n')
        root=Path(__file__).parents[1]
        for name in ('AGENTS.md','CLAUDE.md'):(source/name).write_bytes((root/name).read_bytes())
        def git(*args,cwd=source):
            result=subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            return result.stdout
        git('init','-q');git('add','.')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.org','commit','-qm','Prepared contribution project')
        clone=source/'fresh-clone'
        git('clone','-q',str(source),str(clone))
        self.assertFalse((clone/'work').exists())
        def cli(*args):
            result=subprocess.run([sys.executable,'-I','paper_evolve.py',*args],cwd=clone,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            return result.stdout
        self.assertIn('oracle-001',cli('list'))
        cli('start','--pack','oracle-001','--name','Git contributor','--tool','Agent/version')
        work=clone/'work/contributions/oracle-001'
        doc=json.loads((work/'submission.json').read_text());doc['submission']['decisions'][0]['decision']=self.fixture.decision
        (work/'submission.json').write_text(json.dumps(doc))
        cli('check','--workspace',str(work))
        plan=json.loads(cli('pr','--workspace',str(work)))
        git('switch','-c',plan['branch'],cwd=clone)
        git('add','--',plan['output'],cwd=clone)
        self.assertEqual(git('diff','--cached','--name-only',cwd=clone).strip(),plan['output'])
        self.assertNotIn('work/',git('status','--porcelain',cwd=clone))


if __name__=='__main__':unittest.main()
