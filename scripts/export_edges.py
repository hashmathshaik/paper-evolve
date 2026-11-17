"""Publish validated relationship predictions and Voyage similarity shards.
References are provenance only, never a sixth evolution type. API credentials,
source abstracts, and local billing records are excluded from the public export.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from voyage_pipeline import ROOT, read_records, atomic_json
from relation_core import TYPES, VERSION
from relation_review_policy import load_policy,apply_policy

SHARD = 500
OUT = ROOT / 'evolve/generated/edges'


def main():
    recs = read_records('corpus'); index = {r['id']:i for i,r in enumerate(recs)}; n = len(recs)
    nb = [{'c':[], 's':[], 'checked':0} for _ in recs]
    d = np.load(ROOT/'work/edges/knn.npz'); ids, idx, sim = d['ids'], d['idx'], d['sim']
    for i, pid in enumerate(ids):
        if pid not in index: continue
        nb[index[pid]]['s'] = [[index[ids[j]],round(float(s),3)] for j,s in zip(idx[i],sim[i]) if ids[j] in index and s < .99][:5]
    counts = {name:0 for name in TYPES}; classified = set(); models = set(); accepted = 0;fulltext_count=0
    path = ROOT/'work/edges/relations.sqlite3'
    best = {}; policies=load_policy();withheld=0
    if path.exists():
        with sqlite3.connect(path) as db:
            versions=dict(db.execute('SELECT id,version FROM request_specs')) if db.execute("SELECT 1 FROM sqlite_master WHERE name='request_specs'").fetchone() else {}
            for identity,a,b,model,state,result in db.execute("SELECT id,a,b,model,state,result FROM calls WHERE status='complete' ORDER BY rowid"):
                best[(a,b)] = (model,json.loads(state),json.loads(result),versions.get(identity,'legacy-unrecorded'))
    for (a,b),(model,state,result,prompt_version) in best.items():
        if a not in index or b not in index: continue
        classified.update([a,b]); models.add(model); nb[index[a]]['checked']+=1; nb[index[b]]['checked']+=1
        result=apply_policy(a,b,result,policies)
        if result is None:
            withheld+=1;continue
        types = {k:v for k,v in result.get('types',{}).items() if k in TYPES and v >= .85}
        if not result.get('related') or not types: continue
        if recs[index[a]]['year'] >= recs[index[b]]['year']: continue
        evidence = result.get('evidence',[])
        if not evidence: continue
        # Full exact quotes are retained rather than truncating away their meaning.
        context = next((e['quote'] for e in evidence if e['source']=='citing_sentence'),None)
        info = {k:result[k] for k in ['reason','inherited','changed','basis','evidence']}
        if result.get('assistant_review'):info['assistant_review']=result['assistant_review']
        if result.get('verification'):info['verification']=result['verification']
        tier=result.get('quality_tier','abstract_only_prediction')
        fulltext_count+=tier=='fulltext_supported_prediction'
        info.update(quality_tier=tier,model=model, version=prompt_version, citation_backed=state.get('reference_list_contains_a')==1)
        mode = 'modelstudio' if result.get('provider') == 'modelstudio' else ('qwen' if model.startswith('qwen') else 'historical_model')
        row = [types,max(types.values()),result['inherited'],result['changed'],context,mode,info]
        nb[index[b]]['c'].append([index[a],-1]+row)
        nb[index[a]]['c'].append([index[b],1]+row)
        accepted += 1
        for name in types: counts[name] += 1
    OUT.mkdir(parents=True,exist_ok=True)
    for k in range(0,n,SHARD):
        part = {str(i):nb[i] for i in range(k,min(n,k+SHARD)) if nb[i]['c'] or nb[i]['s']}
        target=OUT/f'{k//SHARD:03d}.json'; temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(part,separators=(',',':'),ensure_ascii=False));temp.replace(target)
    meta = {'shard_size':SHARD,'papers':n,'embedding_model':'voyage-4-large','classifier':sorted(models),
            'edges':accepted,'fulltext_supported_predictions':fulltext_count,'abstract_only_predictions':accepted-fulltext_count,'withheld_after_assistant_review':withheld,'human_verified':False,'relation_counts':counts,'classified_pairs':len(best),'classified_papers':len(classified),
            'papers_with_similarity':sum(bool(x['s']) for x in nb),'generated_at':datetime.now(timezone.utc).isoformat(),
            'type_threshold_shown':.85,'score_description':'Model self-assessment; not calibrated accuracy','current_prompt_version':VERSION}
    atomic_json(OUT/'meta.json',meta)
    print(json.dumps(meta))


if __name__=='__main__': main()
