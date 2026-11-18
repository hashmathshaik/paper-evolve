"""Compute research similarities locally, validate records, and package static files."""
import subprocess,sys
from pathlib import Path
root=Path(__file__).parent
for command in [['evolve/embed.py'],['-m','unittest','discover','-s','tests'],['build_evolve.py']]:
 subprocess.run([sys.executable,*command],cwd=root,check=True)
print('Ready: dist/. All research computation completed locally; no API keys required.')
