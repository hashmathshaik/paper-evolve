import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from relation_core import Ledger
from project_budget import configure,configure_edges

class ProjectBudget(unittest.TestCase):
    def test_historical_cost_and_contingency_limit_every_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.db'
            first=Ledger(path,50)
            configure(first,50,{'historical':18},2)
            self.assertTrue(first.reserve('one','a','b','test',{},29))
            resumed=Ledger(path,500)
            self.assertFalse(resumed.reserve('two','a','c','test',{},1.01))
            self.assertTrue(resumed.reserve('three','a','d','test',{},1))
            self.assertEqual(resumed.project_snapshot()['remaining_request_allowance_usd'],0)
            first.finish('one',None,{},28,'complete')
            self.assertTrue(resumed.reserve('four','a','e','test',{},1))
            self.assertFalse(first.reserve('five','a','f','test',{},.001))

    def test_invalid_configuration_preserves_existing_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=Ledger(Path(directory)/'ledger.db',50)
            configure(ledger,50,{'historical':18},2)
            for maximum in [float('nan'),19]:
                with self.assertRaises(ValueError):configure(ledger,maximum,{'historical':18},2)
            self.assertEqual(ledger.project_snapshot()['maximum_usd'],50)

    def test_edge_ceiling_survives_a_worker_opening_with_larger_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.db'
            ledger=Ledger(path,50)
            configure(ledger,50,{'historical':17.5},2)
            configure_edges(ledger,30)
            resumed=Ledger(path,500)
            self.assertTrue(resumed.reserve('one','a','b','test',{},29))
            self.assertFalse(resumed.reserve('two','a','c','test',{},1.01))
            self.assertTrue(resumed.reserve('three','a','d','test',{},1))
            self.assertEqual(resumed.project_snapshot()['remaining_request_allowance_usd'],0)

if __name__=='__main__':unittest.main()
