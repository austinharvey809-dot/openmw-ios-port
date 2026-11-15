"""Authored 9-CELL/LAND world. No original placement arrays or image bytes."""
import importlib.util,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_g3_authored_g2',ROOT.parent/'ios-openmw-interior-smoke/tools/fixtures.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sub=old.sub;record=old.record;le=old.le
POSITIVE=('good','multi-texture','sloped','no-colors','deleted-reference','clamped-scale','emissive','inherited-emission','emission-override','vertex-emission','light-emission','light-emission-ignore','vertex-diffuse','vertex-fallback')
NEGATIVE={'missing-cell':'Missing selected exterior CELL','missing-land':'Missing selected terrain',
    'missing-height':'Missing required VHGT/VNML/VTEX','missing-texture':'Missing/default LTEX',
    'bad-height':'Nonfinite height','bad-seam':'Height seam mismatch','zero-normal':'Zero terrain normal',
    'bad-scale':'Invalid placement scale','duplicate-ref':'Duplicate reference number',
    'missing-base':'Missing/deleted base ID','unsupported-property':'NiDitherProperty',
    'missing-spawn':'Missing genuine Fargoth arrival door','invalid-spawn':'Invalid arrival position',
    'bad-image':'Terrain image decode failed','material-invalid':'Invalid material alpha/emission',
    'vertex-invalid':'Invalid vertex color mode','lighting-invalid':'Invalid lighting mode',
    'unsafe-land-texture':'Unsafe terrain texture path','missing-halo-texture':'Missing/default LTEX'}

def archive_members(data):
    size,count=struct.unpack_from('<II',data,4);start=12+size+8*count;names=12+12*count;items=[]
    for i in range(count):
        offset=names+struct.unpack_from('<I',data,12+8*count+4*i)[0];end=data.index(b'\0',offset)
        length,position=struct.unpack_from('<II',data,12+8*i)
        items.append((data[offset:end],data[start+position:start+position+length]))
    return items
