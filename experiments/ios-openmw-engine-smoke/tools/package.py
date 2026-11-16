"""Strict iPhoneOS package verification; reuse accepted Mach-O/SDK inspectors."""
import argparse
import hashlib
import importlib.util
import json
import plistlib
import stat
import struct
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('g5_build_provenance',ROOT/'tools/provenance.py')
provenance=importlib.util.module_from_spec(spec);spec.loader.exec_module(provenance)
sys.path.insert(0,str(ROOT.parent/'ios-openmw-world-smoke/tools'))
spec=importlib.util.spec_from_file_location('g4_accepted_package',ROOT.parent/'ios-openmw-world-smoke/tools/package.py')
accepted=importlib.util.module_from_spec(spec);spec.loader.exec_module(accepted)
p=accepted.p
p.core.APP_NAME='IOSOpenMWEngine.app';p.core.PREFIX='Payload/IOSOpenMWEngine.app/'


def registrations(data):
    count,extent=struct.unpack_from('<II',data,16);offset=32;names=set()
    for _ in range(count):
        kind,size=struct.unpack_from('<II',data,offset)
        if kind==2:
            symoff,nsyms,stroff,strsize=struct.unpack_from('<4I',data,offset+8)
            if symoff+nsyms*16>len(data) or stroff+strsize>len(data):raise ValueError('Invalid G5 symbol table')
            strings=data[stroff:stroff+strsize]
            for i in range(nsyms):
                index=struct.unpack_from('<I',data,symoff+i*16)[0]
                if index>=len(strings):raise ValueError('Invalid G5 symbol name')
                end=strings.find(b'\0',index)
                if end<0:raise ValueError('Unterminated G5 symbol name')
                kind,section=struct.unpack_from('<BB',data,symoff+i*16+4)
                if kind&0x0e==0x0e and section: # Defined N_SECT, not an undefined import/reference.
                    names.add(strings[index:end].decode(errors='strict'))
        offset+=size
    required={'_osgdb_dds','_osgdb_tga','_osgdb_bmp','_osgdb_png','_osgdb_jpeg','_osgdb_osg','_osgdb_osg2',
              '_wrapper_serializer_library_osg','_wrapper_serializer_BufferIndexBinding'}
    if not required<=names:raise ValueError('Required genuine OSG registrations absent from G5 executable')
    for token in ('N7MWWorld8ESMStore4load','N7MWWorld8ESMStore5setUp'):
        if not any(token in n for n in names):raise ValueError('Genuine ESMStore implementation absent: '+token)
    return {'registrations':sorted(required),'engine_store_load_and_setup':True}


def validate(entries,prepared,sdk):
    if sdk is None:raise ValueError('A genuine Apple SDK is mandatory for package acceptance')
    original,metadata=p.prepared_resources(prepared)
    allowed={n:b for n,b in original.items() if n.startswith(('Frameworks/','Licenses/','Provenance/'))}
    manifest=json.loads(entries['g5-build.json'].data)
    base=manifest['accepted_g4_build'];generated=manifest['public_resources_sha256']
    provenance.accepted_contract(base)
    new={'Licenses/G5-Lua-readme.html','g5-engine.json'}
    if set(generated)!=set(base['public_resources_sha256'])|new:raise ValueError('Unexpected G5 generated resource inventory')
    if set(entries)!=set(allowed)|set(generated)|{'Info.plist','IOSOpenMWEngine','g5-build.json'}:
        raise ValueError('Exact G5 public bundle inventory mismatch')
    for name,value in entries.items():
        p.core.safe_name(name)
        if not stat.S_ISREG(value.mode):raise ValueError('Nonregular G5 bundle member')
        if Path(name).suffix.lower() in ('.esm','.esp','.bsa','.nif','.dds','.p12','.mobileprovision'):
            raise ValueError('Private game/signing content cannot enter public IPA')
    for name,want in generated.items():
        if provenance.digest(entries[name].data)!=want:raise ValueError('G5 public resource hash mismatch: '+name)
    if any(entries[n].data!=raw for n,raw in allowed.items()):raise ValueError('Verified ANGLE/dependency bytes changed')
    for name,want in base['public_resources_sha256'].items():
        if provenance.digest(entries[name].data)!=want:raise ValueError('Accepted G4 resources changed')
    commit=p.host.git('rev-parse','HEAD').decode().strip()
    if manifest['commit']!=commit or base['commit']!=commit:raise ValueError('G5 source identity mismatch')
    if manifest['source_sha256_lf']!=provenance.sources():raise ValueError('G5 exact source hashes/inventory mismatch')
    if manifest['workflow_sha256_lf']!=provenance.digest(provenance.WORKFLOW.read_bytes().replace(b'\r\n',b'\n')):
        raise ValueError('G5 workflow provenance mismatch')
    if manifest['engine_lock']!=json.loads((ROOT/'engine-lock.json').read_text()) or manifest['new_dependencies']!=json.loads((ROOT/'dependencies.json').read_text()):
        raise ValueError('G5 engine/dependency pins mismatch')
    if provenance.digest(entries['g5-build.json'].data).encode() not in entries['IOSOpenMWEngine'].data:
        raise ValueError('Executable lacks G5 metadata binding')
    info=plistlib.loads(entries['Info.plist'].data)
    if info.get('CFBundleIdentifier')!='org.openmw.experiments.real-model' or info.get('CFBundleExecutable')!='IOSOpenMWEngine' or info.get('CFBundleSupportedPlatforms')!=['iPhoneOS'] or info.get('MinimumOSVersion')!='18.0':
        raise ValueError('G5 identity/platform/deployment mismatch')
    if not info.get('UIFileSharingEnabled') or not info.get('LSSupportsOpeningDocumentsInPlace'):
        raise ValueError('Private Documents import compatibility missing')
    binaries,dependencies=p.graph(entries,'IOSOpenMWEngine',metadata['angle_libraries'],sdk)
    retained=registrations(entries['IOSOpenMWEngine'].data)
    return {'valid':True,'commit':commit,'sdk_checked':True,'exact_public_files':len(entries),
            'binaries':binaries,'dependencies':dependencies,'retained_symbols':retained,'physical_acceptance':'UNVERIFIED'}


def package(app,prepared,sdk,output):
    p.core.check_sdk(sdk);entries=p.core.collect_bundle(app);report=validate(entries,prepared,sdk)
    output.parent.mkdir(parents=True,exist_ok=True);p.core.write_ipa(entries,output)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist())!=len(set(archive.namelist())):raise ValueError('Corrupt/duplicate G5 IPA')
        reopened={}
        for item in archive.infolist():
            if item.is_dir():continue
            if not item.filename.startswith(p.core.PREFIX):raise ValueError('Unexpected G5 IPA root')
            name=item.filename.removeprefix(p.core.PREFIX);p.core.safe_name(name)
            reopened[name]=p.Entry(archive.read(item),item.external_attr>>16)
        if reopened!=entries:raise ValueError('Independently reopened G5 IPA differs')
        validate(reopened,prepared,sdk)
    report['sha256']=provenance.digest(output.read_bytes());return report


if __name__=='__main__':
    a=argparse.ArgumentParser()
    for name in ('app','prepared','sdk','output'):a.add_argument('--'+name,type=Path,required=True)
    args=a.parse_args();print(json.dumps(package(args.app,args.prepared,args.sdk,args.output),indent=2))
