"""Read-only real-content diagnostic metadata. Never export original game bytes.

This is not a replacement for the genuine native interior-check executable.
"""
import argparse,collections,hashlib,json,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import inspect_cells as source
CELL="Seyda Neen, Fargoth's House"
CANDIDATES=(CELL,"Seyda Neen, Indrele Rathryon's Shack","Seyda Neen, Fine-Mouth's Shack","Balmora, Caius Cosades' House")
def run(installation):
    reports=source.inspect(installation,CANDIDATES)
    selected=next(c for c in reports if c['cell']==CELL)
    models=[m for m in selected['models'] if m['model']!='meshes/marker_north.nif']
    for m in models:
        if m.get('layout_error') or m.get('error'):raise ValueError('Incomplete layout '+m['model'])
        for feature in m['visible_features']:
            if not feature['normals'] or feature['zero_normals'] or feature['uv_sets']!=1 or feature['degenerate_triangles']:
                raise ValueError('Visible geometry incompatible: '+m['model'])
            props=feature['properties']
            if set(props)-{'NiMaterialProperty','NiTexturingProperty','NiVertexColorProperty','NiAlphaProperty','NiZBufferProperty','NiStencilProperty','NiSpecularProperty'}:
                raise ValueError('New property type needs review '+m['model'])
            if any(props.get('NiMaterialProperty',{}).get('emissive',(0,0,0))):raise ValueError('Emission needs review')
            texture=props.get('NiTexturingProperty')
            if not texture or texture['apply_mode'] not in (2,3):raise ValueError('Texture mode needs review')
            enabled=[i for i,t in enumerate(texture['textures']) if t['enabled']]
            if enabled!=[0] or texture['textures'][0]['uv_set']!=0:raise ValueError('Texture layers need review')
    archive=installation/'Data Files/Morrowind.bsa'
    entries={n:(o,s) for n,o,s in source.assets.old.bsa_entries(archive)}
    images={}
    with archive.open('rb') as stream:
        for name in sorted({t for m in models for t in m['visible_textures']}):
            key=name.replace('\\','/').lower()
            if not key.startswith('textures/'):key='textures/'+key
            choices=['meshes/'+str(Path(key).with_suffix('.dds')).replace('\\','/'),'meshes/'+key]
            resolved=next((k for k in choices if k in entries),None)
            if resolved is None:raise ValueError('Missing original texture '+name)
            offset,n=entries[resolved];stream.seek(offset);data=stream.read(n)
            if not data.startswith(b'DDS '):raise ValueError('Non-DDS needs explicit diagnostic extension')
            height,width=struct.unpack_from('<II',data,12);fourcc=data[84:88].decode('ascii')
            if not 0<width<=4096 or not 0<height<=4096 or fourcc not in ('DXT1','DXT3','DXT5'):raise ValueError('DDS dimensions/format need review')
            images[resolved.removeprefix('meshes/')]=dict(width=width,height=height,fourcc=fourcc,bytes=n,sha256=hashlib.sha256(data).hexdigest())
    objects,cells=source.scan(installation/'Data Files/Morrowind.esm')
    cell=next(c for c in cells if c[0]==CELL)
    lights=[]
    for r in cell[2]:
        obj=objects[source.string(r[b'NAME']).lower()]
        if obj['type']=='LIGH':
            weight,value,time,radius,color,flags=struct.unpack('<fiiiIi',obj['light'])
            lights.append({'id':source.string(r[b'NAME']),'radius':radius,'color':color,'flags':flags,
                'negative':bool(flags&4),'time_varying_frozen':bool(flags&(8|64|128|256)),'modelled':bool(obj['model'])})
    return {'scope':'read-only diagnostic layout; genuine native parsing and rendering UNVERIFIED',
        'candidates':[{'cell':c['cell'],'references':c['references'],'types':c['types'],'unique_models':c['unique_models'],
                       'incomplete_layout_models':sum('layout_error' in m for m in c['models'])} for c in reports],
        'selected':CELL,'references':selected['references'],'instances':sum(m['instances'] for m in models),'unique_models':len(models),
        'vertices':sum(m['vertices']*m['instances'] for m in models),'triangles':sum(m['triangles']*m['instances'] for m in models),
        'shapes':sum(m['shapes']*m['instances'] for m in models),
        'particle_branches_omitted':sum(m['particle_branches']*m['instances'] for m in models),
        'collision_branches_excluded':sum(m['collision_branches']*m['instances'] for m in models),
        'unique_textures':len(images),'decoded_rgba_bytes':sum(i['width']*i['height']*4 for i in images.values()),
        'cell_ambient_rgb':[v/255 for v in cell[1][b'AMBI'][:3]],'lights':lights,
        'models':[{k:m[k] for k in ('model','instances','vertices','triangles','shapes','sha256')} for m in models],
        'textures':images,'original_input_sha256':{n:source.assets.sha(installation/'Data Files'/n) for n in ('Morrowind.esm','Morrowind.bsa')},
        'private_bytes_exported':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--installation',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.installation),indent=2))