def inputs(mode='good'):
    if mode not in (*POSITIVE,*NEGATIVE):raise ValueError('Unknown G3 fixture case')
    originals=old.inputs({'unsupported-property':'unsupported-property','bad-image':'bad-image'}.get(mode,'good'))
    if mode in ('emissive','inherited-emission','emission-override','vertex-emission','light-emission','light-emission-ignore','vertex-diffuse','vertex-fallback','material-invalid','vertex-invalid','lighting-invalid'):
        files=old.authored_assets('inheritance' if mode in ('inherited-emission','emission-override') else mode);nif=next(value for name,value in files.items() if name.endswith('.nif'))
        if mode in ('inherited-emission','emission-override'):
            g=old.old.g
            def material(name,emission):return g.net(name)+le('H14f',0,1,1,1,1,1,1,0,0,0,*emission,0,1)
            original=material('Material',(0,0,0))
            if nif.count(original)!=1:raise ValueError('Inherited material fixture anchor')
            nif=nif.replace(original,material('Material',(.2,.1,0)))
            if mode=='emission-override':
                index=len(b'NetImmerse File Format, Version 4.0.0.2\n')+4;count=struct.unpack_from('<I',nif,index)[0]
                shape=g.av('Quad')+le('ii',3,-1)
                if nif.count(shape)!=1:raise ValueError('Override shape fixture anchor')
                nif=nif.replace(shape,g.av('Quad',(count,))+le('ii',3,-1))
                nif=nif[:index]+le('I',count+1)+nif[index+4:]
                nif=nif[:-8]+g.record('NiMaterialProperty',material('ChildMaterial',(.4,.2,.1)))+nif[-8:]
        points=le('12f',0,0,0,1,0,0,0,1,0,1,1,0);needle=le('H',4)+old.old.g.boolean(True)+points+old.old.g.boolean(False)
        if nif.count(needle)!=1:raise ValueError('Material fixture normal anchor')
        nif=nif.replace(needle,le('H',4)+old.old.g.boolean(True)+points+old.old.g.boolean(True)+le('12f',*(0,0,1)*4))
        originals['Morrowind.bsa']=old.old.g.existing.bsa.archive([(b'Meshes\\Authored\\quad.nif',nif),(b'Textures\\fixture.dds',next(value for name,value in files.items() if name.endswith('.dds')))])
    h=old.esm.tes3_header()
    base=record(b'STAT',sub(b'NAME',b'floor\0')+sub(b'MODL',b'Authored\\quad.nif\0'))
    ltex=record(b'LTEX',sub(b'NAME',b'AuthoredLand\0')+sub(b'INTV',le('I',0))+sub(b'DATA',b'../fixture.dds\0' if mode=='unsafe-land-texture' else b'fixture.dds\0'))
    multi=mode in ('multi-texture','missing-halo-texture')
    if multi:
        for index,name in ((1,b'second.dds'),(2,b'halo.dds')):
            if mode=='missing-halo-texture' and index==2:continue
            ltex+=record(b'LTEX',sub(b'NAME',b'AuthoredLand'+str(index).encode()+b'\0')+sub(b'INTV',le('I',index))+sub(b'DATA',name+b'\0'))
        items=archive_members(originals['Morrowind.bsa']);dds=next(b for n,b in items if n.lower().endswith(b'.dds'))
        for name,color in ((b'Textures\\second.dds',0xf800),(b'Textures\\halo.dds',0x001f)):
            image=bytearray(dds);struct.pack_into('<H',image,136,color);items.append((name,bytes(image)))
        originals['Morrowind.bsa']=old.old.g.existing.bsa.archive(items)
    cells=b'';number=0
    for x in range(-3,0):
        for y in range(-10,-7):
            if mode=='missing-cell' and (x,y)==(-2,-9):continue
            number+=1;ref=le('I',1 if mode=='duplicate-ref' else number)
            scale=float('nan') if mode=='bad-scale' else 0 if mode=='clamped-scale' else 1
            r=sub(b'FRMR',ref)+sub(b'NAME',b'undefined\0' if mode=='missing-base' else b'floor\0')+sub(b'XSCL',le('f',scale))
            if mode=='deleted-reference' and (x,y)==(-3,-10):r+=sub(b'DELE',b'\0\0\0')
            r+=sub(b'DATA',le('6f',x*8192+128,y*8192+128,0,0,0,0))
            cells+=record(b'CELL',sub(b'NAME',b'Authored Exterior\0')+sub(b'DATA',le('Iii',0,x,y))+r)
    # Read-only genuine teleport destination supplies spawn, not an app coordinate.
    spawn=b'' if mode=='missing-spawn' else sub(b'FRMR',le('I',100))+sub(b'NAME',b'floor\0')+sub(b'DODT',le('6f',-12000,-68000,float('nan') if mode=='invalid-spawn' else 16,0,0,.25))+sub(b'DATA',le('6f',0,0,0,0,0,0))
    cells+=record(b'CELL',sub(b'NAME',b"Seyda Neen, Fargoth's House\0")+sub(b'DATA',le('Iii',1,0,0))+sub(b'AMBI',le('IIIf',0,0,0,0))+spawn)
    lands=b''
    for x in range(-4,1):
        for y in range(-11,-6):
            if mode=='missing-land' and (x,y)==(-3,-10):continue
            offset=float('nan') if mode=='bad-height' else (10 if mode=='bad-seam' and (x,y)==(-2,-9) else 0)
            deltas=bytearray(65*65)
            if mode=='sloped':
                offset=float(x*64);deltas[:]=bytes(0 if i%65==0 else 1 for i in range(65*65))
            hgt=b'' if mode=='missing-height' else sub(b'VHGT',le('f',offset)+deltas+b'\0\0\0')
            normals=bytes((0,0,0 if mode=='zero-normal' else 127))*4225
            payload=sub(b'INTV',le('ii',x,y))+sub(b'DATA',le('I',7))+sub(b'VNML',normals)+hgt
            if mode!='no-colors':payload+=sub(b'VCLR',bytes((255,240,220))*4225)
            if multi:
                raster=[3 if x==-4 or y==-7 else 1 if tx<8 else 2 for ty in range(16) for tx in range(16)]
                tiled=[raster[(y1*4+y2)*16+x1*4+x2] for y1 in range(4) for x1 in range(4) for y2 in range(4) for x2 in range(4)]
            else:tiled=[2 if mode=='missing-texture' else 1]*256
            payload+=sub(b'VTEX',le('256H',*tiled))
            lands+=record(b'LAND',payload)
    return {'Morrowind.esm':h+base+ltex+cells+lands,'Morrowind.bsa':originals['Morrowind.bsa']}
def write(directory,mode):
    directory.mkdir(parents=True,exist_ok=True)
    for name,value in inputs(mode).items():(directory/name).write_bytes(value)
