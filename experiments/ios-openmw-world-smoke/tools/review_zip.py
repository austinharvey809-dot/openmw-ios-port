"""Explicit source/evidence allowlist, hashes and independently reopened ZIP."""
import argparse,hashlib,json,stat,zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import paths,provenance

EVIDENCE={
    'final-validation/validation.json':'validation.json',
    'final-validation/g4-python.log':'g4-python.log',
    'final-validation/workflow-syntax.log':'workflow-syntax.log',
    'configured-audit.json':'configured-audit.json',
    'imported-provider-audit.json':'imported-provider-audit.json',
    'native-cases.json':'authored-native-cases.json',
    'windows-build.log':'windows-build.log',
    'windows-configure.log':'windows-configure.log',
    'dependency-verification.log':'dependency-verification.log',
    'legacy-validation/preservation-audit.log':'preservation-audit.json',
    'legacy-validation/provider-audit.log':'legacy-provider-audit.json',
    'legacy-validation/validation.json':'legacy-validator-summary.json',
    'g1c-cmake-scope.log':'g1c-cmake-scope.log',
    'private-inspection/inspection.json':'private-inspection-aggregates.json',
}

def inventory():
    result={str((paths.ROOT/name).relative_to(paths.REPO)).replace('\\','/'):paths.ROOT/name for name in provenance.sources()}
    result[provenance.WORKFLOW.relative_to(paths.REPO).as_posix()]=provenance.WORKFLOW
    return dict(sorted(result.items()))

def create(output):
    if not output.resolve().is_relative_to(paths.ROOT/'artifacts'):raise ValueError('Review ZIP belongs under ignored G4 artifacts')
    validated=json.loads((paths.ROOT/'artifacts/final-validation/validation.json').read_text())
    if validated['source_sha256_lf']!=provenance.sources():raise ValueError('Source changed after final validation')
    workflow=hashlib.sha256(provenance.WORKFLOW.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    if validated['workflow_sha256_lf']!=workflow:raise ValueError('Workflow changed after final validation')
    entries={name:p.read_bytes() for name,p in inventory().items()}
    for source,name in EVIDENCE.items():entries['experiments/ios-openmw-world-smoke/review-evidence/'+name]=(paths.ROOT/'artifacts'/source).read_bytes()
    for p in (paths.ROOT/'artifacts/legacy-validation').glob('*.log'):
        if p.stem in ('g0b','g0c','g1a','g1b','g1c','g1d','g2','g3'):
            entries['experiments/ios-openmw-world-smoke/review-evidence/'+p.name]=p.read_bytes()
    for name in entries:
        if Path(name).suffix.lower() in ('.esm','.esp','.bsa','.nif','.dds','.png','.jpg','.jpeg','.dll','.exe','.ipa','.a','.zip'):
            raise ValueError('Asset/binary is not review source: '+name)
        if name.startswith('experiments/ios-osg-smoke/'):raise ValueError('Unrelated Build15 file in archive')
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(entries.items())}
    entries['REVIEW-SHA256.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(entries.items()):
            item=zipfile.ZipInfo(name,date_time=(2026,11,15,12,0,0));item.create_system=3
            item.external_attr=(stat.S_IFREG|0o644)<<16;item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,data)
    with zipfile.ZipFile(output) as reopened:
        if reopened.testzip() or set(reopened.namelist())!=set(entries) or len(reopened.namelist())!=len(entries):raise ValueError('Reopened review archive mismatch')
        if any(reopened.read(name)!=data for name,data in entries.items()):raise ValueError('Review bytes changed')
    report={'file':str(output.resolve()),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,
        'source_files':len(inventory()),'evidence_files':len(entries)-len(inventory())-1,'manifest_files':1,'reopened_crc_and_hashes':'PASS',
        'proprietary_assets':'none','published':False}
    output.with_suffix('.zip.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(create(a.output),indent=2))
