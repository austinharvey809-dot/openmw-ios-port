"""Optional supplemental Windows CPU validation; never changes macOS/iOS providers.

Supply independently verified portable development tools and the existing pinned
Bullet acquisition output. No tools/dependencies are downloaded or installed.
The one platform substitution is unchanged upstream filewin32.cpp for fileposix.cpp.
"""
import argparse,hashlib,json,os,subprocess,sys,tarfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paths import ROOT,REPO,verify
import mesh_bridge

def run(zig,ninja,cmake,osg,bullet,output):
    if sys.platform!='win32':raise ValueError('Supplemental recipe requires Windows; use normal CMake on macOS')
    verify()
    git=['git','-c','safe.directory='+osg.as_posix(),'-C',str(osg)]
    revision=subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()
    if revision!='9b384d5439977784e5cd250ff8ff7966928ddd27' or subprocess.check_output(git+['status','--porcelain']):raise ValueError('Pinned OSG must be unchanged')
    provenance=json.loads((bullet/'bullet-provenance.json').read_text())
    if provenance['source_url']!='https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz' or provenance['archive_sha512']!='7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4' or Path(provenance['source_directory']).resolve()!=bullet/'source':raise ValueError('Bullet source provenance mismatch')
    with (bullet/'bullet-3.25.tar.gz').open('rb') as stream:
        if hashlib.file_digest(stream,'sha512').hexdigest()!=provenance['archive_sha512']:raise ValueError('Bullet archive differs')
    with tarfile.open(bullet/'bullet-3.25.tar.gz','r:gz') as archive:
        for member in archive:
            if member.isfile() and (member.name.startswith('bullet3-3.25/src/') or member.name=='bullet3-3.25/CMakeLists.txt'):
                relative=member.name.removeprefix('bullet3-3.25/');source=(bullet/'source'/relative).resolve()
                if not source.is_relative_to(bullet/'source') or source.read_bytes()!=archive.extractfile(member).read():raise ValueError('Extracted Bullet source changed: '+relative)
    if output.is_relative_to(REPO) and not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Build output must be outside source or under G3 artifacts')
    output.mkdir(parents=True,exist_ok=True);project=output/'project';project.mkdir(exist_ok=True)
    generated=output/'generated';mesh_bridge.generate(generated)
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(output/'zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(output/'zig-local-cache'))
    for kind,command in (('cc','cc'),('cxx','c++'),('ar','ar'),('ranlib','ranlib')):
        (output/('zig-'+kind+'.cmd')).write_text('@"'+str(zig)+'" '+command+' %*\n')
    sources=set(json.loads((REPO/'experiments/ios-openmw-esm/data/source-audit.json').read_text())['sources'])
    sources.update(json.loads((REPO/'experiments/ios-openmw-esm-vfs/data/source-audit.json').read_text())['additional_sources'])
    sources.remove('components/platform/fileposix.cpp');sources.add('components/platform/filewin32.cpp')
    sources.update(json.loads((REPO/'experiments/ios-openmw-nif-smoke/data/nif-source-sha256.json').read_text())['sources'])
    sources.update('components/esm3/'+n+'.cpp' for n in ('loadcell','cellref','loadacti','loadcont','loaddoor','loadmisc','loadligh','loadland','loadltex'))
    sources.update(('components/nifbullet/bulletnifloader.cpp','components/resource/bulletshape.cpp','components/sceneutil/material.cpp','components/terrain/buffercache.cpp','components/misc/resourcehelpers.cpp','experiments/ios-openmw-interior-smoke/src/Interior.cpp'))
    source_paths=[REPO/n for n in sorted(sources)]+[ROOT/'src'/n for n in ('Exterior.cpp','Terrain.cpp','Physics.cpp')]
    source_paths+=[generated/'WorldMesh.cpp',generated/'MeshBridge.cpp',osg/'src/osgPlugins/dds/ReaderWriterDDS.cpp',osg/'src/osgPlugins/tga/ReaderWriterTGA.cpp']
    lines=['cmake_minimum_required(VERSION 3.24)','project(G3WindowsCPU LANGUAGES C CXX)',
        'set(CMAKE_AR "'+(output/'zig-ar.cmd').as_posix()+'")','set(CMAKE_RANLIB "'+(output/'zig-ranlib.cmd').as_posix()+'")']
    for name in ('BUILD_SHARED_LIBS','BUILD_OSG_APPLICATIONS','BUILD_OSG_EXAMPLES','BUILD_OSG_PLUGINS','BUILD_BULLET2_DEMOS','BUILD_CPU_DEMOS','BUILD_OPENGL3_DEMOS','BUILD_EXTRAS','BUILD_UNIT_TESTS'):
        lines.append('set('+name+' OFF CACHE BOOL "" FORCE)')
    lines+=['set(OSG_WINDOWING_SYSTEM None CACHE STRING "" FORCE)','set(OPENGL_PROFILE GL2 CACHE STRING "" FORCE)',
        'add_subdirectory("'+osg.as_posix()+'" osg EXCLUDE_FROM_ALL)','set(USE_DOUBLE_PRECISION ON CACHE BOOL "" FORCE)',
        'add_subdirectory("'+(bullet/'source').as_posix()+'" bullet EXCLUDE_FROM_ALL)',
        'add_library(world STATIC','\n'.join('"'+p.as_posix()+'"' for p in source_paths),')']
    includes=[REPO,ROOT/'src',ROOT.parent/'ios-openmw-interior-smoke/src',ROOT.parent/'ios-openmw-nif-render-smoke/real-model/src',ROOT.parent/'ios-openmw-nif-render-smoke/textured/src',ROOT.parent/'ios-openmw-nif-render-smoke/src',ROOT.parent/'ios-openmw-bsa-vfs/src',REPO/'extern/smhasher/include',REPO/'extern/smhasher/include/smhasher',bullet/'source/src',osg/'include']
    lines+=['target_include_directories(world BEFORE PUBLIC "${CMAKE_CURRENT_BINARY_DIR}/osg/include"',
        '\n'.join('"'+p.as_posix()+'"' for p in includes),')',
        'target_compile_definitions(world PUBLIC OSG_LIBRARY_STATIC OPENTHREADS_STATIC BT_USE_DOUBLE_PRECISION)',
        'target_compile_features(world PUBLIC cxx_std_20)',
        'target_link_libraries(world PUBLIC osgDB osgUtil osg OpenThreads BulletDynamics BulletCollision LinearMath)',
        'add_executable(g3-windows "'+(ROOT/'tests/exterior_check.cpp').as_posix()+'")','target_link_libraries(g3-windows PRIVATE world)']
    (project/'CMakeLists.txt').write_text('\n'.join(lines)+'\n',newline='\n')
    build=output/'build'
    commands=[('configure',[str(cmake),'-S',str(project),'-B',str(build),'-G','Ninja','-DCMAKE_POLICY_VERSION_MINIMUM=3.5','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DCMAKE_MAKE_PROGRAM='+str(ninja),'-DCMAKE_C_COMPILER='+str(output/'zig-cc.cmd'),'-DCMAKE_CXX_COMPILER='+str(output/'zig-cxx.cmd'),'-DCMAKE_AR='+str(output/'zig-ar.cmd'),'-DCMAKE_RANLIB='+str(output/'zig-ranlib.cmd')]),
        ('bullet-configured',[sys.executable,'-B',str(ROOT/'tools/provenance.py'),'--host-configured',str(build)]),
        ('build',[str(cmake),'--build',str(build),'--target','g3-windows','--parallel','6'])]
    for name,command in commands:
        with (output/(name+'.log')).open('w') as log:
            result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise ValueError('Windows CPU '+name+' failed; see '+str(output/(name+'.log')))
    # This supplemental desktop provider may use local OSG DLLs; never package them for iOS.
    env['PATH']=str(build/'osg/bin')+os.pathsep+env['PATH']
    result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/run_cases.py'),'--binary',str(build/'g3-windows.exe')],env=env,capture_output=True,text=True)
    (output/'native-cases.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise ValueError('Windows CPU cases failed; see retained log')
    return {'scope':'supplemental Windows CPU only; Apple/GPU/physical acceptance UNVERIFIED','cases':len(json.loads(result.stdout)),
        'binary':str(build/'g3-windows.exe'),'binary_sha256':hashlib.sha256((build/'g3-windows.exe').read_bytes()).hexdigest()}
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for arg in ('zig','ninja','cmake','osg','bullet','output'):parser.add_argument('--'+arg,type=Path,required=True)
    a=parser.parse_args();print(json.dumps(run(*(getattr(a,n).resolve() for n in ('zig','ninja','cmake','osg','bullet','output'))),indent=2))
