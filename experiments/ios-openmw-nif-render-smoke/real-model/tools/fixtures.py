"""Only self-authored inputs. No installed game file is read here."""
import importlib.util,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_g1c_fixture_encoders',ROOT.parent/'textured/tools/fixtures.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
le=g.le
POSITIVE=('good','rug-properties','vertex-ignore','vertex-diffuse','vertex-fallback',
          'inheritance','override','depth-off','depth-write-only','depth-read-only',
          'two-sided','clockwise','mirrored','alpha-blend','alpha-test','alpha-unsorted','mw-specular')
NEGATIVE={'cycle':'Cyclic/oversized hierarchy','transform':'Nonfinite transform',
          'index':'Index out of range','path':'Unsafe path segment','missing':'', 'image':'Image decode failed',
          'vertex-invalid':'Invalid vertex color mode','lighting-invalid':'Invalid lighting mode',
          'vertex-emission':'Emissive vertex colors','light-emission':'Emission-only lighting',
          'light-emission-ignore':'Emission-only lighting',
          'unknown-property':'NiDitherProperty','stencil-enabled':'stencil-capable EGL',
          'stencil-invalid':'Invalid face draw mode','alpha-invalid':'Invalid GLES blend factors',
          'alpha-flags':'Unknown alpha flags','wireframe':'Wireframe needs',
          'flat-shading':'Only smooth shading','apply-invalid':'texture treatment',
          'filter-invalid':'texture sampler','clamp-invalid':'texture sampler',
          'emissive':'Emissive material','material-invalid':'Invalid material color/alpha',
          'vertex-nan':'Invalid vertex color'}

