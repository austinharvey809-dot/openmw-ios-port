"""Local review checks with explicit platforms and durable UTF-8 evidence."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]


def run(build,cmake,bash,snapshot,output):
    output.mkdir(parents=True,exist_ok=True);results={}
    env=dict(os.environ,OPENMW_TEST_CMAKE=str(cmake),PYTHONDONTWRITEBYTECODE='1')
    def check(name,args):
        p=subprocess.run([str(x) for x in args],cwd=REPO,env=env,capture_output=True)
        (output/(name+'.log')).write_bytes(p.stdout+p.stderr)
        results[name]={'status':'PASS' if p.returncode==0 else 'FAIL','exit':p.returncode}
        if p.returncode:raise ValueError(name+' failed; see '+str(output/(name+'.log')))
    py=[sys.executable,'-B']
    check('g5-python',py+['-m','unittest','discover','-s',ROOT/'tools','-p','test_g5.py','-v'])
    check('accepted-g4-python',py+['-m','unittest','discover','-s',ROOT.parent/'ios-openmw-world-smoke/tools','-p','test_g4.py','-v'])
    for name in ('g5-python','accepted-g4-python'):
        if b'skipped=' in (output/(name+'.log')).read_bytes():raise ValueError('Unexpected skipped tests in '+name)
    check('configured-engine-provider',py+[ROOT/'tools/native_preflight.py','--build',build,'--audit'])
    check('g5-engine-native',py+[ROOT/'tools/run_engine_cases.py','--binary',build/'openmw-g5-store-check.exe' if os.name=='nt' else build/'openmw-g5-store-check','--output',output/'store-cases.json'])
    check('g5-world-native',py+[ROOT/'tools/run_engine_cases.py','--world-binary',build/'openmw-engine-check.exe' if os.name=='nt' else build/'openmw-engine-check','--shaders',build/'g4-generated/Shaders','--output',output/'world-cases.json'])
    check('workflow-shell',py+[ROOT.parent/'ios-openmw-nif-render-smoke/textured/tools/check_workflow.py','--workflow',REPO/'.github/workflows/ios-openmw-engine-device.yml','--bash',bash])
    check('accepted-source-provider-preservation',py+[ROOT.parent/'ios-openmw-nif-render-smoke/device/tools/provenance.py','audit','--osg-reference',os.environ['OPENMW_G5_OSG_REFERENCE'],'--local-build15'])
    check('current-tree-preservation',py+[ROOT/'tools/preserve.py','--snapshot',snapshot])
    check('original-tree-preservation',py+[ROOT.parent/'ios-openmw-world-smoke/tools/preserve.py','--verify',ROOT.parent/'ios-openmw-world-smoke/artifacts/preparation-tree.json'])
    check('git-whitespace',['git','diff','--check'])
    source={}
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts):continue
        raw=p.read_bytes().replace(b'\r\n',b'\n');text=raw.decode('utf-8')
        if p.suffix=='.py':ast.parse(text,filename=str(p))
        if any(line.rstrip()!=line for line in text.splitlines()):raise ValueError('Source whitespace: '+str(p))
        source[p.relative_to(REPO).as_posix()]=hashlib.sha256(raw).hexdigest()
    workflow=REPO/'.github/workflows/ios-openmw-engine-device.yml'
    source[workflow.relative_to(REPO).as_posix()]=hashlib.sha256(workflow.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    for name in ('Apple-compile','Apple-link','IPA-package-reopen','physical-G5'):
        results[name]={'status':'UNVERIFIED','reason':'Requires separately authorized native CI / actual iPhone testing'}
    report={'platform':sys.platform,'python':sys.version,'results':results,'source_sha256_lf':source,
            'native_binary_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in build.glob('openmw-*') if p.is_file() and p.name in ('openmw-engine-check.exe','openmw-g5-store-check.exe','openmw-engine-check','openmw-g5-store-check')}}
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('build','cmake','bash','snapshot','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.build.resolve(),a.cmake.resolve(),a.bash.resolve(),a.snapshot.resolve(),a.output.resolve()),indent=2))
