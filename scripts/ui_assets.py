"""Give local and hosted UI assets stable content-based cache versions."""
import hashlib,re
from pathlib import Path

VERSION=re.compile(r'(\.(?:js|css))\?v=[A-Za-z0-9_.-]+')

def version_ui(root):
    root=Path(root)
    paths=[root/'index.html',*([root/'contribute.html'] if (root/'contribute.html').exists() else []),*sorted((root/'evolve').glob('*.js')),*sorted((root/'evolve').glob('*.css'))]
    source={path:path.read_text() for path in paths}
    canonical='\0'.join(str(path.relative_to(root))+'\0'+VERSION.sub(r'\1?v=BUILD',text) for path,text in source.items())
    identity=hashlib.sha256(canonical.encode()).hexdigest()[:12]
    for path,text in source.items():
        updated=VERSION.sub(lambda match:match[1]+'?v='+identity,text)
        if updated!=text:path.write_text(updated)
    return identity
