import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from evolution_starters import export


class StartingPapers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'evolve/generated/edges').mkdir(parents=True)
        self.records = [{'t': f'Method {i}', 'u': f'https://example.org/{i}', 'y': 2020+i,
                         'v': 'icml', 'mega': 'Language' if i<3 else 'Vision', 'topic': f'Topic {i}'} for i in range(6)]
        (self.root/'evolve/corpus.json').write_text(json.dumps(self.records))

    def row(self, other, direction, source=True):
        return [other,direction,{'Extends':.95},.95,'Inherited','Changed',None,'modelstudio',
                {'quality_tier':'fulltext_supported_prediction' if source else 'abstract_only_prediction',
                 'verification':{'method':'two_qwen_model_agreement'}}]

    def save(self, data):
        (self.root/'evolve/generated/edges/000.json').write_text(json.dumps(data))

    def test_recommendations_use_real_passage_supported_edges_and_diverse_areas(self):
        self.save({'0':{'c':[self.row(1,1),self.row(2,1),self.row(5,1,False)]},
                   '1':{'c':[self.row(0,-1)]},'2':{'c':[self.row(0,-1)]},
                   '3':{'c':[self.row(4,1)]},'4':{'c':[self.row(3,-1)]},
                   '5':{'c':[self.row(0,-1,False)]}})
        result=export(self.root,limit=2)
        self.assertEqual(result['papers'],6)
        self.assertEqual(result['edges'],4)
        self.assertEqual({p['mega'] for p in result['starters']},{'Language','Vision'})
        self.assertNotIn(self.records[5]['u'],[p['u'] for p in result['starters']])

    def test_empty_graph_does_not_fall_back_to_a_fake_example(self):
        result=export(self.root)
        self.assertEqual(result['starters'],[])
        self.assertEqual(result['edges'],0)
        self.assertEqual(result['papers'],6)

    def test_accepted_community_withdrawal_overrides_the_old_prediction(self):
        self.save({'0':{'c':[self.row(1,1)]},'1':{'c':[self.row(0,-1)]}})
        (self.root/'evolve/generated/community.json').write_text(json.dumps({'entries':{
            '0':{'c':[],'overrides':[1]},'1':{'c':[],'overrides':[0]}}}))
        result=export(self.root)
        self.assertEqual(result['starters'],[])
        self.assertEqual(result['edges'],0)


if __name__=='__main__':unittest.main()
