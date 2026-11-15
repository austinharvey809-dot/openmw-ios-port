"""Reproducible self-authored CELL/base/reference/NIF/DDS inputs only."""
import functools,importlib.util,math,struct,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=module('_g2_accepted_authored_encoders',REPO/'experiments/ios-openmw-nif-render-smoke/real-model/tools/fixtures.py')
esm=old.g.existing.esm;le=old.le;sub=esm.subrecord;record=esm.record
CELL='G2 Authored Room'
POSITIVE=('good','collision','particles','deleted-reference','negative-light','two-models','attach-light')
NEGATIVE={'missing-cell':'Selected interior not found','missing-base':'Missing/unsupported base ID',
    'bad-scale':'Invalid placement scale','bad-position':'Nonfinite CELL placement',
    'duplicate-base':'Duplicate base ID','duplicate-ref':'Duplicate CELL reference number',
    'water':'Water/weather cells','missing-model':'Missing model for non-light',
    'missing-mesh':"Resource 'meshes/authored/quad.nif' not found",'bad-index':'Index out of range','bad-image':'Image decode failed',
    'unsupported-property':'NiDitherProperty','emission':'Emission-only lighting',
    'bad-cell-data':'record size mismatch, requested 12, got 1','no-entry':'placed teleport door','missing-normal':'original normals',
    'excess-lights':'Point-light budget','duplicate-attach':'Ambiguous AttachLight nodes','zero-normal':'Zero normal',
    'image-budget':'Decoded texture budget exceeded','texture-budget':'Texture storage budget exceeded'}

@functools.lru_cache(maxsize=None)
def authored_assets(mode):
    legacy=old.inputs(mode)
    archive=legacy['Morrowind.bsa'];directory_size,count=struct.unpack_from('<II',archive,4)
    names_start=12+12*count;data_start=12+directory_size+8*count;files={}
    for i in range(count):
        size,offset=struct.unpack_from('<II',archive,12+8*i)
        ni=struct.unpack_from('<I',archive,12+8*count+4*i)[0]+names_start
        end=archive.index(b'\0',ni);name=archive[ni:end].decode().replace('\\','/').lower()
        files[name]=archive[data_start+offset:data_start+offset+size]
    return files

