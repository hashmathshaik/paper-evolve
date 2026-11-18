"""Package public static assets. Never copy API jobs, caches, env files or vectors."""
from pathlib import Path
import shutil
import sys
root=Path(__file__).parent
sys.path.insert(0,str(root/'scripts'))
from community_edges import export_static
export_static()
from evolution_starters import export as export_starters
export_starters(root)
from scripts.ui_assets import version_ui
version_ui(root)
from contribution_packs import bundles
bundles(root)
from contribution_repository import project
from voyage_pipeline import atomic_json
abstract_cache=root/'work/abstracts/cache.sqlite3'
abstract_meta=root/'evolve/generated/abstracts/meta.json'
if abstract_cache.exists() and (not abstract_meta.exists() or
        max(abstract_cache.stat().st_mtime,(root/'evolve/corpus.json').stat().st_mtime)>abstract_meta.stat().st_mtime):
    from scripts.export_abstracts import export
    export(root/'evolve/corpus.json',abstract_cache,abstract_meta.parent)
out=root/'dist'
if out.exists():
    shutil.rmtree(out)
out.mkdir()
for name in ['index.html','contribute.html','fonts','assets','LICENSE','EVOLVE.md','CONTRIBUTING.md','README.md','docs/MAINTAINING.md','docs/decisions']:
    src=root/name
    if src.is_dir():
        shutil.copytree(src,out/name)
    elif src.exists():
        (out/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,out/name)
community=root/'community'
if community.exists():
    for name in ['tasks','bundles','REVIEW_PROMPT.md','API.md','CLONE.md','RESEARCH.md','PAPERS.md','venues.json','decision.schema.json','submission-template.json','task-manifest.json']:
        src=community/name
        if src.is_dir():shutil.copytree(src,out/'community'/name)
        elif src.exists():
            (out/'community').mkdir(exist_ok=True)
            shutil.copy2(src,out/'community'/name)
atomic_json(out/'community/project.json',project(root))
for src in (root/'evolve').rglob('*'):
    if src.is_file() and src.suffix in {'.js','.css','.json'}:
        dest=out/src.relative_to(root)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)
(out/'.nojekyll').touch()
print('Built public static app in',out)
