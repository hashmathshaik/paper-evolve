"""Conservative publication policies from source-evidence review. Never rewrite raw API results."""
import json
from pathlib import Path
from voyage_pipeline import ROOT

def load_policy(path=None):
    path=Path(path) if path else ROOT/'evolve/review-policy.json'
    if not path.exists():return {}
    return {(p['a'],p['b']):p for p in json.loads(path.read_text())['policies']}

def apply_policy(a,b,result,policies):
    policy=policies.get((a,b))
    if not policy:return result
    if policy['action']=='withhold':return None
    if policy['action']=='restrict_types':
        types={k:v for k,v in result.get('types',{}).items() if k in policy['allowed_types']}
        if not types:return None
        return {**result,'types':types,'assistant_review':{'review_id':policy['review_id'],'human_verified':False,'note':policy['reason']}}
    if policy['action']=='infer_basis':
        return {**result,'basis':'contribution_comparison','assistant_review':{'review_id':policy['review_id'],'human_verified':False,'note':policy['reason']}}
    raise ValueError('Unknown review action; refusing to publish')
