import hashlib
import json
from pathlib import Path
import sys

def verify(source):
    lock=json.loads((Path(__file__).resolve().parents[1]/'dependencies.json').read_text())['lua']
    report=json.loads((source.parent/'lua-source.json').read_text())
    if report['archive']!=lock:raise ValueError('Lua dependency pin mismatch')
    # Reopen the archive, not just an editable extracted-source manifest.
    archive=source.parent/('lua-'+lock['version']+'.tar.gz')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=lock['sha256']:raise ValueError('Lua archive changed')
    import tarfile
    with tarfile.open(archive,'r:gz') as stream:
        expected={m.name.split('/',1)[1]:hashlib.sha256(stream.extractfile(m).read()).hexdigest() for m in stream.getmembers() if m.isfile()}
    if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):raise ValueError('Lua source symlinks are forbidden')
    actual={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    if actual!=expected or report['files']!=expected:raise ValueError('Lua exact source inventory/hash mismatch')
    return len(actual)

if __name__=='__main__':print('Verified Lua source files:',verify(Path(sys.argv[1])))
