"""Only self-authored inputs. No installed game file is read here."""
import importlib.util,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_g1c_fixture_encoders',ROOT.parent/'textured/tools/fixtures.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
le=g.le
def inputs(mode='good'):
    def av(name,props=(),translation=(0,0,0)):
        data=bytearray(g.av(name,props));pos=len(g.net(name))+2;struct.pack_into('<3f',data,pos,*translation);return bytes(data)
    root=av('Root')+le('IiI',1,0 if mode=='cycle' else 1,0)
    child=av('Offset',translation=(1,2,float('nan') if mode=='transform' else 3))+le('IiI',1,2,0)
    shape=av('Quad',(4,6))+le('ii',3,-1)
    points=(0,0,0,1,0,0,0,1,0,1,1,0)
    data=le('H',4)+g.boolean(True)+le('12f',*points)+g.boolean(False)+le('4f',0,0,0,2)+g.boolean(False)+le('H',1)+g.boolean(True)+le('8f',0,0,2,0,0,2,2,2)+le('HI6HH',2,6,0,1,2,1,3,99 if mode=='index' else 2,0)
    texture=g.net('Texture')+le('HII',0,2,1)+g.boolean(True)+le('iIII',5,3,1,0)+bytes(6)
    source=g.net('DDS')+le('B',1)+g.string('../private.dds' if mode=='path' else 'fixture.tga')+le('IIIB',2,0,2,1)
    material=g.net('Material')+le('H14f',0,1,1,1,1,1,1,0,0,0,0,0,0,0,1)
    types=('NiNode','NiNode','NiTriShape','NiTriShapeData','NiTexturingProperty','NiSourceTexture','NiMaterialProperty')
    nif=b'NetImmerse File Format, Version 4.0.0.2\n'+le('II',0x04000002,7)+b''.join(g.record(t,b) for t,b in zip(types,(root,child,shape,data,texture,source,material)))+le('Ii',1,0)
    # A self-authored opaque-white BC2/DXT3 block; dimensions 4x4.
    header=[124,0x1007,4,4,16,0,1]+[0]*11+[32,4,struct.unpack('<I',b'DXT3')[0],0,0,0,0,0]+[0x1000,0,0,0,0]
    dds=b'DDS '+le('31I',*header)+bytes([255]*8)+le('HHI',0xffff,0,0)
    files=[(b'Meshes\\f\\furn_rug_02.nif',nif)]
    if mode!='missing':files.append((b'Textures\\fixture.dds',dds[:12] if mode=='image' else dds))
    return {'Morrowind.esm':g.existing.stat_file(model=b'f\\furn_rug_02.nif\0',name=b'furn_de_rug_02\0'),'Morrowind.bsa':g.existing.bsa.archive(files)}
def write(directory,mode='good'):
    directory.mkdir(parents=True,exist_ok=True)
    for n,b in inputs(mode).items():(directory/n).write_bytes(b)
