import argparse,hashlib,json,subprocess,shlex,re,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import paths as bridge
ROOT=bridge.ROOT;REPO=bridge.REPO

def arguments(entry):
    if entry.get('arguments'):return entry['arguments']
    return [a[1:-1] if len(a)>1 and a[0]==a[-1] and a[0] in ('"',"'") else a for a in shlex.split(entry['command'],posix=os.name!='nt')]

def platform_options(args):
    def values(option):return [args[i+1] for i,s in enumerate(args[:-1]) if s==option]
    return {'compiler':args[0],'arch':values('-arch'),'sdk':values('-isysroot'),
        'target':values('-target')+values('--target')+[a.split('=',1)[1] for a in args if a.startswith('--target=')]}

def double_precision(args):
    definitions=[a for a in args if a=='-DBT_USE_DOUBLE_PRECISION' or a.startswith('-DBT_USE_DOUBLE_PRECISION=')]
    return bool(definitions) and all(a in ('-DBT_USE_DOUBLE_PRECISION','-DBT_USE_DOUBLE_PRECISION=1') for a in definitions) and '-UBT_USE_DOUBLE_PRECISION' not in args

def bullet_configuration(commands):
    consumers=[x for x in commands if Path(x['file']).resolve()==(ROOT/'src/Physics.cpp').resolve()]
    if len(consumers)!=1:raise ValueError('Missing/duplicate physics consumer')
    reference=arguments(consumers[0]);options=platform_options(reference)
    if not double_precision(reference):raise ValueError('Physics consumer lacks double precision')
    counts={};roots=set()
    anchors={'BulletDynamics':'Dynamics/btDiscreteDynamicsWorld.cpp','BulletCollision':'CollisionDispatch/btCollisionWorld.cpp','LinearMath':'btAlignedAllocator.cpp'}
    for provider,anchor in anchors.items():
        marker='/src/'+provider+'/'
        units=[x for x in commands if marker in Path(x['file']).as_posix()]
        if sum(Path(x['file']).as_posix().endswith(marker+anchor) for x in units)!=1:raise ValueError('Missing/duplicate '+provider+' provider')
        for unit in units:
            args=arguments(unit);roots.add(Path(unit['file']).as_posix().split(marker,1)[0])
            if not double_precision(args):raise ValueError(provider+' lacks double precision: '+unit['file'])
            if platform_options(args)!=options:raise ValueError(provider+' compiler/platform differs from physics consumer: '+unit['file'])
        counts[provider]=len(units)
    if len(roots)!=1:raise ValueError('Multiple Bullet source providers')
    return {'providers':counts,'platform_options':options,'precision':'double'}

def host_configured(build):
    bridge.verify();commands=json.loads((build/'compile_commands.json').read_text())
    report=bullet_configuration(commands);options=report['platform_options']
    if sys.platform=='darwin' and (options['arch']!=['arm64'] or any('iphone' in v.lower() for v in options['sdk']) or any('ios' in v.lower() for v in options['target'])):
        raise ValueError('Host Bullet provider is not native macOS ARM64')
    return report
def sources():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for p in ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts)}
def prepare(output):
    bridge.verify()
    report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'scope':'G3 original exterior and experimental grounded traversal; native and device acceptance UNVERIFIED',
        'source_sha256_lf':sources(),'accepted_g2_commit':json.loads((ROOT/'accepted-source-lock.json').read_text())['accepted_g2_commit'],
        'workflow_sha256_lf':hashlib.sha256((REPO/'.github/workflows/ios-openmw-exterior-device.yml').read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
    output.mkdir(parents=True,exist_ok=True);bridge.verify()
    data=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();(output/'g3-build.json').write_bytes(data)
    (output/'G3Expected.hpp').write_text('#pragma once\nnamespace G3Expected {inline constexpr char SHA[]="'+hashlib.sha256(data).hexdigest()+'";}\n')
    return report
def configured(build,sdk):
    bridge.verify()
    if not sdk.name.lower().startswith('iphoneos'):raise ValueError('Selected SDK is not iPhoneOS')
    commands=json.loads((build/'compile_commands.json').read_text())
    generated=build/'g3-generated'
    include=(generated/'osg-include.txt').read_text().strip()
    expected=[ROOT/'src/Exterior.cpp',ROOT/'src/Terrain.cpp',ROOT/'src/Physics.cpp',generated/'WorldMesh.cpp',ROOT/'device/src/main.mm',REPO/'components/nifbullet/bulletnifloader.cpp',REPO/'components/esm3/loadland.cpp',REPO/'components/terrain/buffercache.cpp']
    for source in expected:
        entries=[x for x in commands if Path(x['file']).resolve()==source.resolve()]
        if len(entries)!=1:raise ValueError('Missing/duplicate G3 compilation: '+str(source))
        args=entries[0].get('arguments') or shlex.split(entries[0]['command'])
        standards=[s for s in args if s.startswith('-std=')]
        if len(standards)!=1 or standards[0] not in ('-std=c++20','-std=c++2a'):raise ValueError('Wrong G3 C++ standard')
        if [args[i+1] for i,s in enumerate(args[:-1]) if s=='-arch']!=['arm64']:raise ValueError('Wrong G3 architecture')
        if [str(Path(args[i+1]).resolve()) for i,s in enumerate(args[:-1]) if s=='-isysroot']!=[str(sdk.resolve())]:raise ValueError('Wrong iPhoneOS SDK')
        if not double_precision(args):raise ValueError('Wrong Bullet precision')
        includes=[]
        for i,s in enumerate(args):
            if s.startswith('-I') and s!='-I':includes.append(s[2:])
            elif s in ('-I','-isystem') and i+1<len(args):includes.append(args[i+1])
        if include not in includes:raise ValueError('Missing actual generated OSG include tree')
        if any(i<includes.index(include) and p.endswith('/osg-math/include') for i,p in enumerate(includes)):raise ValueError('Math-only headers precede actual OSG headers')
    state=[x for x in commands if Path(x['file']).as_posix().endswith('/src/osg/State.cpp')]
    if len(state)!=1:raise ValueError('Multiple/missing OSG providers')
    bullet=bullet_configuration(commands)
    for name in ('OpenThreads/Config','OpenThreads/Version','osg/Config','osg/GL','osg/Version'):
        if not (Path(include)/name).is_file():raise ValueError('Missing generated '+name)
    gl=(Path(include)/'osg/GL').read_text()
    if not re.search(r'^\s*#define\s+OSG_GLES3_AVAILABLE\s*$',gl,re.M):raise ValueError('Provider is not GLES3')
    return {'consumers':len(expected),'osg_providers':len(state),'bullet':bullet,'sdk':str(sdk),'generated_headers':include,'scope':'configured only; native rendering UNVERIFIED'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--configured',type=Path);p.add_argument('--host-configured',type=Path);p.add_argument('--sdk',type=Path);a=p.parse_args()
    if a.host_configured:result=host_configured(a.host_configured.resolve())
    elif a.configured:
        if not a.sdk:raise ValueError('Selected iPhoneOS SDK required')
        result=configured(a.configured.resolve(),a.sdk)
    elif a.output:result=prepare(a.output)
    else:raise ValueError('Select output or configured audit')
    print(json.dumps(result,indent=2))
