"""Private read-only exterior metadata; never exports game records or resources."""
import argparse,collections,hashlib,json,math,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'ios-openmw-interior-smoke/tools'))
import inspect_cells as old

def heights(data):
    if len(data)!=4+65*65+3:raise ValueError('Invalid VHGT size')
    row=struct.unpack_from('<f',data)[0];values=[]
    if not math.isfinite(row):raise ValueError('Nonfinite VHGT offset')
    deltas=struct.unpack_from('<4225b',data,4)
    for y in range(65):
        row+=deltas[y*65];current=row;values.append(current*8)
        for x in range(1,65):current+=deltas[y*65+x];values.append(current*8)
    return values

def tile_indices(data):
    if len(data)!=512:raise ValueError('Invalid VTEX size')
    source=iter(struct.unpack('<256H',data));out=[0]*256
    for y1 in range(4):
        for x1 in range(4):
            for y2 in range(4):
                for x2 in range(4):out[(y1*4+y2)*16+x1*4+x2]=next(source)
    return out

def scan(path):
    objects,_=old.scan(path);cells={};lands={};textures={};doors=[]
    for kind,subs in old.records(path):
        fields=dict(subs)
        if kind==b'LTEX':textures[struct.unpack('<I',fields[b'INTV'])[0]]=old.string(fields[b'DATA'])
        elif kind==b'LAND':lands[struct.unpack('<ii',fields[b'INTV'])]=fields
        elif kind==b'CELL':
            header={};refs=[];ref=None
            for tag,value in subs:
                if tag==b'FRMR':ref={};refs.append(ref)
                (header if ref is None else ref)[tag]=value
            flags,x,y=struct.unpack('<Iii',header[b'DATA'])
            if not flags&1:cells[x,y]=(old.string(header.get(b'NAME',b'')),header,refs)
            elif old.string(header.get(b'NAME',b''))=="Seyda Neen, Fargoth's House":
                for r in refs:
                    if b'DODT' in r:doors.append({'destination':old.string(r.get(b'DNAM',b'')),'position':struct.unpack('<6f',r[b'DODT'])})
    return objects,cells,lands,textures,doors

