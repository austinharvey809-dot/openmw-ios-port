"""Acquire the pinned, genuine non-JIT Lua runtime with verified HTTPS."""
import argparse
import hashlib
import io
import json
import ssl
import tarfile
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def acquire(output,archive=None,cafile=None):
    lock=json.loads((ROOT/'dependencies.json').read_text())['lua']
    if archive:
        raw=archive.read_bytes()
    else:
        context=ssl.create_default_context(cafile=str(cafile) if cafile else None)
        with urllib.request.urlopen(lock['url'],context=context,timeout=90) as response:
            raw=response.read(lock['bytes']+1)
    if len(raw)!=lock['bytes'] or hashlib.sha256(raw).hexdigest()!=lock['sha256']:
        raise ValueError('Lua archive size/hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as stream:
        members=stream.getmembers()
        for item in members:
            p=Path(item.name)
            if not (item.isfile() or item.isdir()) or p.is_absolute() or '..' in p.parts or p.parts[0]!='lua-'+lock['version']:
                raise ValueError('Unsafe Lua archive member')
        output.mkdir(parents=True,exist_ok=True)
        (output/('lua-'+lock['version']+'.tar.gz')).write_bytes(raw)
        stream.extractall(output,filter='data')
    source=output/('lua-'+lock['version'])
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as stream:
        expected={m.name.split('/',1)[1]:hashlib.sha256(stream.extractfile(m).read()).hexdigest()
                  for m in stream.getmembers() if m.isfile()}
    actual={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    if actual!=expected:raise ValueError('Lua extracted source inventory/hash mismatch')
    (output/'lua-source.json').write_text(json.dumps({'archive':lock,'files':expected},indent=2)+'\n',encoding='utf-8')
    return source


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--cafile',type=Path)
    a=p.parse_args();print(acquire(a.output,a.archive,a.cafile))
