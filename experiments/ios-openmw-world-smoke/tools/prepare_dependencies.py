"""Acquire G4-only upstream source archives with normal TLS and exact SHA-512.

No system installation, CMake downloads, credentials, or upstream edits.
"""
import argparse,hashlib,json,ssl,stat,urllib.request,urllib.parse,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def members(archive,prefixes=None):
    seen=set();prefix=None
    for item in archive.infolist():
        name=item.filename
        if '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') for p in name.rstrip('/').split('/')):
            raise ValueError('Unsafe archive member')
        parts=name.split('/');top=parts.pop(0)
        if prefix is None:prefix=top
        if top!=prefix or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Archive root/symlink mismatch')
        relative='/'.join(parts).rstrip('/')
        if not relative:continue
        if relative in seen:raise ValueError('Duplicate archive member')
        seen.add(relative)
        if prefixes and not any(relative==p or relative.startswith(p) for p in prefixes):continue
        yield relative,item

def verify_source(archive,target,prefixes=None):
    expected={}
    for name,item in members(archive,prefixes):
        if not item.is_dir():expected[name]=hashlib.sha256(archive.read(item)).hexdigest()
    actual={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in target.rglob('*') if p.is_file()}
    if actual!=expected:raise ValueError('Dependency source inventory/hash mismatch: '+target.name)
    return len(expected)

def prepare(output,cafile=None,offline=False):
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    if output.is_relative_to(ROOT.parents[1]) and not output.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Dependency output must be outside source or under artifacts')
    lock=json.loads((ROOT/'dependencies.json').read_text());result={}
    context=ssl.create_default_context(cafile=str(cafile) if cafile else None)
    for name,entry in lock['sources'].items():
        archive_path=output/(name+'.zip');target=output/name
        if not archive_path.exists():
            if offline:raise ValueError('Missing verified dependency archive: '+name)
            url=urllib.parse.urlsplit(entry['url'])
            if url.scheme!='https' or url.hostname not in ('codeload.github.com','archives.boost.io'):raise ValueError('Unexpected source origin')
            request=urllib.request.Request(entry['url'],headers={'User-Agent':'OpenMW-iOS-G4-source-verification'})
            with urllib.request.urlopen(request,context=context,timeout=120) as response:
                if not response.url.startswith('https://'):raise ValueError('Non-HTTPS redirect')
                with archive_path.open('xb') as stream:
                    while block:=response.read(1024*1024):stream.write(block)
        with archive_path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha512').hexdigest()
        if actual!=entry['sha512']:raise ValueError('Dependency archive SHA-512 mismatch: '+name)
        with zipfile.ZipFile(archive_path) as archive:
            if not target.exists():
                target.mkdir()
                for relative,item in members(archive,entry.get('include_prefixes')):
                    path=(target/relative).resolve()
                    if not path.is_relative_to(target):raise ValueError('Archive path escaped output')
                    if item.is_dir():path.mkdir(parents=True,exist_ok=True)
                    else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(item))
            count=verify_source(archive,target,entry.get('include_prefixes'))
        result[name]={**entry,'source':str(target),'files':count}
    (output/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cafile',type=Path);p.add_argument('--offline',action='store_true');a=p.parse_args()
    print(json.dumps(prepare(a.output,a.cafile,a.offline),indent=2))
