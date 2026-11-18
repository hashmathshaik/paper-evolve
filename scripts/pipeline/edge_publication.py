"""Serialize static edge publication across concurrent local review workers."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import fcntl
import subprocess
import sys
from voyage_pipeline import ROOT


def publish():
    path = ROOT / 'work/edges/publication.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for script in ('scripts/pipeline/export_edges.py', 'build_evolve.py'):
            subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)
