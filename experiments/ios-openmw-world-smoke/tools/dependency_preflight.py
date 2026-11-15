"""Build/inspect genuine G4 dependency archives before the engine/viewer build.

Archive members must be thin arm64 MH_OBJECT with iOS 18 LC_BUILD_VERSION.
This is additional to, and never replaces, final executable/bundle/IPA gates.
"""
import argparse,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import provenance

TARGETS=('g4-jpeg-build','yaml-cpp','zlibstatic','g4-png','g4-boost-options')
LIBRARIES={'jpeg','yaml','zlib','png','boost_program_options'}

def require(condition,message):
    if not condition:raise ValueError(message)

def archive_objects(data):
    require(data.startswith(b'!<arch>\n'),'Expected a regular static ar archive')
    offset=8;objects=[]
    while offset<len(data):
        header=data[offset:offset+60];offset+=60
        require(len(header)==60 and header[58:]==b'`\n','Malformed ar member header')
        try:size=int(header[48:58].strip());name=header[:16].decode('ascii').strip()
        except (ValueError,UnicodeDecodeError):raise ValueError('Invalid ar member size/name') from None
        require(size>=0 and offset+size<=len(data),'Truncated ar member')
        payload=data[offset:offset+size];offset+=size
        if offset%2:
            require(data[offset:offset+1]==b'\n','Missing ar alignment padding');offset+=1
        if name.startswith('#1/'):
            try:length=int(name[3:])
            except ValueError:raise ValueError('Invalid BSD archive name') from None
            require(0<length<=len(payload),'Invalid BSD archive name extent')
            name=payload[:length].rstrip(b'\0').decode('utf-8');payload=payload[length:]
        else:name=name.rstrip('/')
        if name in ('__.SYMDEF','__.SYMDEF SORTED','__.SYMDEF_64','__.SYMDEF_64 SORTED',''):continue # BSD/GNU symbol table
        require(name.endswith(('.o','.obj')),'Unexpected archive member: '+name)
        objects.append((name,payload))
    require(offset==len(data) and objects,'Empty/malformed dependency archive')
    return objects

def device_object(data):
    require(len(data)>=32,'Truncated Mach-O object')
    magic,cpu,subtype,kind,count,extent,flags,reserved=struct.unpack_from('<8I',data)
    require((magic,cpu,subtype,kind)==(0xfeedfacf,0x0100000c,0,1),'Expected thin arm64 MH_OBJECT (no host/simulator/universal/arm64e substitute)')
    require(count<=65536 and 32+extent<=len(data),'Invalid object load-command extent')
    offset=32;platforms=[]
    for _ in range(count):
        require(offset+8<=32+extent,'Truncated object load command')
        command,length=struct.unpack_from('<II',data,offset)
        require(length>=8 and length%8==0 and offset+length<=32+extent,'Malformed object load command')
        require(command not in (0x24,0x25,0x2f,0x30),'Ambiguous legacy object platform')
        if command==0x32:
            require(length>=24,'Truncated LC_BUILD_VERSION')
            platform,minimum,sdk,tools=struct.unpack_from('<4I',data,offset+8)
            require(length==24+8*tools,'Malformed object build version')
            platforms.append((platform,minimum))
        offset+=length
    require(offset==32+extent and platforms==[(2,18<<16)],'Object must target iPhoneOS 18.0; host/simulator/missing/duplicate platform rejected')

def inspect_archive(path):
    require(path.is_file() and not path.is_symlink(),'Missing/nonregular dependency archive')
    data=path.read_bytes();members=archive_objects(data)
    for name,value in members:
        try:device_object(value)
        except ValueError as error:raise ValueError(str(path)+': '+name+': '+str(error)) from error
    return {'sha256':hashlib.sha256(data).hexdigest(),'objects':len(members),'architecture':'arm64',
        'platform':'iPhoneOS','minimum_os':'18.0','scope':'Static object inspection; no GPU/device execution'}

def cache(path):
    result={}
    for line in path.read_text().splitlines():
        found=re.match(r'^([^/#][^:]*):[^=]*=(.*)$',line)
        if found:result[found[1]]=found[2]
    return result

