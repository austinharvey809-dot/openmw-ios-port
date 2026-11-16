"""Audit actual G5 compile commands and compile new Apple consumers early."""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'ios-openmw-world-smoke/tools'))
import provenance as accepted
import dependency_preflight
spec=importlib.util.spec_from_file_location('g4_native_preflight',ROOT.parent/'ios-openmw-world-smoke/tools/native_preflight.py')
old_preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_preflight)


def consumer_contract(entry,sdk=None):
    args=accepted.arguments(entry)
    if not entry['file'].endswith('.c'):
        accepted.standard(args)
        if not accepted.double(args):raise ValueError('G5 Bullet precision mismatch')
    else:
        if [arg for arg in args if arg.startswith('-std=')]!=['-std=c99']:
            raise ValueError('G5 Lua consumer lacks strict C99')
        if sdk and ('-DLUA_USE_IOS' not in args or any(a.startswith(('-ULUA_USE_IOS','-DLUA_USE_IOS=')) for a in args)):
            raise ValueError('G5 Lua lacks the genuine iOS platform configuration')
    platform=accepted.platform(args)
    if sdk and (platform['-arch']!=['arm64'] or [str(Path(p).resolve()) for p in platform['-isysroot']]!=[str(sdk.resolve())]):
        raise ValueError('G5 native architecture/SDK mismatch')
    return platform


def audit(build,sdk=None):
    commands=json.loads((build/'compile_commands.json').read_text())
    selected=[e for e in commands if any('/'+n+'.dir/' in e.get('output',e.get('command','')).replace('\\','/') for n in ('g5-engine-store','g5-world','g5-lua','IOSOpenMWEngine'))]
    if len(selected)!=45+(1 if sdk else 0):raise ValueError('G5 source closure incomplete: '+str(len(selected)))
    cache=dict(line.split('=',1) for line in (build/'CMakeCache.txt').read_text().splitlines()
               if '=' in line and not line.startswith(('#','//')))
    lua=Path(next(value for key,value in cache.items() if key.split(':')[0]=='G5_LUA_SOURCE'))
    generated=build/'g5-generated';repo=ROOT.parents[1]
    lua_units='lapi lauxlib lbaselib lcode lcorolib lctype ldblib ldebug ldo ldump lfunc lgc linit liolib llex lmathlib lmem loadlib lobject lopcodes loslib lparser lstate lstring lstrlib ltable ltablib ltm lundump lutf8lib lvm lzio'.split()
    expected={'g5-lua':{(lua/'src'/(n+'.c')).resolve() for n in lua_units},
              'g5-world':{(generated/(n+'.cpp')).resolve() for n in ('Resources','TerrainStorage','World','Environment','Session')},
              'g5-engine-store':{(generated/n).resolve() for n in ('esmstore.cpp','readonly.cpp','References.cpp')}|
                  {(ROOT/'src/EngineIndex.cpp').resolve()}|
                  {(repo/n).resolve() for n in ('components/esm/luascripts.cpp','components/lua/serialization.cpp','components/lua/configuration.cpp','components/misc/color.cpp')}}
    if sdk:expected['IOSOpenMWEngine']={(generated/'main.mm').resolve()}
    for target,wanted in expected.items():
        units=[e for e in selected if '/'+target+'.dir/' in e.get('output',e.get('command','')).replace('\\','/')]
        if len(units)!=len(wanted) or {Path(e['file']).resolve() for e in units}!=wanted:
            raise ValueError('G5 exact source inventory mismatch: '+target)
    reference=None
    for e in selected:
        platform=consumer_contract(e,sdk)
        if reference is None:reference=platform
        if platform!=reference:raise ValueError('G5 dependency/consumer platform mismatch')
    return selected


def run(build,sdk,output):
    if sys.platform!='darwin':raise ValueError('Real Apple preflight requires macOS and iPhoneOS SDK')
    accepted.configured(build,sdk);selected=audit(build,sdk);output.mkdir(parents=True,exist_ok=True)
    results=[]
    for i,entry in enumerate(selected):
        args=old_preflight.syntax_arguments(accepted.arguments(entry))
        result=subprocess.run(args,cwd=entry['directory'],capture_output=True,text=True)
        (output/(str(i)+'-'+Path(entry['file']).name+'.log')).write_text(result.stdout+result.stderr)
        results.append({'file':entry['file'],'command':args,'exit':result.returncode})
        (output/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
        if result.returncode:raise ValueError('G5 early Apple compilation failed: '+entry['file'])
    with (output/'lua-build.log').open('w') as log:
        built=subprocess.run(['cmake','--build',str(build),'--target','g5-lua','--parallel','3'],stdout=log,stderr=subprocess.STDOUT)
    if built.returncode:raise ValueError('Genuine Lua archive build failed')
    archive=Path((build/'g5-lua-Release.txt').read_text().strip())
    evidence=dependency_preflight.inspect_archive(archive)
    return {'status':'PASS','consumers':len(results),'lua_archive':evidence,
            'scope':'Apple consumer syntax and genuine Lua ARM64/iOS archive; final link and package remain mandatory'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--build',type=Path,required=True);p.add_argument('--sdk',type=Path);p.add_argument('--output',type=Path);p.add_argument('--audit',action='store_true')
    a=p.parse_args()
    if a.audit:result={'status':'PASS','configured_consumers':len(audit(a.build.resolve(),a.sdk)),'scope':'Configured commands only, no Apple execution'}
    else:
        if not a.sdk or not a.output:p.error('Apple preflight requires --sdk and --output')
        result=run(a.build.resolve(),a.sdk.resolve(),a.output.resolve())
    print(json.dumps(result,indent=2))
