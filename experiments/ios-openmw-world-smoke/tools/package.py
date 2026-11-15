"""Strict public bundle/IPA inventory; original game files are never resources."""
import argparse,hashlib,json,plistlib,stat,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'ios-openmw-nif-render-smoke/textured/tools'))
import support
sys.path.insert(0,str(ROOT/'tools'))
import provenance
p=support.package
p.core.APP_NAME='IOSOpenMWWorld.app';p.core.PREFIX='Payload/IOSOpenMWWorld.app/'

def validate(entries,prepared,sdk):
    original,base_metadata=p.prepared_resources(prepared)
    allowed={n:b for n,b in original.items() if n.startswith(('Frameworks/','Licenses/','Provenance/'))}
    if 'g4-build.json' not in entries:raise ValueError('Missing bound G4 build provenance')
    manifest=json.loads(entries['g4-build.json'].data)
    generated=manifest['public_resources_sha256']
    expected=set(allowed)|set(generated)|{'Info.plist','IOSOpenMWWorld','g4-build.json'}
    if set(entries)!=expected:raise ValueError('Exact public G4 inventory mismatch')
    for name in generated:
        p.core.safe_name(name)
        if not (name.startswith(('Shaders/','Licenses/G4-')) or name in ('g4-environment.json','g4-dependencies.json')):
            raise ValueError('Unexpected G4 public resource category')
        if Path(name).suffix.lower() in ('.esm','.esp','.bsa','.nif','.dds'):raise ValueError('Game assets cannot enter the public application')
        if hashlib.sha256(entries[name].data).hexdigest()!=generated[name]:raise ValueError('Generated G4 resource changed: '+name)
    if any(entries[n].data!=b for n,b in allowed.items()):raise ValueError('Verified ANGLE/dependency bytes changed')
    if manifest['commit']!=support.host.git('rev-parse','HEAD').decode().strip():raise ValueError('Source commit mismatch')
    if manifest['source_sha256_lf']!=provenance.sources():raise ValueError('Exact G4 source inventory differs')
    expected_workflow=hashlib.sha256(provenance.WORKFLOW.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    if manifest['workflow_sha256_lf']!=expected_workflow:raise ValueError('Workflow provenance differs')
    if hashlib.sha256(entries['g4-build.json'].data).hexdigest().encode() not in entries['IOSOpenMWWorld'].data:
        raise ValueError('Binary lacks G4 provenance binding')
    info=plistlib.loads(entries['Info.plist'].data)
    if info.get('CFBundleIdentifier')!='org.openmw.experiments.real-model' or info.get('CFBundleExecutable')!='IOSOpenMWWorld' or info.get('CFBundleSupportedPlatforms')!=['iPhoneOS'] or info.get('MinimumOSVersion')!='18.0':
        raise ValueError('App identity/platform/deployment mismatch')
    if any(not stat.S_ISREG(entry.mode) for entry in entries.values()):raise ValueError('Nonregular public bundle member')
    metadata=json.loads(original['g1b-build.json'])
    binaries,deps=p.graph(entries,'IOSOpenMWWorld',metadata['angle_libraries'],sdk)
    return {'valid':True,'source_commit':manifest['commit'],'binaries':binaries,'dependencies':deps,
        'sdk_checked':True,'exact_public_files':len(expected),'physical_rendering':'UNVERIFIED'}

def package(app,prepared,sdk,output):
    p.core.check_sdk(sdk);entries=p.core.collect_bundle(app);report=validate(entries,prepared,sdk)
    output.parent.mkdir(parents=True,exist_ok=True);p.core.write_ipa(entries,output)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist())!=len(set(archive.namelist())):raise ValueError('Corrupt/duplicate IPA')
        reopened={}
        for entry in archive.infolist():
            if entry.is_dir():continue
            if not entry.filename.startswith(p.core.PREFIX):raise ValueError('Unexpected IPA root')
            name=entry.filename[len(p.core.PREFIX):];p.core.safe_name(name)
            reopened[name]=p.Entry(archive.read(entry),entry.external_attr>>16)
        if reopened!=entries:raise ValueError('Independently reopened IPA differs')
        validate(reopened,prepared,sdk)
    report['sha256']=hashlib.sha256(output.read_bytes()).hexdigest();return report
if __name__=='__main__':
    a=argparse.ArgumentParser()
    for name in ('app','prepared','sdk','output'):a.add_argument('--'+name,type=Path,required=True)
    args=a.parse_args();print(json.dumps(package(args.app,args.prepared,args.sdk,args.output),indent=2))
