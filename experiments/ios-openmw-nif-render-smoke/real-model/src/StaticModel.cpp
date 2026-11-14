#include "StaticModel.hpp"
#include "StaticProperties.hpp"
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/nif/node.hpp>
#include <components/nif/data.hpp>
#include <components/nif/property.hpp>
#include <components/nif/texture.hpp>
#include <components/misc/resourcehelpers.hpp>
#include <components/resource/objectcache.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <osg/MatrixTransform>
#include <osg/FrontFace>
#include <osg/Texture2D>
#include <osg/Uniform>
#include <osgDB/Registry>
#include <osgDB/Options>
#include <cmath>
#include <functional>
#include <set>
#include <stdexcept>
USE_OSGPLUGIN(tga)
USE_OSGPLUGIN(dds)
namespace G1D {
namespace {
void require(bool b,const char* s){if(!b)throw std::runtime_error(s);}
void safe(const std::string& s){require(!s.empty()&&s[0]!='/'&&s[0]!='\\'&&s.find(':')==s.npos&&s.find('\0')==s.npos,"Unsafe texture path");
 std::string part; for(char c:s+'/'){if(c=='/'||c=='\\'){require(!part.empty()&&part!=".."&&part!=".","Unsafe path segment");part.clear();}else part+=c;}}
}
Model load(const std::filesystem::path& directory,const std::string& objectId){
 require(!std::filesystem::is_symlink(directory)&&std::filesystem::is_directory(directory),"Missing model directory");
 for(const auto& n:{"Morrowind.esm","Morrowind.bsa"}) require(std::filesystem::is_regular_file(std::filesystem::symlink_status(directory/n)),"Missing/nonregular private input");
 ToUTF8::Utf8Encoder encoder(ToUTF8::WINDOWS_1252);
 ToUTF8::StatelessUtf8Encoder archiveEncoder(ToUTF8::WINDOWS_1252);
 ESM::ESMReader esm;esm.setEncoder(&encoder);esm.open(directory/"Morrowind.esm");
 std::string model; bool found=false;
 while(esm.hasMoreRecs()){auto type=esm.getRecName();esm.getRecHeader();if(type!="STAT"){esm.skipRecord();continue;}
 ESM::Static stat;bool deleted=false;stat.load(esm,deleted);if(!deleted&&stat.mId.getRefIdString()==objectId){require(!found,"Duplicate STAT");model=stat.mModel.getOriginal();found=true;}}
 require(found&&!model.empty(),"Selected original STAT missing");safe(model);
 VFS::Manager vfs;OpenMWIOSBsaVfs::addExistingMorrowindBSA(vfs,directory/"Morrowind.bsa",archiveEncoder);vfs.buildIndex();
 auto key=VFS::Path::join(VFS::Path::NormalizedView("meshes"),VFS::Path::Normalized(model));
 Nif::NIFFile file(key);Nif::Reader reader(file,&archiveEncoder);reader.parse(vfs.get(key));
 require(file.mVersion==Nif::NIFFile::VER_MW&&!file.mRoots.empty(),"Expected MW NIF");
 Resource::GenericObjectCache<std::string,osg::ref_ptr<osg::Image>> cache;
 Model result;result.resourceKey=std::string(key.value());result.scene=new osg::Group;std::set<const Nif::NiAVObject*> visiting;unsigned visits=0;
 std::function<osg::ref_ptr<osg::Node>(const Nif::NiAVObject*,StaticProperties,osg::Matrix)> visit;
 visit=[&](const Nif::NiAVObject* source,StaticProperties material,osg::Matrix parent)->osg::ref_ptr<osg::Node>{
 require(source&&visiting.size()<256&&++visits<=10000&&visiting.insert(source).second,"Cyclic/oversized hierarchy");
 const std::string context=source->mRecordName+"#"+std::to_string(source->mRecordIndex)+"["+source->mName+"]";
 std::string stage="hierarchy";const Nif::NiProperty* processing=nullptr;
 try {
 require(source->mController.empty(),"Animated models are not supported");
 osg::ref_ptr<osg::MatrixTransform> node=new osg::MatrixTransform;
 const auto matrix=source->mTransform.toMatrix();for(unsigned a=0;a<4;++a)for(unsigned b=0;b<4;++b)require(std::isfinite(matrix(a,b)),"Nonfinite transform");
 node->setMatrix(matrix);auto world=osg::Matrix(matrix)*parent;
 if(source->mFlags&Nif::NiAVObject::Flag_Hidden){visiting.erase(source);return node;}
 stage="properties";
 for(const auto& p:source->mProperties)inheritProperty(material,p.empty()?nullptr:p.getPtr(),context);
 stage="node-dispatch";
 if(auto* branch=dynamic_cast<const Nif::NiNode*>(source)){
 require(source->mRecordType==Nif::RC_NiNode,"Specialized node unsupported");for(const auto& c:branch->mChildren)if(!c.empty())node->addChild(visit(c.getPtr(),material,world));
 }else if(auto* shape=dynamic_cast<const Nif::NiTriShape*>(source)){
 stage="geometry";
 require(shape->mSkin.empty()&&!shape->mData.empty(),"Skinned/missing geometry unsupported");
 auto* data=dynamic_cast<const Nif::NiTriShapeData*>(shape->mData.getPtr());
 require(data&&data->mVertices.size()>=3&&data->mVertices.size()==data->mNumVertices&&data->mTriangles.size()==3u*data->mNumTriangles&&data->mNumTriangles>0,"Invalid triangle arrays");
 require(data->mVertices.size()<=1000000&&data->mUVList.size()==1&&data->mUVList[0].size()==data->mVertices.size(),"Invalid UV/vertex inventory");
 for(const auto& v:data->mVertices)for(unsigned i=0;i<3;++i)require(std::isfinite(v[i]),"Nonfinite vertex");
 for(const auto& uv:data->mUVList[0])for(unsigned i=0;i<2;++i)require(std::isfinite(uv[i]),"Nonfinite UV");
 for(auto i:data->mTriangles)require(i<data->mVertices.size(),"Index out of range");
 for(unsigned i=0;i<data->mTriangles.size();i+=3){auto a=data->mTriangles[i],b=data->mTriangles[i+1],c=data->mTriangles[i+2];require(a!=b&&a!=c&&b!=c,"Repeated triangle index");osg::Vec3d x(data->mVertices[a]),y(data->mVertices[b]),z(data->mVertices[c]);double area=((y-x)^(z-x)).length2();require(std::isfinite(area)&&area>0,"Degenerate triangle");}
 stage="texture-binding";processing=material.texture;
 // OpenMW's MW Hilight path uses the ordinary modulated diffuse map.
 require(material.texture&&(material.texture->mApplyMode==Nif::NiTexturingProperty::ApplyMode::Modulate
     ||material.texture->mApplyMode==Nif::NiTexturingProperty::ApplyMode::Hilight),"Missing/unsupported texture treatment");
 const auto& slots=material.texture->mTextures;require(!slots.empty()&&slots[0].mEnabled&&!slots[0].mSourceTexture.empty(),"Missing base texture");
 for(unsigned i=1;i<slots.size();++i)require(!slots[i].mEnabled,"Additional texture layer unsupported");
 const auto& slot=slots[0];require(slot.mClamp<=3&&slot.mFilter<=5,"Invalid/unsupported texture sampler");require(slot.mUVSet==0&&!slot.mHasTransform,"Texture transform unsupported");
 auto* tex=slot.mSourceTexture.getPtr();require(tex->mExternal,"Embedded texture unsupported");safe(tex->mFile);
 auto textureKey=Misc::ResourceHelpers::correctTexturePath(VFS::Path::Normalized(tex->mFile),vfs);
 std::string name(textureKey.value());result.textureKeys.push_back(name);auto image=cache.getRefFromObjectCache(name);
 stage="image-decode";
 if(!image){auto ext=std::string(textureKey.extension().value());require(ext=="dds"||ext=="tga","Unsupported image type");
 auto* decoder=osgDB::Registry::instance()->getReaderWriterForExtension(ext);require(decoder,"Static image decoder missing");auto stream=vfs.get(textureKey);
 osg::ref_ptr<osgDB::Options> options=new osgDB::Options("dds_dxt1_detect_rgba ignoreTga2Fields");auto decoded=decoder->readImage(*stream,options);require(decoded.success()&&decoded.getImage(),"Image decode failed");
 auto* original=decoded.getImage();require(original->s()>0&&original->t()>0&&original->s()<=4096&&original->t()<=4096&&original->r()==1,"Image dimensions rejected");
 auto format=original->getPixelFormat();require(!original->isCompressed()||format==GL_COMPRESSED_RGB_S3TC_DXT1_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT1_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT3_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT5_EXT,"Unsupported compressed DDS format");
 // Same getColor/setColor CPU decompression mechanism as OpenMW ImageManager;
 // upload ordinary RGBA, never assume BC/S3TC support on iPhone Metal.
 image=new osg::Image;image->allocateImage(original->s(),original->t(),1,GL_RGBA,GL_UNSIGNED_BYTE);image->setOrigin(original->getOrigin());
 for(int y=0;y<original->t();++y)for(int x=0;x<original->s();++x)image->setColor(original->getColor(x,y),x,y);
 if(ext=="dds")image->setOrigin(osg::Image::TOP_LEFT);
 else if(image->getOrigin()==osg::Image::BOTTOM_LEFT){image->flipVertical();image->setOrigin(osg::Image::TOP_LEFT);}
 cache.addEntryToObjectCache(name,image);}
 osg::ref_ptr<osg::Geometry> drawable=new osg::Geometry;
 osg::ref_ptr<osg::Vec3Array> positions=new osg::Vec3Array;positions->assign(data->mVertices.begin(),data->mVertices.end());drawable->setVertexArray(positions);
 osg::ref_ptr<osg::Vec2Array> uv=new osg::Vec2Array;uv->assign(data->mUVList[0].begin(),data->mUVList[0].end());drawable->setVertexAttribArray(6,uv,osg::Array::BIND_PER_VERTEX);
 stage="material-colors";processing=material.vertex;
 const auto diffuse=diffuseColor(material,!data->mColors.empty(),context);
 const bool useColors=!material.vertex||material.vertex->mVertexMode==Nif::NiVertexColorProperty::VertexMode::VertMode_SrcAmbDif;
 require(data->mColors.empty()||data->mColors.size()==data->mVertices.size(),"Invalid vertex color inventory");
 for(const auto& color:data->mColors)for(unsigned i=0;i<4;++i)require(std::isfinite(color[i])&&color[i]>=0&&color[i]<=1,"Invalid vertex color");
 osg::ref_ptr<osg::Vec4Array> colors=new osg::Vec4Array;
 if(useColors&&!data->mColors.empty())colors->assign(data->mColors.begin(),data->mColors.end());
 else colors->assign(data->mVertices.size(),diffuse);
 drawable->setColorArray(colors,osg::Array::BIND_PER_VERTEX);
 if(!data->mNormals.empty()){require(data->mNormals.size()==data->mVertices.size(),"Invalid normals");osg::ref_ptr<osg::Vec3Array> normals=new osg::Vec3Array;normals->assign(data->mNormals.begin(),data->mNormals.end());drawable->setNormalArray(normals,osg::Array::BIND_PER_VERTEX);}
 osg::ref_ptr<osg::DrawElementsUShort> indices=new osg::DrawElementsUShort(GL_TRIANGLES);indices->assign(data->mTriangles.begin(),data->mTriangles.end());drawable->addPrimitiveSet(indices);
 drawable->setUseDisplayList(false);drawable->setUseVertexBufferObjects(true);drawable->setUseVertexArrayObject(true);
 osg::ref_ptr<osg::Geode> geode=new osg::Geode;geode->addDrawable(drawable);auto* state=geode->getOrCreateStateSet();
 stage="osg-state";processing=material.texture;
 osg::ref_ptr<osg::Texture2D> texture=new osg::Texture2D(image);
 const osg::Texture::FilterMode filters[]={osg::Texture::NEAREST,osg::Texture::LINEAR,osg::Texture::LINEAR_MIPMAP_LINEAR,osg::Texture::NEAREST_MIPMAP_NEAREST,osg::Texture::NEAREST_MIPMAP_LINEAR,osg::Texture::LINEAR_MIPMAP_NEAREST};
 texture->setFilter(osg::Texture::MIN_FILTER,filters[slot.mFilter]);
 texture->setFilter(osg::Texture::MAG_FILTER,slot.mFilter==0||slot.mFilter==3||slot.mFilter==4?osg::Texture::NEAREST:osg::Texture::LINEAR);
 texture->setWrap(osg::Texture::WRAP_S,slot.wrapS()?osg::Texture::REPEAT:osg::Texture::CLAMP_TO_EDGE);texture->setWrap(osg::Texture::WRAP_T,slot.wrapT()?osg::Texture::REPEAT:osg::Texture::CLAMP_TO_EDGE);
 // CPU RGBA expansion discards source DDS mips (as in ImageManager). Generate
 // the RGBA mip chain when the genuine sampler asks for mip filtering.
 texture->setUseHardwareMipMapGeneration(slot.mFilter>=2);state->setTextureAttribute(0,texture);state->addUniform(new osg::Uniform("baseTexture",0));
 double det=world(0,0)*(world(1,1)*world(2,2)-world(1,2)*world(2,1))-world(0,1)*(world(1,0)*world(2,2)-world(1,2)*world(2,0))+world(0,2)*(world(1,0)*world(2,1)-world(1,1)*world(2,0));
 require(std::isfinite(det)&&det!=0,"Singular transform");applyStaticState(*state,material,det);
 node->addChild(geode);result.vertices+=data->mVertices.size();result.triangles+=data->mNumTriangles;++result.shapes;
 }else throw std::runtime_error("Unsupported scene node");
 visiting.erase(source);return node;
 }catch(const std::exception& e){
 if(std::string(e.what()).starts_with("G1D stage="))throw;
 throw std::runtime_error("G1D stage="+stage+" node="+context+" property="
     +(processing?processing->mRecordName+"#"+std::to_string(processing->mRecordIndex):"<none>")+": "+e.what());
 }};
 for(auto* root:file.mRoots){auto* av=dynamic_cast<Nif::NiAVObject*>(root);result.scene->addChild(visit(av,{},osg::Matrix::identity()));}
 require(result.shapes>0,"No renderable geometry");return result;
}
}
