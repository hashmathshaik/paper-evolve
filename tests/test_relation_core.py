import concurrent.futures
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from relation_core import Ledger, validate


class RelationshipEvidence(unittest.TestCase):
    def setUp(self):
        self.state={'paper_a':{'abstract':'A introduces a quantized cache for language models.'},
                    'paper_b':{'abstract':'We extend the quantized cache with adaptive precision.'},'citing_sentence':''}
        self.result={'related':True,'basis':'explicit_statement','relations':[{'type':'Extends','confidence':.95}],
                     'reason':'Adds precision control.','inherited':'Quantized cache.','changed':'Adaptive precision.',
                     'evidence':[{'source':'b_abstract','quote':self.state['paper_b']['abstract']}]}

    def test_fabricated_quote_cannot_create_edge(self):
        self.result['evidence'][0]['quote']='This quotation never appeared in either abstract.'
        result=validate(self.result,self.state)
        self.assertFalse(result['related']);self.assertEqual(result['types'],{})
        self.assertEqual(result['inherited'],'');self.assertEqual(result['changed'],'')

    def test_revival_needs_explicit_evidence_basis(self):
        self.result['relations']=[{'type':'Revives','confidence':.99}]
        self.result['basis']='contribution_comparison'
        self.assertFalse(validate(self.result,self.state)['related'])

    def test_citation_or_similarity_is_not_a_relation_type(self):
        for name in ('Cites','Similar'):
            self.result['relations']=[{'type':name,'confidence':.99}]
            with self.assertRaises(ValueError):validate(self.result,self.state)

    def test_multilabel_survives_and_weak_type_is_rejected(self):
        self.result['relations']+=[{'type':'Transfers','confidence':.9},{'type':'Combines','confidence':.4}]
        self.assertEqual(set(validate(self.result,self.state)['types']),{'Extends','Transfers'})


class BudgetReservations(unittest.TestCase):
    def test_concurrent_workers_cannot_overbook_and_restart_keeps_reservations(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.sqlite3';ledger=Ledger(path,1)
            def reserve(i):return ledger.reserve(str(i),'a','b','model',{},.3)
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                results=list(pool.map(reserve,range(20)))
            self.assertEqual(sum(results),3);self.assertAlmostEqual(ledger.spent(),.9)
            resumed=Ledger(path,1)
            self.assertFalse(resumed.reserve('new','a','b','model',{},.3))
            self.assertFalse(resumed.reserve('0','a','b','model',{},.01))
            ledger.finish('0',None,{},.1,'invalid','Invalid paid response')
            self.assertTrue(resumed.reserve('new','a','b','model',{},.3))
            self.assertAlmostEqual(resumed.spent(),1)


if __name__=='__main__':unittest.main()