def inputs(mode='good'):
    if mode not in POSITIVE and mode not in NEGATIVE:raise ValueError('Unknown fixture mode')
    def av(name,props=(),translation=(0,0,0)):
        data=bytearray(g.av(name,props));pos=len(g.net(name))+2;struct.pack_into('<3f',data,pos,*translation);return bytes(data)
    extra=[];props=[]
    def prop(kind,payload):
        index=7+len(extra);extra.append((kind,g.net(kind)+payload));props.append(index);return index
    if mode in ('rug-properties','vertex-ignore','vertex-diffuse','vertex-fallback','inheritance','override',
                'vertex-invalid','lighting-invalid','vertex-emission','light-emission','light-emission-ignore','vertex-nan'):
        vertex_mode={'vertex-diffuse':2,'vertex-fallback':2,'vertex-invalid':9,'vertex-emission':1,'light-emission':2}.get(mode,0)
        lighting={'lighting-invalid':9,'light-emission':0,'light-emission-ignore':0}.get(mode,1)
        prop('NiVertexColorProperty',le('HII',0,vertex_mode,lighting))
    if mode in ('depth-off','depth-write-only','depth-read-only','inheritance','override'):
        prop('NiZBufferProperty',le('H',{'depth-off':0,'depth-write-only':2,'depth-read-only':1,'inheritance':2,'override':0}[mode]))
    if mode in ('two-sided','clockwise','stencil-enabled','stencil-invalid','inheritance','override'):
        draw={'clockwise':2,'stencil-invalid':9}.get(mode,3)
        prop('NiStencilProperty',le('HB7I',0,mode=='stencil-enabled',7,0,0xffffffff,0,0,0,draw))
    if mode in ('alpha-blend','alpha-test','alpha-unsorted','alpha-invalid','alpha-flags','inheritance','override'):
        flags=1|(6<<1)|(7<<5)
        if mode=='alpha-test':flags=0x200|(4<<10)
        if mode=='alpha-unsorted':flags|=0x2000
        if mode=='alpha-invalid':flags=1|(15<<1)
        if mode=='alpha-flags':flags|=0x8000
        prop('NiAlphaProperty',le('HB',flags,128))
    if mode in ('unknown-property','wireframe','flat-shading','mw-specular'):
        prop({'unknown-property':'NiDitherProperty','wireframe':'NiWireframeProperty',
              'flat-shading':'NiShadeProperty','mw-specular':'NiSpecularProperty'}[mode],le('H',0 if mode=='flat-shading' else 1))
    root_props=(4,6,*props) if mode in ('inheritance','override') else ()
    root=av('Root',root_props)+le('IiI',1,0 if mode=='cycle' else 1,0)
    child=av('Offset',translation=(1,2,float('nan') if mode=='transform' else 3))+le('IiI',1,2,0)
    shape_props=(4,6,*props)
    if mode=='inheritance':shape_props=()
    if mode=='override':
        props=[]
        prop('NiVertexColorProperty',le('HII',0,2,1))
        prop('NiZBufferProperty',le('H',3))
        prop('NiStencilProperty',le('HB7I',0,0,7,0,0xffffffff,0,0,0,1))
        prop('NiAlphaProperty',le('HB',0,0))
        shape_props=tuple(props)
    shape=av('Quad',shape_props)+le('ii',3,-1)
    if mode=='mirrored':
        shape=bytearray(shape);struct.pack_into('<f',shape,len(g.net('Quad'))+2+12+36,-1);shape=bytes(shape)
    points=(0,0,0,1,0,0,0,1,0,1,1,0)
    has_colors=mode in ('vertex-ignore','vertex-diffuse','vertex-nan')
    colors=le('16f',*((float('nan') if mode=='vertex-nan' else .2,.4,.6,.5)*4)) if has_colors else b''
    data=le('H',4)+g.boolean(True)+le('12f',*points)+g.boolean(False)+le('4f',0,0,0,2)+g.boolean(has_colors)+colors+le('H',1)+g.boolean(True)+le('8f',0,0,2,0,0,2,2,2)+le('HI6HH',2,6,0,1,2,1,3,99 if mode=='index' else 2,0)
    texture=g.net('Texture')+le('HII',0,99 if mode=='apply-invalid' else 3 if mode=='rug-properties' else 2,1)+g.boolean(True)+le('iIII',5,99 if mode=='clamp-invalid' else 3,99 if mode=='filter-invalid' else 2 if mode=='rug-properties' else 1,0)+bytes(6)
    source=g.net('DDS')+le('B',1)+g.string('../private.dds' if mode=='path' else 'fixture.tga')+le('IIIB',2,0,2,1)
    diffuse=(.25,.5,.75) if mode in ('vertex-ignore','vertex-diffuse','vertex-fallback') else (1,1,1)
    material=g.net('Material')+le('H14f',0,1,1,1,*diffuse,1 if mode=='mw-specular' else 0,0,0,1 if mode=='emissive' else 0,0,0,0,float('nan') if mode=='material-invalid' else .8 if mode=='vertex-diffuse' else 1)
    types=('NiNode','NiNode','NiTriShape','NiTriShapeData','NiTexturingProperty','NiSourceTexture','NiMaterialProperty')
    nif=b'NetImmerse File Format, Version 4.0.0.2\n'+le('II',0x04000002,7+len(extra))+b''.join(g.record(t,b) for t,b in zip(types,(root,child,shape,data,texture,source,material)))+b''.join(g.record(t,b) for t,b in extra)+le('Ii',1,0)
    # A self-authored opaque-white BC2/DXT3 block; dimensions 4x4.
    header=[124,0x1007,4,4,16,0,1]+[0]*11+[32,4,struct.unpack('<I',b'DXT3')[0],0,0,0,0,0]+[0x1000,0,0,0,0]
    dds=b'DDS '+le('31I',*header)+bytes([255]*8)+le('HHI',0xffff,0,0)
    files=[(b'Meshes\\f\\furn_rug_02.nif',nif)]
    if mode!='missing':files.append((b'Textures\\fixture.dds',dds[:12] if mode=='image' else dds))
    return {'Morrowind.esm':g.existing.stat_file(model=b'f\\furn_rug_02.nif\0',name=b'furn_de_rug_02\0'),'Morrowind.bsa':g.existing.bsa.archive(files)}

def write(directory,mode='good'):
    directory.mkdir(parents=True,exist_ok=True)
    for n,b in inputs(mode).items():(directory/n).write_bytes(b)
