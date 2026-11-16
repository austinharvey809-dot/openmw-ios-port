"""Native ESMStore integration, preserving actual crash/timeout diagnostics."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
G4=ROOT.parent/'ios-openmw-world-smoke'
sys.path.insert(0,str(G4/'tools'))
import fixtures
import run_cases as runner


def inputs(mode):
    source=fixtures.inputs('good')
    def book(value=7):
        return fixtures.sub(b'NAME',b'g5_book\0')+fixtures.sub(b'BKDT',fixtures.le('fiiii',1, value,0,-1,0))
    source['Morrowind.esm']+=fixtures.record(b'BOOK',book())
    if mode in ('override','delete','ignored','load-order') or mode.startswith('lua'):
        header=fixtures.old.old.esm.tes3_header(0)[16:]+fixtures.sub(b'MAST',b'Morrowind.esm\0')+fixtures.sub(b'DATA',fixtures.le('Q',len(source['Morrowind.esm'])))
        payload=fixtures.sub(b'NAME',b'g5_book\0')+fixtures.sub(b'DELE',fixtures.le('I',0)) if mode=='delete' else book(42)
        record=fixtures.record(b'BOOK',payload)
        if mode=='ignored':
            import struct
            record=record[:12]+struct.pack('<I',0x1000)+record[16:]
        if mode.startswith('lua'):
            binary=b'\0\2\1' if mode!='lua-binary-invalid' else b'\xff'
            if mode=='lua-table':binary=b'\0\3\x21x\2\1\4'
            if mode.startswith('lua-refnum'):binary=b'\0\xc0o'+fixtures.le('Ii',23,2 if mode=='lua-refnum-invalid' else 1)
            data=fixtures.sub(b'LUAS',b'g5_authored.lua\0')+fixtures.sub(b'LUAF',fixtures.le('I',0))
            data+=fixtures.sub(b'LUAD',binary)+fixtures.sub(b'LUAI',fixtures.le('BIi',1,23,2 if mode=='lua-invalid' else 1))
            record=fixtures.record(b'LUAL',data)
        source['Authored.esp']=fixtures.record(b'TES3',header)+record
    if mode=='unknown':source['Morrowind.esm']+=fixtures.record(b'ZZZZ',b'')
    return source


def run(binary,output):
    positives={'good':16,'override':16,'delete':13,'ignored':16,'lua':19,'lua-table':19,'lua-refnum':19}
    negatives={'unknown':'Unknown record: ZZZZ','empty-content':'content count outside','duplicate-content':'duplicate content filename',
               'load-order':'missing or out-of-order master','lua-invalid':'Incorrect contentFile index','lua-binary-invalid':'Incorrect version of Lua serialization format',
               'lua-refnum-invalid':'Incorrect contentFile index'}
    results=[];runner.save(output,results)
    for case in (*positives,*negatives):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,raw in inputs(case).items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            before=runner.snapshot(root)
            row={'case':case,'status':'RUNNING'};results.append(row);runner.save(output,results)
            row.update(runner.capture([binary,root,case],120));runner.save(output,results)
            try:
                runner.process_ok(row)
                if case in positives:
                    report=json.loads(row['stdout'])
                    if row['exit']!=0 or report['status']!='PASS' or report['checks']!=positives[case]:raise ValueError('False engine-store PASS/assertion inventory')
                elif row['exit']!=1 or negatives[case] not in row['stderr']:raise ValueError('Wrong native rejection: '+negatives[case])
                if before!=runner.snapshot(root):raise ValueError('Authored inputs changed')
            except Exception as e:
                error=runner.failure(row,output,str(e));runner.save(output,results);raise error from e
            row['status']='PASS';runner.save(output,results)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--binary',type=Path);g.add_argument('--world-binary',type=Path)
    p.add_argument('--shaders',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.world_binary:
        result=runner.run(a.world_binary.resolve(),a.shaders.resolve(),a.output)
    else:result=run(a.binary.resolve(),a.output)
    print(json.dumps({'status':'PASS','cases':len(result),'evidence':str(a.output)},indent=2))
