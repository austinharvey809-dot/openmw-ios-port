import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def prepare(output):
    sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
             for p in ROOT.rglob('*') if p.is_file() and not {'artifacts','build','private','__pycache__'}&set(p.relative_to(ROOT).parts)}
    report={'commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
            'source_sha256_lf':sources,'scope':'G1D private original static model; physical acceptance unverified'}
    data=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();output.mkdir(parents=True,exist_ok=True)
    (output/'g1d-build.json').write_bytes(data)
    (output/'G1DExpected.hpp').write_text('#pragma once\nnamespace G1DExpected {inline constexpr char SHA[]="'+hashlib.sha256(data).hexdigest()+'";}\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--check-dds',type=Path);a=p.parse_args()
    if a.check_dds:
        expected=json.loads((ROOT/'source-closure.json').read_text())
        if a.check_dds.is_symlink() or hashlib.sha256(a.check_dds.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected['dds_sha256_lf']:raise ValueError('DDS source differs from pinned revision')
    if a.output:prepare(a.output)
