"""Read-only original asset inspection and private, local-only transfer bundle."""
import argparse,hashlib,importlib.util,json,shutil,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
spec=importlib.util.spec_from_file_location('_private_metadata',REPO/'experiments/ios-openmw-nif-smoke/tools/inspect_private_assets.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
MODEL='meshes/f/furn_rug_02.nif'
OBJECT='furn_de_rug_02'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def inspect(installation):
    data=installation/'Data Files';archive=data/'Morrowind.bsa'
    entries={n:(o,s) for n,o,s in old.bsa_entries(archive)}
    off,size=entries[MODEL]
    with archive.open('rb') as f:f.seek(off);model=f.read(size)
    # Diagnostic only; genuine production parsing is Nif::Reader in StaticModel.cpp.
    import re
    textures=[x.decode('cp1252') for x in re.findall(rb'[A-Za-z0-9_\\/.-]+\.(?:tga|dds|bmp)',model,re.I)]
    records={t:model.count(struct.pack('<I',len(t))+t.encode()) for t in ('NiNode','NiTriShape','NiTriShapeData','NiMaterialProperty','NiTexturingProperty','NiSourceTexture')}
    pos=model.index(struct.pack('<I',14)+b'NiTriShapeData')+18
    def read(fmt):
        nonlocal pos
        v=struct.unpack_from('<'+fmt,model,pos);pos+=struct.calcsize('<'+fmt);return v[0]
    vertices=read('H');has_vertices=read('I');pos+=vertices*12 if has_vertices else 0
    normals=read('I');pos+=vertices*12 if normals else 0
    pos+=16;colors=read('I');pos+=vertices*16 if colors else 0
    uv_sets=read('H');has_uv=read('I');pos+=vertices*8*uv_sets if has_uv else 0
    triangles=read('H');indices=read('I')
    tag=b'NiMaterialProperty';mp=model.index(struct.pack('<I',len(tag))+tag)+4+len(tag)
    name_size=struct.unpack_from('<I',model,mp)[0];mp+=4+name_size+8+2
    material=struct.unpack_from('<14f',model,mp)
    dependencies=[]
    for name in textures:
        key=name.replace('\\','/').lower()
        if not key.startswith('textures/'):key='textures/'+key
        # Legacy metadata inspector prefixes all names with meshes/. Undo only
        # for texture lookup; production uses the genuine OpenMW path helper.
        choices=['meshes/'+str(Path(key).with_suffix('.dds')).replace('\\','/'),'meshes/'+key]
        selected=next((n for n in choices if n in entries),None)
        if selected is None:raise ValueError('Texture missing from base archive: '+name)
        pos,count=entries[selected]
        with archive.open('rb') as f:f.seek(pos);image=f.read(count)
        info={'reference':name,'resource':selected.removeprefix('meshes/'),'bytes':count,'sha256':hashlib.sha256(image).hexdigest()}
        if image.startswith(b'DDS '):info.update(width=struct.unpack_from('<I',image,16)[0],height=struct.unpack_from('<I',image,12)[0],fourcc=image[84:88].decode('ascii'))
        dependencies.append(info)
    refs=old.stat_models(data/'Morrowind.esm')
    if OBJECT not in refs[MODEL]:raise ValueError('Original STAT association differs')
    return {'object_id':OBJECT,'model':MODEL,'bytes':size,'sha256':hashlib.sha256(model).hexdigest(),
            'record_type_occurrences_diagnostic_only':records,'geometry_diagnostic_only':dict(vertices=vertices,triangles=triangles,index_count=indices,uv_sets=uv_sets,normals=bool(normals)),'textures':dependencies,
            'material_diagnostic_only':{'diffuse':material[3:6],'specular':material[6:9],'emissive':material[9:12],'gloss':material[12],'alpha':material[13]},
            'native_parse':'UNVERIFIED until genuine host runner executes'}
def export(installation,output):
    output=output.resolve();installation=installation.resolve()
    if output.is_relative_to(REPO) or output.is_relative_to(installation) or installation.is_relative_to(output):
        raise ValueError('Private output must be outside repository and installation')
    if output.exists():raise ValueError('Refusing to overwrite a private bundle')
    report=inspect(installation);before={n:sha(installation/'Data Files'/n) for n in ('Morrowind.esm','Morrowind.bsa')}
    output.mkdir(parents=True)
    for n in before:
        shutil.copyfile(installation/'Data Files'/n,output/n)
        if sha(output/n)!=before[n] or sha(installation/'Data Files'/n)!=before[n]:raise ValueError('Copy/input integrity failure')
    manifest={'schema_version':1,'object_id':OBJECT,'files':before,'model_inspection':report,'private':True}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'output':str(output),'source_and_copy_hashes_verified':True,'private':True}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--installation',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();print(json.dumps(export(a.installation,a.output) if a.output else inspect(a.installation),indent=2))
