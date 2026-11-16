"""Create an exact source-review archive without private data or Git mutation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
WORKFLOW=REPO/'.github/workflows/ios-openmw-engine-device.yml'
BASE='cd5e74396fc75a502d441925adc77efcac4af1ec'


def sources():
    result=[]
    for directory,children,names in os.walk(ROOT):
        children[:]=[n for n in children if n not in ('artifacts','build','private','__pycache__')]
        for name in names:
            path=Path(directory)/name
            if path.is_symlink() or (path.suffix not in ('.md','.json','.py','.cpp','.hpp','.cmake') and name!='.gitignore'):
                raise ValueError('Unexpected source member: '+str(path))
            result.append(path)
    result.append(WORKFLOW)
    return sorted(result)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def package(output):
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()!=BASE:
        raise ValueError('Review archive must be prepared against the documented base')
    files={p.relative_to(REPO).as_posix():p.read_bytes() for p in sources()}
    validation=json.loads((ROOT/'artifacts/validation/validation.json').read_text())
    if validation['source_sha256_lf']!={n:digest(raw.replace(b'\r\n',b'\n')) for n,raw in files.items()}:
        raise ValueError('Validation source inventory/hashes differ from current review')
    if any(r['status'] not in ('PASS','UNVERIFIED') for r in validation['results'].values()):
        raise ValueError('Failed validation cannot enter review package')
    source_names=set(files)
    selected={
        'g4-closure/artifact-verification.json':'g4/artifact-verification.json',
        'g4-closure/verification.json':'g4/portable-ci-review.json',
        'g4-closure/closure-summary.json':'g4/closure-summary.json',
        'private-content-summary.json':'private-content-summary.json',
        'metadata-smoke/result.json':'metadata-smoke.json',
        'workflow-yaml.json':'workflow-yaml.json',
        'upstream/dispatch-review.json':'dispatch-review.json',
        'build-final.log':'windows-build.log',
    }
    for source,name in selected.items():files['evidence/'+name]=(ROOT/'artifacts'/source).read_bytes()
    for path in sorted((ROOT/'artifacts/validation').iterdir()):
        if path.is_file() and path.suffix in ('.json','.log'):
            files['evidence/validation/'+path.name]=path.read_bytes()
    inventory={'schema':1,'base_commit':BASE,'source_additions':sorted(source_names),
               'source_count':len(source_names),'evidence_files':sorted(set(files)-source_names),
               'source_sha256_raw':{n:digest(files[n]) for n in sorted(source_names)},
               'source_sha256_lf':{n:digest(files[n].replace(b'\r\n',b'\n')) for n in sorted(source_names)},
               'publication':'UNPUBLISHED; no staging, commit, push or workflow dispatch',
               'excluded':'Original game assets, private profiles/exports/recordings, dependency archives, libraries and executables'}
    files['REVIEW-INVENTORY.json']=(json.dumps(inventory,indent=2)+'\n').encode()
    checksums=''.join(digest(raw)+'  '+name+'\n' for name,raw in sorted(files.items()))
    files['SHA256SUMS']=checksums.encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,11,16,0,0,0));info.create_system=3
            info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,raw)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist())!=len(set(archive.namelist())):
            raise ValueError('Review ZIP integrity/inventory failure')
        if set(archive.namelist())!=set(files):raise ValueError('Review ZIP inventory differs')
        for name,raw in files.items():
            if archive.read(name)!=raw:raise ValueError('Review ZIP payload changed: '+name)
    result={'path':str(output.resolve()),'sha256':digest(output.read_bytes()),'bytes':output.stat().st_size,
            'source_files':len(source_names),'evidence_files':len(inventory['evidence_files']),
            'manifested_payload_files':len(files)-1,'zip_entries':len(files),'status':'PASS'}
    output.with_suffix('.zip.sha256').write_text(result['sha256']+'  '+output.name+'\n',encoding='utf-8')
    output.with_suffix('.review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(json.dumps(package(p.parse_args().output.resolve()),indent=2))
