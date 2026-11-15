"""Source, provider and generated-resource provenance for the isolated G4 app."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import paths
ROOT=paths.ROOT;REPO=paths.REPO
WORKFLOW=REPO/'.github/workflows/ios-openmw-world-device.yml'
def sha(data):return hashlib.sha256(data).hexdigest()
def sources():
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n'))
        for p in ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts)}
def public_files(output,dependencies):
    public=output/'public';public.mkdir(parents=True,exist_ok=True)
    shader_expected={'shader-provenance.json'}|{'compatibility/'+n for n in ('objects.vert','objects.frag','terrain.vert','terrain.frag','terrain_composite.vert','terrain_composite.frag')}
    shader_actual={p.relative_to(output/'Shaders').as_posix() for p in (output/'Shaders').rglob('*') if p.is_file()}
    if shader_actual!=shader_expected:raise ValueError('Unexpected generated shader inventory')
    shutil.copytree(output/'Shaders',public/'Shaders',dirs_exist_ok=True)
    shutil.copyfile(output/'g4-environment.json',public/'g4-environment.json')
    lock=json.loads((ROOT/'dependencies.json').read_text())
    (public/'g4-dependencies.json').write_text(json.dumps(lock,sort_keys=True,indent=2)+'\n')
    licenses={'yaml':'LICENSE','mygui':'COPYING.MIT','zlib':'LICENSE','png':'LICENSE','jpeg':'LICENSE.md','boost':'LICENSE_1_0.txt'}
    for name,source in licenses.items():
        target=public/'Licenses'/('G4-'+name+'.txt');target.parent.mkdir(exist_ok=True)
        target.write_bytes((dependencies/name/source).read_bytes())
    (public/'Licenses/G4-jpeg-ijg.txt').write_bytes((dependencies/'jpeg/README.ijg').read_bytes())
    expected={'Shaders/'+name for name in shader_expected}|{'g4-environment.json','g4-dependencies.json'}|{'Licenses/G4-'+name+'.txt' for name in licenses}|{'Licenses/G4-jpeg-ijg.txt'}
    actual={p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file() and p.name!='g4-build.json'}
    if actual!=expected:raise ValueError('Unexpected public resource inventory; private assets must never be bundled')
    return {name:sha((public/name).read_bytes()) for name in sorted(expected)}
def prepare(output,dependencies):
    paths.verify();resources=public_files(output,dependencies)
    report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'scope':'G4 genuine resource/terrain integration and bounded static world streaming; native/device acceptance UNVERIFIED',
        'source_sha256_lf':sources(),'workflow_sha256_lf':sha(WORKFLOW.read_bytes().replace(b'\r\n',b'\n')),
        'accepted_g3_commit':paths.verify()['accepted_g3_commit'],'public_resources_sha256':resources,
        'dependencies':json.loads((ROOT/'dependencies.json').read_text()),
        'shader_translation':json.loads((output/'Shaders/shader-provenance.json').read_text())}
    data=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();(output/'public/g4-build.json').write_bytes(data)
    (output/'G4Expected.hpp').write_text('#pragma once\nnamespace G4Expected {inline constexpr char SHA[]="'+sha(data)+'";inline constexpr char Commit[]="'+report['commit']+'";}\n')
    return report
def arguments(entry):
    if entry.get('arguments'):return entry['arguments']
    return [p[1:-1] if len(p)>1 and p[0]==p[-1] and p[0] in ('"',"\'") else p for p in shlex.split(entry['command'],posix=os.name!='nt')]
def platform(args):
    return {key:[args[i+1] for i,value in enumerate(args[:-1]) if value==key] for key in ('-arch','-isysroot','-target')}
def double(args):return any(x in ('-DBT_USE_DOUBLE_PRECISION','-DBT_USE_DOUBLE_PRECISION=1') for x in args) and not any(x.startswith('-UBT_USE_DOUBLE_PRECISION') or (x.startswith('-DBT_USE_DOUBLE_PRECISION=') and x!='-DBT_USE_DOUBLE_PRECISION=1') for x in args)

def standard(args):
    standards=[a for a in args if a.startswith('-std=')]
    if len(standards)!=1 or standards[0] not in ('-std=c++20','-std=c++2a'):
        raise ValueError('Unsupported/conflicting G4 C++ standard')
def configured(build,sdk=None):
    paths.verify();commands=json.loads((build/'compile_commands.json').read_text())
    consumers=[e for e in commands if 'g4-upstream.dir' in e.get('output',e.get('command','')) or 'IOSOpenMWWorld.dir' in e.get('output',e.get('command',''))]
    if not consumers:raise ValueError('Missing configured G4 consumers')
    expected=set(json.loads((ROOT/'engine-sources.json').read_text())['sources'])
    expected.update(p.relative_to(REPO).as_posix() for p in (ROOT/'src').glob('*.cpp'))
    actual={Path(e['file']).resolve() for e in consumers}
    if not {REPO/p for p in expected}.issubset(actual):raise ValueError('Genuine source closure missing configured compilation')
    include=(build/'g4-generated/osg-include.txt').read_text().strip()
    for entry in consumers:
        args=arguments(entry)
        standard(args)
        if not double(args):raise ValueError('G4 consumer lacks double-precision Bullet ABI')
        if sdk:
            selected=platform(args)
            if selected['-arch']!=['arm64'] or [str(Path(p).resolve()) for p in selected['-isysroot']]!=[str(sdk.resolve())]:
                raise ValueError('G4 consumer architecture/SDK mismatch')
        includes=[]
        for i,arg in enumerate(args):
            if arg.startswith('-I') and arg!='-I':includes.append(arg[2:])
            elif arg in ('-I','-isystem') and i+1<len(args):includes.append(args[i+1])
        if Path(include).resolve() not in [Path(p).resolve() for p in includes]:raise ValueError('G4 lacks actual generated OSG headers')
        if any('osg-math' in p for p in includes[:next(i for i,p in enumerate(includes) if Path(p).resolve()==Path(include).resolve())]):
            raise ValueError('Math-only OSG headers precede actual provider')
    states=[e for e in commands if Path(e['file']).as_posix().endswith('/src/osg/State.cpp')]
    # Supplemental imported desktop providers were audited in their original build.
    if (sdk or states) and len(states)!=1:raise ValueError('G4 requires exactly one OSG provider')
    for name in ('osg/Config','osg/GL','osg/Version','OpenThreads/Config','OpenThreads/Version'):
        if not (Path(include)/name).is_file():raise ValueError('Missing generated '+name)
    bullet_present=any('/src/BulletDynamics/' in Path(e['file']).as_posix() for e in commands)
    if sdk or bullet_present:
        reference=platform(arguments(consumers[0]))
        for library,anchor in {'BulletDynamics':'Dynamics/btDiscreteDynamicsWorld.cpp','BulletCollision':'CollisionDispatch/btCollisionWorld.cpp','LinearMath':'btAlignedAllocator.cpp'}.items():
            units=[e for e in commands if '/src/'+library+'/' in Path(e['file']).as_posix()]
            if sum(Path(e['file']).as_posix().endswith('/src/'+library+'/'+anchor) for e in units)!=1:raise ValueError('Missing/duplicate Bullet provider '+library)
            if any(not double(arguments(e)) or platform(arguments(e))!=reference for e in units):raise ValueError('Bullet precision/platform mismatch '+library)
    if sdk:
        if not sdk.name.lower().startswith('iphoneos'):raise ValueError('SDK must be iPhoneOS')
        gl=(Path(include)/'osg/GL').read_text()
        if '#define OSG_GLES3_AVAILABLE' not in gl:raise ValueError('G4 provider is not GLES3')
        link=build/'CMakeFiles/IOSOpenMWWorld.dir/link.txt'
        if link.exists() and any(name in link.read_text() for name in ('libg3-world','libg2-cell','libg1b-geometry','libg1c-texture')):
            raise ValueError('G4 executable links a legacy mesh bridge')
    return {'status':'PASS','scope':'configured source/provider only; compilation and device rendering not established',
        'g4_consumers':len(consumers),'osg_providers':len(states),'generated_headers':include}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--dependencies',type=Path);p.add_argument('--configured',type=Path);p.add_argument('--sdk',type=Path);a=p.parse_args()
    if a.configured:result=configured(a.configured.resolve(),a.sdk)
    elif a.output and a.dependencies:result=prepare(a.output.resolve(),a.dependencies.resolve())
    else:p.error('Choose configured or output/dependencies')
    print(json.dumps(result,indent=2))
