"""Authored CELL/LAND/NIF/BSA fixtures; never read original game assets."""
import importlib.util,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_g4_authored_g3',ROOT.parent/'ios-openmw-exterior-smoke/tools/fixtures.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sub=old.sub;record=old.record;le=old.le
POSITIVE=('good','multi-texture','placement','cache','unload','door','session','suspend',
          'device-rejection','maintenance-clock','cache-clock','notification-concurrency','notification-lifetime','shutdown',
          'stream','stream-rollback','door-transition','gles-terrain','input-profile',
          'plugin-override','plugin-delete','plugin-new','plugin-move','plugin-palette','loose-override','last-bsa-wins')
NEGATIVE={'missing-master':'missing or out-of-order master','load-order':'missing or out-of-order master',
          'duplicate-content':'duplicate content filename','deleted-cell':'deleted CELL unsupported',
          'deleted-land':'deleted LAND unsupported','bad-scale':'invalid original scale',
          'invalid-destination':'nonfinite original placement/destination',
          'missing-mesh':'stage=ResourceSystem/SceneManager/NifOsg',
          'broken-nif':'stage=ResourceSystem/SceneManager/NifOsg',
          'missing-image':'image fallback','bad-height':'nonfinite LAND height',
          'locked-door':'locked/trapped door','bad-terrain-image':'image fallback',
          'missing-base':'missing/deleted base reference','deleted-base':'missing/deleted base reference'}

def records(data):
    offset=0
    while offset<len(data):
        if len(data)-offset<16:raise ValueError('Authored record truncated')
        tag,size,reserved,flags=struct.unpack_from('<4sIII',data,offset);offset+=16
        if offset+size>len(data):raise ValueError('Authored record size invalid')
        yield tag,data[offset:offset+size];offset+=size

def subs(data):
    offset=0
    while offset<len(data):
        tag,size=struct.unpack_from('<4sI',data,offset);offset+=8
        if offset+size>len(data):raise ValueError('Authored subrecord size invalid')
        yield tag,data[offset:offset+size];offset+=size

def cell_header(x=-2,y=-9):return sub(b'NAME',b'Authored Exterior\0')+sub(b'DATA',le('Iii',0,x,y))
def reference(number,name=b'floor',z=0,deleted=False):
    return sub(b'FRMR',le('I',number))+sub(b'NAME',name+b'\0')+(sub(b'DELE',b'\0\0\0') if deleted else b'')+sub(b'DATA',le('6f',-12000,-68000,z,0,0,0))

