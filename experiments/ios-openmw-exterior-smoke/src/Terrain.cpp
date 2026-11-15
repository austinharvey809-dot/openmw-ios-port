#include "Exterior.hpp"
#include "TerrainCoordinates.hpp"
#include <components/esmterrain/gridsampling.hpp>
#include <components/terrain/buffercache.hpp>
#include <components/misc/resourcehelpers.hpp>
#include <osg/BlendFunc>
#include <osg/Depth>
#include <osg/Geode>
#include <osg/Geometry>
#include <osg/Uniform>
#include <osgDB/Registry>
#include <osgDB/Options>
#include <BulletCollision/CollisionShapes/btTriangleMesh.h>
#include <cmath>
#include <set>
#include <stdexcept>
namespace G3 {
namespace {
void require(bool value,const std::string& message){if(!value)throw std::runtime_error("G3 LAND "+message);}
osg::ref_ptr<osg::Texture2D> image(G2::Resources& resources,const std::string& name){
    require(!name.empty()&&name.front()!='/'&&name.front()!='\\'&&name.find(':')==name.npos&&name.find('\0')==name.npos,"Unsafe terrain texture path");
    std::string segment;for(char c:name+'/'){
        if(c=='/'||c=='\\'){require(!segment.empty()&&segment!="."&&segment!="..","Unsafe terrain texture path");segment.clear();}
        else segment+=c;
    }
    auto key=Misc::ResourceHelpers::correctTexturePath(VFS::Path::Normalized(name),resources.vfs);
    const std::string path(key.value());auto decoded=resources.images.getRefFromObjectCache(path);
    if(!decoded){
        auto ext=std::string(key.extension().value());require(ext=="dds"||ext=="tga","Unsupported terrain image "+path);
        auto* reader=osgDB::Registry::instance()->getReaderWriterForExtension(ext);require(reader,"Missing terrain decoder");
        auto stream=resources.vfs.get(key);osg::ref_ptr<osgDB::Options> options=new osgDB::Options("dds_dxt1_detect_rgba ignoreTga2Fields");
        auto result=reader->readImage(*stream,options);require(result.success()&&result.getImage(),"Terrain image decode failed "+path);
        auto* original=result.getImage();require(original->s()>0&&original->t()>0&&original->s()<=4096&&original->t()<=4096&&original->r()==1,"Terrain dimensions");
        auto format=original->getPixelFormat();require(!original->isCompressed()||format==GL_COMPRESSED_RGB_S3TC_DXT1_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT1_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT3_EXT||format==GL_COMPRESSED_RGBA_S3TC_DXT5_EXT,"Unsupported DDS compression");
        auto bytes=std::size_t(original->s())*original->t()*4;
        require(resources.decodedBytes+bytes<=64u*1024*1024,"Decoded image budget");
        decoded=new osg::Image;decoded->allocateImage(original->s(),original->t(),1,GL_RGBA,GL_UNSIGNED_BYTE);
        for(int y=0;y<original->t();++y)for(int x=0;x<original->s();++x)decoded->setColor(original->getColor(x,y),x,y);
        decoded->setOrigin(original->getOrigin());
        if(ext=="dds")decoded->setOrigin(osg::Image::TOP_LEFT);
        else if(decoded->getOrigin()==osg::Image::BOTTOM_LEFT){decoded->flipVertical();decoded->setOrigin(osg::Image::TOP_LEFT);}
        resources.images.addEntryToObjectCache(path,decoded);resources.decodedBytes+=bytes;
    }
    auto& texture=resources.samplers[std::make_tuple(path,3u,2u)];
    if(!texture){
        const auto bytes=std::size_t(decoded->s())*decoded->t()*8;
        require(resources.samplerBytes+bytes<=128u*1024*1024,"Terrain texture budget");resources.samplerBytes+=bytes;
        texture=new osg::Texture2D(decoded);texture->setFilter(osg::Texture::MIN_FILTER,osg::Texture::LINEAR_MIPMAP_LINEAR);
        texture->setFilter(osg::Texture::MAG_FILTER,osg::Texture::LINEAR);texture->setWrap(osg::Texture::WRAP_S,osg::Texture::REPEAT);texture->setWrap(osg::Texture::WRAP_T,osg::Texture::REPEAT);texture->setUseHardwareMipMapGeneration(true);
    }
    return texture;
}
}
void buildTerrain(Environment& out,G2::Resources& resources,const std::map<Coord,ESM::Land>& lands,const std::map<unsigned,std::string>& textures){
    constexpr int side=65;Terrain::BufferCache buffers;
    auto indices=buffers.getIndexBuffer(side,0); // genuine upstream diamond topology, shared with Bullet
    for(int cx=-3;cx<=-1;++cx)for(int cy=-10;cy<=-8;++cy){
        auto it=lands.find({cx,cy});require(it!=lands.end(),"Missing selected terrain");
        constexpr int required=ESM::Land::DATA_VHGT|ESM::Land::DATA_VNML|ESM::Land::DATA_VTEX;
        const auto* data=it->second.getLandData(required|ESM::Land::DATA_VCLR);
        require(data&&(data->mDataLoaded&required)==required,"Missing required VHGT/VNML/VTEX");
        osg::ref_ptr<osg::Vec3Array> vertices=new osg::Vec3Array,normals=new osg::Vec3Array;
        osg::ref_ptr<osg::Vec4Array> colors=new osg::Vec4Array;
        osg::ref_ptr<osg::Vec2Array> uv=new osg::Vec2Array,blendUV=new osg::Vec2Array;
        for(int x=0;x<side;++x)for(int y=0;y<side;++y){
            const int index=y*side+x;const auto h=data->mHeights[index];require(std::isfinite(h),"Nonfinite height");
            vertices->push_back({float(cx*8192+x*128),float(cy*8192+y*128),h});
            osg::Vec3 normal(data->mNormals[index*3],data->mNormals[index*3+1],data->mNormals[index*3+2]);
            require(normal.length2()>0,"Zero terrain normal");normal.normalize();normals->push_back(normal);
            const bool colored=data->mDataLoaded&ESM::Land::DATA_VCLR;
            colors->push_back(colored?osg::Vec4(data->mColours[index*3]/255.f,data->mColours[index*3+1]/255.f,data->mColours[index*3+2]/255.f,1):osg::Vec4(1,1,1,1));
            uv->push_back({x/4.f,y/4.f});blendUV->push_back(blendCoordinates(x/64.f,y/64.f));
        }
        // Detect height cracks instead of hiding them with invented skirt vertices.
        for(const auto& [neighbor,dx,dy]:{std::tuple(Coord(cx+1,cy),1,0),std::tuple(Coord(cx,cy+1),0,1)}){
            auto n=lands.find(neighbor);if(n==lands.end())continue;auto* adjacent=n->second.getLandData(ESM::Land::DATA_VHGT);
            require(adjacent,"Missing adjacent heights");
            for(int i=0;i<side;++i){int a=dx?i*side+64:64*side+i;int b=dx?i*side:i;
                require(std::abs(data->mHeights[a]-adjacent->mHeights[b])<=.01,"Height seam mismatch");}
        }
        auto mesh=std::make_unique<btTriangleMesh>();
        mesh->preallocateVertices(indices->getNumIndices());mesh->preallocateIndices(indices->getNumIndices());
        for(unsigned i=0;i<indices->getNumIndices();i+=3){
            const auto& a=vertices->at(indices->index(i));const auto& b=vertices->at(indices->index(i+1));const auto& c=vertices->at(indices->index(i+2));
            // Known topology: append directly, avoiding a quadratic duplicate-vertex search.
            mesh->addTriangle(btVector3(a.x(),a.y(),a.z()),btVector3(b.x(),b.y(),b.z()),btVector3(c.x(),c.y(),c.z()),false);
        }
        Resource::CollisionShapePtr collision(new Resource::TriangleMeshShape(mesh.get(),true));mesh.release();out.physics->addTerrain(std::move(collision));
        const int blendSize=ESMTerrain::getBlendmapSize(1,16); // 17; sample a real neighboring texture border
        std::map<unsigned,osg::ref_ptr<osg::Image>> masks;
        ESMTerrain::sampleBlendmaps(1,float(cx),float(cy),16,[&](const ESMTerrain::CellSample& sample){
            const auto found=lands.find({sample.mCellX,sample.mCellY});require(found!=lands.end(),"Missing blendmap halo LAND");
            const auto* source=found->second.getLandData(ESM::Land::DATA_VTEX);require(source,"Missing blendmap VTEX");
            const unsigned id=source->mTextures[sample.mSrcCol*16+sample.mSrcRow];
            require(id>0&&textures.count(id-1),"Missing/default LTEX not supported in this bounded region");
            auto& mask=masks[id];if(!mask){mask=new osg::Image;mask->allocateImage(blendSize*2,blendSize*2,1,GL_RGBA,GL_UNSIGNED_BYTE);std::fill(mask->data(),mask->data()+mask->getTotalSizeInBytes(),0);}
            for(unsigned y=0;y<2;++y)for(unsigned x=0;x<2;++x)mask->setColor(osg::Vec4(1,1,1,1),sample.mDstRow*2+x,sample.mDstCol*2+y);
        });
        unsigned pass=0;
        for(const auto& [id,mask]:masks){
            osg::ref_ptr<osg::Geometry> drawable=new osg::Geometry;drawable->setVertexArray(vertices);drawable->setNormalArray(normals,osg::Array::BIND_PER_VERTEX);
            drawable->setColorArray(colors,osg::Array::BIND_PER_VERTEX);drawable->setVertexAttribArray(6,uv,osg::Array::BIND_PER_VERTEX);drawable->setVertexAttribArray(7,blendUV,osg::Array::BIND_PER_VERTEX);drawable->addPrimitiveSet(indices);
            drawable->setUseDisplayList(false);drawable->setUseVertexBufferObjects(true);drawable->setUseVertexArrayObject(true);
            osg::ref_ptr<osg::Geode> node=new osg::Geode;node->addDrawable(drawable);auto* state=node->getOrCreateStateSet();
            auto diffuse=image(resources,textures.at(id-1));
            out.textures.push_back(std::string(Misc::ResourceHelpers::correctTexturePath(VFS::Path::Normalized(textures.at(id-1)),resources.vfs).value()));
            state->setTextureAttribute(0,diffuse);osg::ref_ptr<osg::Texture2D> blend=new osg::Texture2D(mask);
            blend->setFilter(osg::Texture::MIN_FILTER,osg::Texture::LINEAR);blend->setFilter(osg::Texture::MAG_FILTER,osg::Texture::LINEAR);
            blend->setWrap(osg::Texture::WRAP_S,osg::Texture::CLAMP_TO_EDGE);blend->setWrap(osg::Texture::WRAP_T,osg::Texture::CLAMP_TO_EDGE);state->setTextureAttribute(1,blend);
            blend->setResizeNonPowerOfTwoHint(false);state->setMode(GL_CULL_FACE,osg::StateAttribute::ON);
            state->addUniform(new osg::Uniform("baseTexture",0));state->addUniform(new osg::Uniform("blendTexture",1));state->addUniform(new osg::Uniform("terrainLayer",1));
            state->setAttributeAndModes(new osg::Depth(pass?osg::Depth::EQUAL:osg::Depth::LEQUAL,0,1,true),osg::StateAttribute::ON);
            state->setMode(GL_BLEND,pass?osg::StateAttribute::ON:osg::StateAttribute::OFF);
            if(pass)state->setAttribute(new osg::BlendFunc(GL_ONE,GL_ONE));
            state->setRenderBinDetails(-100+int(pass),"RenderBin");++pass;out.scene->addChild(node);
        }
        out.terrainPasses+=pass;out.terrainVertices+=side*side;out.terrainTriangles+=8192;
    }
}
}