def inputs(mode='good'):
    if mode not in (*POSITIVE,*NEGATIVE):raise ValueError('Unknown G2 fixture mode')
    meshmode={'bad-index':'index','bad-image':'image','unsupported-property':'unknown-property',
              'emission':'light-emission-ignore'}.get(mode,'good')
    files=authored_assets(meshmode)
    nif=next(b for n,b in files.items() if n.endswith('.nif'))
    if mode=='missing-normal':pass # accepted fixture intentionally has none; default below adds normals
    else:
        # Add genuine original-data normals to the self-authored quad.
        points=le('12f',0,0,0,1,0,0,0,1,0,1,1,0)
        needle=le('H',4)+old.g.boolean(True)+points+old.g.boolean(False)
        replacement=le('H',4)+old.g.boolean(True)+points+old.g.boolean(True)+le('12f',*((0,0,0) if mode=='zero-normal' else (0,0,1))*4)
        if nif.count(needle)!=1:raise ValueError('Authored geometry anchor differs')
        nif=nif.replace(needle,replacement)
    if mode in ('collision','particles','attach-light','duplicate-attach'):
        oldroot=old.g.av('Root')+le('IiI',1,1,0)
        children=(1,7,8) if mode=='duplicate-attach' else (1,7)
        newroot=old.g.av('Root')+le('I',len(children))+b''.join(le('i',i) for i in children)+le('I',0)
        nif=nif.replace(oldroot,newroot)
        if mode in ('collision','particles'):
            kind='RootCollisionNode' if mode=='collision' else 'NiBSParticleNode'
            extras=old.g.record(kind,old.g.av('Excluded')+le('IiI',1,8,0))
            extras+=old.g.record('NiTriShape',old.g.av('ExcludedGeometry',(4,6))+le('ii',3,-1));count=2
        else:
            av=bytearray(old.g.av('AttachLight'));struct.pack_into('<3f',av,len(old.g.net('AttachLight'))+2,2,3,4)
            extra=old.g.record('NiNode',bytes(av)+le('II',0,0))
            count=2 if mode=='duplicate-attach' else 1;extras=extra*count
        index=len(b'NetImmerse File Format, Version 4.0.0.2\n')+4
        n=struct.unpack_from('<I',nif,index)[0];nif=nif[:index]+le('I',n+count)+nif[index+4:]
        nif=nif[:-8]+extras+nif[-8:]
    mod=b'Authored\\quad.nif\0'
    def base(kind,name,model=True):
        model_name=b'Authored\\second.nif\0' if mode=='two-models' and name=='chair' else mod
        data=sub(b'NAME',name.encode()+b'\0')+(sub(b'MODL',model_name) if model else b'')
        if kind==b'MISC':data+=sub(b'MCDT',le('fii',1,1,0))
        if kind==b'CONT':data+=sub(b'CNDT',le('f',100))+sub(b'FLAG',le('i',8))
        if kind==b'LIGH':data+=sub(b'LHDT',le('fiiiIi',1,1,-1,512,0x00ffffff,4 if mode=='negative-light' else 0))
        if kind==b'LIGH' and mode.endswith('-budget'):data+=sub(b'FNAM',mode.encode()+b'\0')
        return record(kind,data)
    bases=b''.join(base(kind,name,not(mode=='missing-model' and name=='chair')) for kind,name in
        ((b'STAT','room'),(b'MISC','chair'),(b'DOOR','door'),(b'ACTI','bed'),(b'CONT','box'),(b'LIGH','lamp'),(b'ACTI','northmarker')))
    bases+=base(b'LIGH','ambient',False)
    if mode=='duplicate-base':bases+=base(b'STAT','room')
    def ref(number,name,position=(0,0,0),rotation=(0,0,0),scale=1,door=False,deleted=False):
        data=sub(b'FRMR',le('I',number))+sub(b'NAME',name.encode()+b'\0')
        if deleted:data+=sub(b'DELE',b'\0\0\0')
        data+=sub(b'XSCL',le('f',scale))
        if door:data+=sub(b'DODT',le('6f',*(0,)*6))+sub(b'DNAM',b'Authored Outside\0')
        return data+sub(b'DATA',le('6f',*position,*rotation))
    refs=ref(1,'room')+ref(2,'chair',(10,20,float('nan') if mode=='bad-position' else 30),(0,0,math.pi/2),float('nan') if mode=='bad-scale' else 2)
    refs+=ref(3,'door',(-10,0,0),door=mode!='no-entry')+ref(4,'bed')+ref(5,'box')+ref(6,'lamp')+ref(7,'northmarker')+ref(8,'ambient')
    if mode=='missing-base':refs+=ref(9,'not-defined')
    if mode=='duplicate-ref':refs+=ref(1,'chair')
    if mode=='deleted-reference':refs+=ref(9,'chair',deleted=True)
    if mode=='excess-lights':refs+=b''.join(ref(i,'ambient') for i in range(9,18))
    cellname='Other Room' if mode=='missing-cell' else CELL
    header=sub(b'NAME',cellname.encode()+b'\0')+sub(b'DATA',b'x' if mode=='bad-cell-data' else le('iii',3 if mode=='water' else 1,0,0))
    header+=sub(b'AMBI',le('IIIf',0x00404040,0,0,0))
    esmb=esm.tes3_header()+bases+record(b'CELL',header+refs)
    items=[] if mode=='missing-mesh' else [(b'Meshes\\Authored\\quad.nif',nif)]
    if mode=='two-models':items.append((b'Meshes\\Authored\\second.nif',nif))
    items+=[(b'Textures\\fixture.dds',next(b for n,b in files.items() if n.endswith('.dds')))]
    return {'Morrowind.esm':esmb,'Morrowind.bsa':old.g.existing.bsa.archive(items)}

def write(directory,mode='good'):
    directory.mkdir(parents=True,exist_ok=True)
    for n,b in inputs(mode).items():(directory/n).write_bytes(b)