def inputs(mode):
    if mode not in (*POSITIVE,*NEGATIVE):raise ValueError('Unknown G4 fixture case')
    source=old.inputs(mode if mode in ('multi-texture','bad-height','bad-scale','invalid-spawn') else 'good')
    values=list(records(source['Morrowind.esm']));rebuilt=[]
    for tag,data in values:
        if tag==b'CELL':
            header=list(subs(data));name=header[0][1].rstrip(b'\0')
            if name==b"Seyda Neen, Fargoth's House":
                data=data.replace(sub(b'NAME',b'floor\0'),sub(b'NAME',b'entry\0'))
                if mode=='invalid-destination':
                    data=data.replace(sub(b'DODT',le('6f',-12000,-68000,16,0,0,.25)),sub(b'DODT',le('6f',-12000,-68000,float('nan'),0,0,.25)))
            else:
                coord=next(value for kind,value in header if kind==b'DATA');flags,x,y=struct.unpack('<Iii',coord)
                if (x,y)==(-2,-9):
                    door=sub(b'FRMR',le('I',200))+sub(b'NAME',b'entry\0')+sub(b'DODT',le('6f',0,0,16,0,0,0))
                    door+=sub(b'DNAM',b"Seyda Neen, Fargoth's House\0")+sub(b'DATA',le('6f',-12000,-68000,16,0,0,0))
                    data+=door
        rebuilt.append(record(tag,data))
    door_base=record(b'DOOR',sub(b'NAME',b'entry\0')+sub(b'MODL',b'Authored\\quad.nif\0'))
    source['Morrowind.esm']=rebuilt[0]+door_base+b''.join(rebuilt[1:])
    if mode.startswith('plugin-') or mode in ('missing-master','load-order','deleted-cell','deleted-land'):
        # A real TES3 master mapping, not fake remapped reference IDs.
        header=old.old.esm.tes3_header(0)[16:]+sub(b'MAST',b'Absent.esm\0' if mode=='missing-master' else b'Morrowind.esm\0')+sub(b'DATA',le('Q',len(source['Morrowind.esm'])))
        payload=cell_header()
        if mode=='plugin-new':payload+=reference(5,z=128)
        elif mode=='plugin-move':payload+=sub(b'MVRF',le('I',0x01000005))+sub(b'CNDT',le('ii',-1,-9))+reference(0x01000005,z=64)
        elif mode!='deleted-land':payload+=reference(0x01000005,z=64,deleted=mode=='plugin-delete')
        if mode=='deleted-cell':payload=cell_header()+sub(b'DELE',le('I',0))
        plugin=record(b'TES3',header)
        if mode=='plugin-palette':
            plugin+=record(b'LTEX',sub(b'NAME',b'PluginLand\0')+sub(b'INTV',le('I',0))+sub(b'DATA',b'plugin.dds\0'))
            plugin+=next(record(tag,data) for tag,data in records(source['Morrowind.esm']) if tag==b'LAND' and data.startswith(sub(b'INTV',le('ii',-2,-9))))
            members=old.archive_members(source['Morrowind.bsa'])
            dds=next(data for name,data in members if name.lower().endswith(b'.dds'))
            source['Morrowind.bsa']=old.old.old.g.existing.bsa.archive(members+[(b'Textures\\plugin.dds',dds)])
        elif mode=='deleted-land':plugin+=record(b'LAND',sub(b'INTV',le('ii',-2,-9))+sub(b'DELE',le('I',0)))
        else:plugin+=record(b'CELL',payload)
        source['Authored.esp']=plugin
    if mode=='missing-base':
        source['Morrowind.esm']=b''.join(record(tag,data) for tag,data in records(source['Morrowind.esm']) if tag!=b'STAT')
    if mode=='deleted-base':
        header=old.old.esm.tes3_header(0)[16:]+sub(b'MAST',b'Morrowind.esm\0')+sub(b'DATA',le('Q',len(source['Morrowind.esm'])))
        source['Authored.esp']=record(b'TES3',header)+record(b'STAT',sub(b'NAME',b'floor\0')+sub(b'DELE',le('I',0)))
    if mode=='stream-rollback':
        source['Morrowind.esm']+=record(b'CELL',cell_header(0,-9)+reference(700,b'missing-base'))
    if mode in ('broken-nif','missing-image','bad-terrain-image','loose-override','last-bsa-wins'):
        members=old.archive_members(source['Morrowind.bsa'])
        if mode=='broken-nif':members=[(name,b'Invalid authored NIF' if name.lower().endswith(b'.nif') else value) for name,value in members]
        elif mode=='missing-image':members=[(name,value) for name,value in members if not name.lower().endswith(b'.dds')]
        elif mode=='bad-terrain-image':
            members.append((b'Textures\\broken.dds',b'Invalid authored DDS'))
            esm=source['Morrowind.esm'];source['Morrowind.esm']=b''.join(record(tag,data.replace(sub(b'DATA',b'fixture.dds\0'),sub(b'DATA',b'broken.dds\0')) if tag==b'LTEX' else data) for tag,data in records(esm))
        elif mode=='loose-override':
            image=next(value for name,value in members if name.lower().endswith(b'.dds'))
            source['loose/Textures/fixture.dds']=image+b'G4-loose-priority'
        elif mode=='last-bsa-wins':
            source['Authored.bsa']=old.old.old.g.existing.bsa.archive([(name,value+b'G4-last-archive' if name.lower().endswith(b'.dds') else value) for name,value in members])
        source['Morrowind.bsa']=old.old.old.g.existing.bsa.archive(members)
    return source

def write(directory,mode):
    directory.mkdir(parents=True,exist_ok=True)
    for name,data in inputs(mode).items():
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