def inspect(installation,center=(-2,-9),radius=1):
    objects,cells,lands,textures,doors=scan(installation/'Data Files/Morrowind.esm')
    archive=installation/'Data Files/Morrowind.bsa';entries={n:(o,s) for n,o,s in old.assets.old.bsa_entries(archive)}
    models=collections.Counter();types=collections.Counter();summary=[];landtextures=set()
    for key,cell in sorted(cells.items()):
        if abs(key[0]-center[0])>radius or abs(key[1]-center[1])>radius:continue
        count=collections.Counter();land=lands.get(key)
        for r in cell[2]:
            if b'DELE' in r:continue
            b=objects.get(old.string(r.get(b'NAME',b'')).lower(),{})
            count[b.get('type','UNKNOWN')]+=1
            if b.get('model') and b.get('type') in ('STAT','ACTI','CONT','DOOR','MISC','LIGH'):
                models[old.assets.old.normalize_model(b['model'].encode('cp1252'))]+=1
        types.update(count)
        if land and b'VTEX' in land:landtextures.update(struct.unpack('<256H',land[b'VTEX']))
        summary.append({'grid':key,'name':cell[0],'references':len(cell[2]),'types':dict(count),'land':land is not None})
    details=[];resources=set();coverage=[]
    with archive.open('rb') as stream:
        for name,count in sorted(models.items()):
            item={'model':name,'instances':count}
            try:
                offset,n=entries[name];stream.seek(offset);data=stream.read(n)
                layout=old.nif_layout.inspect(data);nodes,collision,effects=old.visible(layout)
                item.update(vertices=sum(g['vertices'] for _,g,_ in nodes),triangles=sum(g['triangles'] for _,g,_ in nodes),shapes=len(nodes),
                    collision_branches=collision,particle_branches=effects,types=dict(collections.Counter(r['type'] for r in layout['records'])),
                    properties=sorted({p for _,_,state in nodes for p in state}),
                    controllers=sum(r['type'].endswith('Controller') for r in layout['records']),
                    colors=sum(g['vertex_colors'] for _,g,_ in nodes),
                    zero_normals=sum(g['zero_normals'] for _,g,_ in nodes),
                    uv_sets=sorted({g['uv_sets'] for _,g,_ in nodes}),
                    degenerate_triangles=sum(g['degenerate_triangles'] for _,g,_ in nodes),
                    sha256=hashlib.sha256(data).hexdigest())
                resources.update(r['file'] for r in layout['records'] if r['type']=='NiSourceTexture')
                if name not in {'meshes/editormarker.nif','meshes/editormarker_box_01.nif','meshes/marker_prison.nif','meshes/marker_north.nif'}:
                    for node,g,state in nodes:
                        if not g['normals'] or g['zero_normals'] or g['uv_sets']!=1 or g['degenerate_triangles']:coverage.append({'model':name,'issue':'geometry inventory'})
                        if set(state)-{'NiMaterialProperty','NiTexturingProperty','NiVertexColorProperty','NiAlphaProperty','NiZBufferProperty','NiStencilProperty','NiSpecularProperty','NiShadeProperty','NiWireframeProperty'}:coverage.append({'model':name,'issue':'property type'})
                        material=state.get('NiMaterialProperty',{})
                        if any(material.get('emissive',(0,0,0))):coverage.append({'model':name,'issue':'emissive material'})
                        texture=state.get('NiTexturingProperty',{})
                        if texture.get('apply_mode') not in (2,3):coverage.append({'model':name,'issue':'texture apply mode'})
                        enabled=[i for i,t in enumerate(texture.get('textures',[])) if t['enabled']]
                        if enabled!=[0]:coverage.append({'model':name,'issue':'texture slots'})
            except (ValueError,KeyError) as error:item['diagnostic_error']=str(error)
            details.append(item)
    sampled=set()
    for cx in range(center[0]-radius,center[0]+radius+1):
        for cy in range(center[1]-radius,center[1]+radius+1):
            for x in range(17):
                for y in range(17):
                    gx=cx*16-1+x;gy=cy*16+y
                    sampled.add(tile_indices(lands[gx//16,gy//16][b'VTEX'])[(gy%16)*16+gx%16])
    images={}
    with archive.open('rb') as stream:
        for name in resources|{textures[i-1] for i in sampled if i}:
            key=name.lower().replace('\\','/')
            if not key.startswith('textures/'):key='textures/'+key
            choices=['meshes/'+str(Path(key).with_suffix('.dds')).replace('\\','/'),'meshes/'+key]
            resolved=next((k for k in choices if k in entries),None)
            if not resolved:raise ValueError('Missing texture '+name)
            off,n=entries[resolved];stream.seek(off);header=stream.read(128)
            if header[:4]!=b'DDS ':raise ValueError('Non-DDS '+name)
            h,w=struct.unpack_from('<II',header,12);images[resolved]={'width':w,'height':h,'fourcc':header[84:88].decode('ascii'),'bytes':n}
    terrain={};seams=[];zeroNormals=0;haloIDs=set()
    for (x,y),fields in lands.items():
        if center[0]-radius-1<=x<=center[0]+radius+1 and center[1]-radius-1<=y<=center[1]+radius+1:
            haloIDs.update(tile_indices(fields[b'VTEX']))
        if abs(x-center[0])>radius or abs(y-center[1])>radius:continue
        terrain[x,y]=heights(fields[b'VHGT']);normal=fields[b'VNML'];zeroNormals+=sum(normal[i:i+3]==b'\0\0\0' for i in range(0,len(normal),3))
    for (x,y),values in terrain.items():
        for neighbor,dx in (((x+1,y),True),((x,y+1),False)):
            if neighbor not in terrain:continue
            error=max(abs(values[i*65+64 if dx else 64*65+i]-terrain[neighbor][i*65 if dx else i]) for i in range(65))
            seams.append(error)
    return {'scope':'metadata diagnostic, not native parser/rendering acceptance','center':center,'radius':radius,'cells':summary,
        'types':dict(types),'models':details,'unique_models':len(details),
        'instanced_triangles':sum(m.get('triangles',0)*m['instances'] for m in details),
        'land_texture_indices':sorted(landtextures),'land_textures':{str(i):textures.get(i-1,'<default>' if i==0 else '<missing>') for i in sorted(landtextures)},
        'sampled_blend_texture_indices':sorted(sampled),
        'model_texture_count':len(resources),'textures':images,'decoded_rgba_bytes':sum(i['width']*i['height']*4 for i in images.values()),
        'terrain_height_range':[min(min(v) for v in terrain.values()),max(max(v) for v in terrain.values())],
        'maximum_height_seam_error':max(seams,default=0),'zero_land_normals':zeroNormals,'halo_texture_ids':sorted(haloIDs),
        'g2_adapter_findings':coverage,'g3_note':'Material emission is now supported; actual compatibility requires the genuine CPU harness',
        'fargoth_exit':doors,'private_bytes_exported':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--installation',type=Path,required=True);p.add_argument('--radius',type=int,default=1);p.add_argument('--output',type=Path);a=p.parse_args()
    data=json.dumps(inspect(a.installation,radius=a.radius),indent=2)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(data+'\n')
    else:print(data)
