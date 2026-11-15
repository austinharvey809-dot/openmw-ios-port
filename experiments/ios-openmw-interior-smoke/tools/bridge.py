"""Derive the accepted G1D converter without editing or duplicating its source.

Every edit has an exact anchor count; input hashes are locked. Generated output
is compiled in G2 only. CMake never generates replacements in an upstream tree.
"""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
BASE=REPO/'experiments/ios-openmw-nif-render-smoke/real-model'

def replace(source,old,new):
    if source.count(old)!=1:raise ValueError('G2 converter anchor differs: '+old[:70])
    return source.replace(old,new)

def generate(output):
    lock=json.loads((ROOT/'baseline-lock.json').read_text())
    for name,digest in lock['source_sha256_lf'].items():
        if hashlib.sha256((REPO/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise ValueError('Accepted source changed: '+name)
    code=(BASE/'src/StaticModel.cpp').read_text()
    code=replace(code,'#include "StaticModel.hpp"','#include "Interior.hpp"\n#include <components/nif/niffile.hpp>\n#include <osg/Geode>\n#include <osg/Geometry>')
    code=replace(code,'namespace G1D {','namespace G2 {\nusing G1D::StaticProperties;using G1D::inheritProperty;using G1D::diffuseColor;using G1D::applyStaticState;')
    start=code.index('Model load(');end=code.index(' Nif::NIFFile file',start)
    code=code[:start]+'''Model loadMesh(Resources& resources,const std::string& model){
 auto& archiveEncoder=resources.encoder;auto& vfs=resources.vfs;auto& cache=resources.images;
 safe(model);
 auto key=VFS::Path::join(VFS::Path::NormalizedView("meshes"),VFS::Path::Normalized(model));
'''+code[end:]
    code=replace(code,' Resource::GenericObjectCache<std::string,osg::ref_ptr<osg::Image>> cache;','')
    code=replace(code,' node->setMatrix(matrix);auto world=osg::Matrix(matrix)*parent;', ''' node->setMatrix(matrix);node->setName(source->mName);auto world=osg::Matrix(matrix)*parent;
 if(source->mName=="AttachLight"){
   require(!result.hasLightOffset,"Ambiguous AttachLight nodes");result.hasLightOffset=true;result.lightOffset=world.getTrans();
 }''')
    code=replace(code,' try {\n require(source->mController.empty()', ''' try {
 if(source->mRecordType==Nif::RC_RootCollisionNode){++result.collisionBranches;visiting.erase(source);return new osg::Group;}
 // Explicit static-environment limitation, surfaced in exported counters.
 // Candle bodies are outside these branches; no replacement flame is created.
 if(source->mRecordType==Nif::RC_NiBSParticleNode){++result.particleBranches;visiting.erase(source);return new osg::Group;}
 require(source->mController.empty()''')
    code=replace(code,' image=new osg::Image;image->allocateImage', ''' require(resources.decodedBytes+std::size_t(original->s())*original->t()*4<=64u*1024*1024,"Decoded texture budget exceeded");
 resources.decodedBytes+=std::size_t(original->s())*original->t()*4;
 image=new osg::Image;image->allocateImage''')
    # Lighting requires valid original normals, never invented normals/vertices.
    code=replace(code,' if(!data->mNormals.empty()){',' require(!data->mNormals.empty(),"G2 lighting requires original normals");\n if(!data->mNormals.empty()){')
    code=replace(code,'"Invalid normals");osg::ref_ptr', '"Invalid normals");for(const auto& n:data->mNormals){for(unsigned i=0;i<3;++i)require(std::isfinite(n[i]),"Nonfinite normal");require(n.length2()>0,"Zero normal");}osg::ref_ptr')
    code=replace(code,'osg::ref_ptr<osg::Texture2D> texture=new osg::Texture2D(image);',
        '''auto& texture=resources.samplers[std::make_tuple(name,slot.mClamp,slot.mFilter)];
 if(!texture){
 const std::size_t estimate=std::size_t(image->s())*image->t()*4*(slot.mFilter>=2?2:1);
 require(resources.samplerBytes+estimate<=128u*1024*1024,"Texture storage budget exceeded");resources.samplerBytes+=estimate;
 texture=new osg::Texture2D(image);''')
    code=replace(code,'texture->setUseHardwareMipMapGeneration(slot.mFilter>=2);state->setTextureAttribute',
        'texture->setUseHardwareMipMapGeneration(slot.mFilter>=2);}\n state->setTextureAttribute')
    # Property helper and scene conversion retain the accepted state semantics.
    output.mkdir(parents=True,exist_ok=True)
    (output/'MeshBridge.cpp').write_text(code,encoding='utf-8',newline='\n')
    return {'generated_sha256':hashlib.sha256(code.encode()).hexdigest(),'baseline':lock['accepted_g1d_commit']}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(generate(a.output)))
