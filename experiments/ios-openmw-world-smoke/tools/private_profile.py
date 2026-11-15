"""Create a private ordered import manifest; never copy or publish game data."""
import argparse,hashlib,json
from pathlib import Path

def relative(root,name,directory=False):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or any(p in ('','.','..') for p in name.split('/')):
        raise ValueError('Unsafe private profile path')
    path=root/name
    for part in (path,*path.parents):
        if part==root.parent:break
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):raise ValueError('Linked private input')
    resolved=path.resolve(strict=True)
    if not resolved.is_relative_to(root):raise ValueError('Private input escapes import root')
    if directory and not path.is_dir():raise ValueError('Loose input must be a directory')
    if not directory and not path.is_file():raise ValueError('Input must be an existing regular file')
    return path

def create(root,content,archives,loose):
    root=root.resolve(strict=True)
    if not 1<=len(content)<=254 or not 1<=len(archives)<=32 or len(loose)>8:raise ValueError('Private input budget exceeded')
    files={}
    def add(name):
        if name in files:raise ValueError('Duplicate selected input')
        path=relative(root,name)
        with path.open('rb') as stream:files[name]=hashlib.file_digest(stream,'sha256').hexdigest()
    if len({Path(n).name.casefold() for n in content})!=len(content):raise ValueError('Duplicate content basename')
    for name in (*content,*archives):add(name)
    for name in loose:
        directory=relative(root,name,True)
        for path in sorted(directory.rglob('*')):
            child=path.relative_to(root).as_posix()
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Linked loose input')
            if path.is_file():add(child)
            elif not path.is_dir():raise ValueError('Unsupported loose input type')
    return {'schema_version':1,'content':content,'archives':archives,'loose_directories':loose,'files':dict(sorted(files.items()))}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--content',action='append');p.add_argument('--archive',action='append');p.add_argument('--loose',action='append',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=create(a.data_dir,a.content or ['Morrowind.esm'],a.archive or ['Morrowind.bsa'],a.loose)
    # The CLI writes metadata only, to an explicit private filename. No data copy.
    if a.output.name!='world-profile.json':p.error('Use the private world-profile.json filename')
    if a.output.resolve().is_relative_to(a.data_dir.resolve()):p.error('Keep generated metadata outside the original game installation')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Private profile written; keep it and every selected game file outside Git/public artifacts.')
