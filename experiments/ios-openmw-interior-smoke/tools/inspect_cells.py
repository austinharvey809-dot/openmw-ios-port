"""Private read-only TES3 cell metadata diagnostics; production uses ESM::Cell.

Never writes original ESM/BSA/NIF/texture bytes or original placement arrays.
"""
import argparse, collections, hashlib, importlib.util, json, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
OLD=REPO/'experiments/ios-openmw-nif-render-smoke/real-model/tools'
sys.path.insert(0,str(OLD))
import assets,nif_layout
sys.path.insert(0,str(ROOT/'tools'))
import layout as nif_layout

def string(value):return value.split(b'\0',1)[0].decode('cp1252')
def records(path):
    with path.open('rb') as f:
        size=path.stat().st_size
        while f.tell()<size:
            head=f.read(16)
            if len(head)!=16:raise ValueError('Truncated ESM header')
            kind,length,unknown,flags=struct.unpack('<4sIII',head)
            if length>size-f.tell():raise ValueError('ESM record exceeds file')
            payload=f.read(length);pos=0;subs=[]
            while pos<len(payload):
                if len(payload)-pos<8:raise ValueError('Truncated subrecord')
                tag,n=struct.unpack_from('<4sI',payload,pos);pos+=8
                if n>len(payload)-pos:raise ValueError('Subrecord exceeds record')
                subs.append((tag,payload[pos:pos+n]));pos+=n
            yield kind,subs

def scan(path):
    objects={};cells=[]
    for kind,subs in records(path):
        if kind==b'CELL':
            header={};refs=[];ref=None
            for tag,value in subs:
                if tag==b'FRMR':
                    ref={};refs.append(ref)
                if ref is None:header[tag]=value
                else:ref[tag]=value
            if b'DATA' in header and struct.unpack_from('<I',header[b'DATA'])[0]&1:
                cells.append((string(header.get(b'NAME',b'')),header,refs))
        elif kind in (b'STAT',b'ACTI',b'CONT',b'MISC',b'DOOR',b'LIGH',b'NPC_',b'CREA',b'BOOK',b'INGR',b'ALCH',b'APPA',b'PROB',b'LOCK',b'REPA',b'ARMO',b'CLOT',b'WEAP'):
            values=dict(subs)
            if b'NAME' in values:
                objects[string(values[b'NAME']).lower()]={'type':kind.decode('ascii'),'model':string(values.get(b'MODL',b'')),
                    'light':values.get(b'LHDT'), 'deleted':b'DELE' in values}
    return objects,cells

def visible(layout):
    records=layout['records'];nodes=[];effects=collision=0;active=set()
    def visit(index,state):
        nonlocal effects,collision
        if index in active:raise ValueError('Cyclic diagnostic hierarchy')
        active.add(index);r=records[index]
        if r['type']=='RootCollisionNode':collision+=1
        elif r['type']=='NiBSParticleNode':effects+=1
        elif not r.get('flags',0)&1:
            state=dict(state)
            for prop in r.get('properties',[]):state[records[prop]['type']]=records[prop]
            if r['type']=='NiTriShape':nodes.append((r,records[r['data']],state))
            for child in r.get('children',[]):
                if child>=0:visit(child,state)
        active.remove(index)
    for index in layout['roots']:visit(index,{})
    return nodes,collision,effects

def inspect(installation,names):
    directory=installation/'Data Files';objects,cells=scan(directory/'Morrowind.esm')
    selected=[c for c in cells if c[0] in names]
    archive=directory/'Morrowind.bsa';entries={n:(o,s) for n,o,s in assets.old.bsa_entries(archive)}
    reports=[]
    with archive.open('rb') as f:
        for name,header,refs in selected:
            types=collections.Counter();models={};missing=[]
            for ref in refs:
                if b'DELE' in ref:continue
                key=string(ref.get(b'NAME',b'')).lower();base=objects.get(key)
                if base is None:missing.append(key);continue
                types[base['type']]+=1
                if base['model']:
                    resource=assets.old.normalize_model(base['model'].encode('cp1252'))
                    models.setdefault(resource,[]).append(base['type'])
            detail=[]
            for resource,uses in sorted(models.items()):
                item={'model':resource,'instances':len(uses),'types':sorted(set(uses))}
                if resource not in entries:item['error']='Missing BSA resource'
                else:
                    offset,n=entries[resource];f.seek(offset);data=f.read(n)
                    item.update(bytes=n,sha256=hashlib.sha256(data).hexdigest())
                    try:
                        layout=nif_layout.inspect(data)
                        nodes,collision,effects=visible(layout)
                        geometry=[g for r,g,p in nodes]
                        item.update(vertices=sum(r['vertices'] for r in geometry),triangles=sum(r['triangles'] for r in geometry),
                            shapes=len(geometry),collision_branches=collision,particle_branches=effects,
                            visible_textures=sorted({layout['records'][slot['source']]['file']
                                for node,g,props in nodes for slot in props.get('NiTexturingProperty',{}).get('textures',[]) if slot['enabled']}),
                            visible_features=[{'vertex_colors':g['vertex_colors'],'normals':g['normals'],'zero_normals':g['zero_normals'],'uv_sets':g['uv_sets'],
                                'degenerate_triangles':g['degenerate_triangles'],
                                'properties':{k:{f:v for f,v in p.items() if f not in ('offset','references','name')} for k,p in props.items()}}
                                for r,g,props in nodes],
                            record_types=dict(collections.Counter(r['type'] for r in layout['records'])),
                            properties=[{k:v for k,v in r.items() if k not in ('references','offset','name')}
                                for r in layout['records'] if r['type'].endswith('Property')],
                            textures=[r['file'] for r in layout['records'] if r['type']=='NiSourceTexture'])
                    except ValueError as e:
                        # Still report the first unsupported layout, never pretend full inventory.
                        item['layout_error']=str(e)
                detail.append(item)
            reports.append({'cell':name,'references':len(refs),'types':dict(types),'unique_models':len(models),
                            'missing_base_ids':missing,'models':detail})
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--installation',type=Path,required=True);p.add_argument('--cell',action='append',default=[])
    a=p.parse_args()
    if a.cell:print(json.dumps(inspect(a.installation,a.cell),indent=2))
    else:
        objects,cells=scan(a.installation/'Data Files/Morrowind.esm')
        values=[]
        for name,header,refs in cells:
            if not refs:continue
            types=collections.Counter(objects.get(string(r.get(b'NAME',b'')).lower(),{}).get('type','UNKNOWN') for r in refs)
            if name.startswith(('Seyda Neen,','Balmora,','Pelagiad,')):
                values.append({'cell':name,'refs':len(refs),'types':dict(types)})
        print(json.dumps(sorted(values,key=lambda x:x['refs'])[:45],indent=2))
