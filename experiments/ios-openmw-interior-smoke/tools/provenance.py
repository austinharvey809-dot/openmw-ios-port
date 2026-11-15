import argparse,hashlib,json,subprocess,shlex,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bridge
ROOT=bridge.ROOT;REPO=bridge.REPO
def sources():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for p in ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts)}
def prepare(output):
    report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'scope':'G2 original static interior; native and device acceptance UNVERIFIED',
        'source_sha256_lf':sources(),'accepted_g1d_commit':json.loads((ROOT/'baseline-lock.json').read_text())['accepted_g1d_commit'],
        'workflow_sha256_lf':hashlib.sha256((REPO/'.github/workflows/ios-openmw-interior-device.yml').read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
    output.mkdir(parents=True,exist_ok=True);bridge.generate(output)
    data=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();(output/'g2-build.json').write_bytes(data)
    (output/'G2Expected.hpp').write_text('#pragma once\nnamespace G2Expected {inline constexpr char SHA[]="'+hashlib.sha256(data).hexdigest()+'";}\n')
    return report
def configured(build,sdk):
    if not sdk.name.lower().startswith('iphoneos'):raise ValueError('Selected SDK is not iPhoneOS')
    commands=json.loads((build/'compile_commands.json').read_text())
    generated=build/'g2-generated'
    include=(generated/'osg-include.txt').read_text().strip()
    expected=[ROOT/'src/Interior.cpp',generated/'MeshBridge.cpp',ROOT/'device/src/main.mm']
    for source in expected:
        entries=[x for x in commands if Path(x['file']).resolve()==source.resolve()]
        if len(entries)!=1:raise ValueError('Missing/duplicate G2 compilation: '+str(source))
        args=entries[0].get('arguments') or shlex.split(entries[0]['command'])
        standards=[s for s in args if s.startswith('-std=')]
        if len(standards)!=1 or standards[0] not in ('-std=c++20','-std=c++2a'):raise ValueError('Wrong G2 C++ standard')
        if [args[i+1] for i,s in enumerate(args[:-1]) if s=='-arch']!=['arm64']:raise ValueError('Wrong G2 architecture')
        if [str(Path(args[i+1]).resolve()) for i,s in enumerate(args[:-1]) if s=='-isysroot']!=[str(sdk.resolve())]:raise ValueError('Wrong iPhoneOS SDK')
        if not any(s.startswith('-DBT_USE_DOUBLE_PRECISION') for s in args):raise ValueError('Wrong Bullet precision')
        includes=[]
        for i,s in enumerate(args):
            if s.startswith('-I') and s!='-I':includes.append(s[2:])
            elif s in ('-I','-isystem') and i+1<len(args):includes.append(args[i+1])
        if include not in includes:raise ValueError('Missing actual generated OSG include tree')
        if any(i<includes.index(include) and p.endswith('/osg-math/include') for i,p in enumerate(includes)):raise ValueError('Math-only headers precede actual OSG headers')
    state=[x for x in commands if Path(x['file']).as_posix().endswith('/src/osg/State.cpp')]
    if len(state)!=1:raise ValueError('Multiple/missing OSG providers')
    for name in ('OpenThreads/Config','OpenThreads/Version','osg/Config','osg/GL','osg/Version'):
        if not (Path(include)/name).is_file():raise ValueError('Missing generated '+name)
    gl=(Path(include)/'osg/GL').read_text()
    if not re.search(r'^\s*#define\s+OSG_GLES3_AVAILABLE\s*$',gl,re.M):raise ValueError('Provider is not GLES3')
    return {'consumers':len(expected),'osg_providers':len(state),'sdk':str(sdk),'generated_headers':include,'scope':'configured only; native rendering UNVERIFIED'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--configured',type=Path);p.add_argument('--sdk',type=Path);a=p.parse_args()
    if a.configured:
        if not a.sdk:raise ValueError('Selected iPhoneOS SDK required')
        result=configured(a.configured.resolve(),a.sdk)
    elif a.output:result=prepare(a.output)
    else:raise ValueError('Select output or configured audit')
    print(json.dumps(result,indent=2))
