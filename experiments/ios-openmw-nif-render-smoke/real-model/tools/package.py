"""Public app packaging only: private game files are never app resources."""
import argparse,hashlib,importlib.util,json,plistlib,stat,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'textured/tools'))
import support
p=support.package
p.core.APP_NAME='IOSOpenMWRealModel.app';p.core.PREFIX='Payload/IOSOpenMWRealModel.app/'
def validate(entries,prepared,sdk):
    original,base_metadata=p.prepared_resources(prepared)
    allowed={n:b for n,b in original.items() if n.startswith(('Frameworks/','Licenses/','Provenance/'))}
    if set(entries)!=set(allowed)|{'Info.plist','IOSOpenMWRealModel','g1d-build.json'}:raise ValueError('Exact public inventory mismatch')
    if any(entries[n].data!=b for n,b in allowed.items()):raise ValueError('Public dependency/provenance bytes changed')
    metadata=json.loads(original['g1b-build.json']);manifest=json.loads(entries['g1d-build.json'].data)
    if manifest['commit']!=support.host.git('rev-parse','HEAD').decode().strip():raise ValueError('Source commit mismatch')
    for n,d in manifest['source_sha256_lf'].items():
        q=(ROOT/n).resolve()
        if not q.is_relative_to(ROOT) or hashlib.sha256(q.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=d:raise ValueError('G1D source changed')
    digest=hashlib.sha256(entries['g1d-build.json'].data).hexdigest()
    if digest.encode() not in entries['IOSOpenMWRealModel'].data:raise ValueError('Binary lacks provenance binding')
    info=plistlib.loads(entries['Info.plist'].data)
    if info.get('CFBundleIdentifier')!='org.openmw.experiments.real-model' or info.get('CFBundleExecutable')!='IOSOpenMWRealModel' or info.get('CFBundleSupportedPlatforms')!=['iPhoneOS'] or info.get('MinimumOSVersion')!='18.0':raise ValueError('App identity/platform mismatch')
    for n,e in entries.items():
        if not stat.S_ISREG(e.mode):raise ValueError('Nonregular app member')
    binaries,deps=p.graph(entries,'IOSOpenMWRealModel',metadata['angle_libraries'],sdk)
    return {'valid':True,'source_commit':manifest['commit'],'binaries':binaries,'dependencies':deps,'sdk_checked':True,'physical_rendering':'UNVERIFIED'}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--app',type=Path,required=True);a.add_argument('--prepared',type=Path,required=True);a.add_argument('--sdk',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    p.core.check_sdk(args.sdk);entries=p.core.collect_bundle(args.app);report=validate(entries,args.prepared,args.sdk)
    args.output.parent.mkdir(parents=True,exist_ok=True);p.core.write_ipa(entries,args.output)
    with zipfile.ZipFile(args.output) as z:
        if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise ValueError('Corrupt/duplicate IPA')
        reopened={}
        for e in z.infolist():
            if e.is_dir():continue
            if not e.filename.startswith(p.core.PREFIX):raise ValueError('Unexpected IPA root')
            name=e.filename[len(p.core.PREFIX):];p.core.safe_name(name);reopened[name]=p.Entry(z.read(e),e.external_attr>>16)
        if reopened!=entries:raise ValueError('Reopened IPA differs')
        validate(reopened,args.prepared,args.sdk)
    report['sha256']=hashlib.sha256(args.output.read_bytes()).hexdigest();print(json.dumps(report,indent=2))