def configured(build,sdk):
    parent=cache(build/'CMakeCache.txt');jpeg=build/'g4-deps/jpeg';child=cache(jpeg/'CMakeCache.txt')
    for name in ('CMAKE_SYSTEM_NAME','CMAKE_SYSTEM_PROCESSOR','CMAKE_OSX_ARCHITECTURES','CMAKE_OSX_DEPLOYMENT_TARGET'):
        require(child.get(name)=={'CMAKE_SYSTEM_NAME':'iOS','CMAKE_SYSTEM_PROCESSOR':'arm64',
            'CMAKE_OSX_ARCHITECTURES':'arm64','CMAKE_OSX_DEPLOYMENT_TARGET':'18.0'}[name],'JPEG target setting mismatch: '+name)
    require(Path(child.get('CMAKE_OSX_SYSROOT','')).resolve()==sdk.resolve(),'JPEG SDK mismatch')
    for name in ('CMAKE_C_COMPILER','CMAKE_AR','CMAKE_RANLIB','CMAKE_MAKE_PROGRAM','CMAKE_BUILD_TYPE'):
        require(child.get(name) and child[name]==parent.get(name),'JPEG did not preserve parent '+name)
    for name,value in {'ENABLE_STATIC':'ON','ENABLE_SHARED':'OFF','WITH_SIMD':'OFF','WITH_TURBOJPEG':'OFF','WITH_TOOLS':'OFF','WITH_TESTS':'OFF'}.items():
        require(child.get(name)==value,'JPEG static/configuration setting mismatch: '+name)
    systems=list((jpeg/'CMakeFiles').glob('*/CMakeSystem.cmake'))
    require(len(systems)==1 and 'set(CMAKE_SYSTEM_PROCESSOR "arm64")' in systems[0].read_text(),'JPEG configured processor differs from explicit cache')
    external=json.loads((jpeg/'compile_commands.json').read_text())
    commands=json.loads((build/'compile_commands.json').read_text())
    new=[e for e in commands if any('/'+name+'.dir/' in e.get('output',e.get('command','')).replace('\\','/') for name in ('yaml-cpp','zlibstatic','g4-png','g4-boost-options'))]
    require(external and len(new)>=30,'Missing dependency compiler commands')
    for entry in external+new:
        args=provenance.arguments(entry);selection=provenance.platform(args)
        require(selection['-arch']==['arm64'],'Dependency compile architecture mismatch')
        require([str(Path(p).resolve()) for p in selection['-isysroot']]==[str(sdk.resolve())],'Dependency compile SDK mismatch')
        require([a for a in args if a.startswith('-miphoneos-version-min=')]==['-miphoneos-version-min=18.0'],'Dependency deployment flag missing/conflicting')
        require(not any('mmacosx-version-min' in a or 'mios-simulator-version-min' in a for a in args),'Host/simulator dependency option')
    return {'jpeg_compile_units':len(external),'in_tree_dependency_units':len(new),'processor':'arm64'}

def run(build,sdk,output,cmake='cmake'):
    require(sys.platform=='darwin','Dependency preflight requires the genuine Apple SDK/toolchain')
    require(sdk.resolve().name.lower().startswith('iphoneos'),'Dependency preflight requires iPhoneOS SDK')
    output.mkdir(parents=True,exist_ok=True)
    def execute(label,command):
        result=subprocess.run(command,capture_output=True,text=True)
        (output/(label+'.log')).write_text(result.stdout+result.stderr)
        require(result.returncode==0,'Early dependency '+label+' failed; see retained log')
    # Exposes the exact ExternalProject configuration error without OSG work.
    execute('jpeg-configure',[cmake,'--build',str(build),'--target','g4-jpeg-build-configure','--parallel','3'])
    report={'configured':configured(build,sdk)}
    execute('dependency-build',[cmake,'--build',str(build),'--target',*TARGETS,'--parallel','3'])
    archives=json.loads((build/'g4-dependencies-Release.json').read_text())
    require(set(archives)==LIBRARIES,'Unexpected dependency archive inventory')
    report['archives']={name:inspect_archive(Path(path)) for name,path in archives.items()}
    report['status']='PASS';report['scope']='Real iPhoneOS dependency compilation and per-object inspection; app/GPU/device gates remain separate'
    (output/'dependencies.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('build','sdk','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cmake',default='cmake');a=p.parse_args()
    print(json.dumps(run(a.build.resolve(),a.sdk.resolve(),a.output.resolve(),a.cmake),indent=2))
