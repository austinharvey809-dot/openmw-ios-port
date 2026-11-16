"""Bind the isolated genuine engine component and reused platform source view."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_engine import ROOT,REPO
from verify_lua import verify as verify_lua

WORKFLOW=REPO/'.github/workflows/ios-openmw-engine-device.yml'
G4=ROOT.parent/'ios-openmw-world-smoke'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sources():
    return {p.relative_to(ROOT).as_posix():digest(p.read_bytes().replace(b'\r\n',b'\n'))
            for p in ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts)}


def accepted_contract(base):
    actual={p.relative_to(G4).as_posix():digest(p.read_bytes().replace(b'\r\n',b'\n'))
            for p in G4.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(G4).parts)}
    if base['source_sha256_lf']!=actual:raise ValueError('Accepted G4 exact source provenance differs')
    workflow=REPO/'.github/workflows/ios-openmw-world-device.yml'
    if base['workflow_sha256_lf']!=digest(workflow.read_bytes().replace(b'\r\n',b'\n')):
        raise ValueError('Accepted G4 workflow provenance differs')
    if base['dependencies']!=json.loads((G4/'dependencies.json').read_text()):raise ValueError('Accepted G4 dependency pins differ')
    if base['accepted_g3_commit']!='d60ca603e82935a9ccce9ae5ec8dc9ec22013580':raise ValueError('Accepted G3 identity differs')
    expected={'Shaders/shader-provenance.json','g4-environment.json','g4-dependencies.json','Licenses/G4-jpeg-ijg.txt'}
    expected.update('Shaders/compatibility/'+n for n in ('objects.vert','objects.frag','terrain.vert','terrain.frag','terrain_composite.vert','terrain_composite.frag'))
    expected.update('Licenses/G4-'+n+'.txt' for n in ('yaml','mygui','zlib','png','jpeg','boost'))
    if set(base['public_resources_sha256'])!=expected:raise ValueError('Accepted G4 public resource categories differ')


def prepare(output,g4_public,lua):
    verify_lua(lua)
    base=json.loads((g4_public/'g4-build.json').read_text())
    accepted_contract(base)
    expected=base['public_resources_sha256']
    actual={p.relative_to(g4_public).as_posix() for p in g4_public.rglob('*') if p.is_file()}
    if actual!=set(expected)|{'g4-build.json'}:raise ValueError('Accepted public inventory differs')
    public=output/'public';public.mkdir(parents=True,exist_ok=True)
    for name,want in expected.items():
        raw=(g4_public/name).read_bytes()
        if digest(raw)!=want:raise ValueError('Accepted public bytes changed: '+name)
        target=public/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    (public/'Licenses/G5-Lua-readme.html').write_bytes((lua/'doc/readme.html').read_bytes())
    (public/'g5-engine.json').write_bytes((output/'engine-projection.json').read_bytes())
    resources={p.relative_to(public).as_posix():digest(p.read_bytes()) for p in public.rglob('*') if p.is_file() and p.name!='g5-build.json'}
    if set(resources)!=set(expected)|{'Licenses/G5-Lua-readme.html','g5-engine.json'}:
        raise ValueError('Unexpected G5 public resource inventory')
    report={'schema':1,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'accepted_g4_commit':'cd5e74396fc75a502d441925adc77efcac4af1ec','source_sha256_lf':sources(),
            'workflow_sha256_lf':digest(WORKFLOW.read_bytes().replace(b'\r\n',b'\n')),
            'engine_lock':json.loads((ROOT/'engine-lock.json').read_text()),
            'new_dependencies':json.loads((ROOT/'dependencies.json').read_text()),'accepted_g4_build':base,
            'public_resources_sha256':resources,'scope':'Genuine ESM3 engine content store; static-world renderer; device acceptance UNVERIFIED'}
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();(public/'g5-build.json').write_bytes(raw)
    (output/'G5Expected.hpp').write_text('#pragma once\nnamespace G5Expected {inline constexpr char SHA[]="'+digest(raw)+'";inline constexpr char Commit[]="'+report['commit']+'";}\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('output','g4-public','lua'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.output,a.g4_public,a.lua),indent=2))
