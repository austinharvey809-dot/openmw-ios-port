#include "Interior.hpp"
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadcell.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/esm3/loadacti.hpp>
#include <components/esm3/loadcont.hpp>
#include <components/esm3/loaddoor.hpp>
#include <components/esm3/loadmisc.hpp>
#include <components/esm3/loadligh.hpp>
#include <osg/MatrixTransform>
#include <osg/ComputeBoundsVisitor>
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <type_traits>
#include <optional>

namespace G2 {
namespace {
void require(bool ok,const std::string& reason){if(!ok)throw std::runtime_error("G2 "+reason);}
std::string lower(std::string s){for(char& c:s)if(c>='A'&&c<='Z')c+=('a'-'A');return s;}
struct Base {std::string model,type;bool deleted=false;ESM::Light::LHDTstruct light{};};
template<class T> void base(ESM::ESMReader& reader,std::map<std::string,Base>& objects,const char* type){
    T value{};bool deleted=false;value.load(reader,deleted);
    Base b;b.type=type;b.deleted=deleted;b.model=value.mModel.getOriginal();
    if constexpr(std::is_same_v<T,ESM::Light>)b.light=value.mData;
    require(objects.emplace(lower(std::string(value.mId.getRefIdString())),b).second,"Duplicate base ID in single-master input");
}
osg::Vec3f rgb(std::uint32_t color){return {float(color&255)/255.f,float((color>>8)&255)/255.f,float((color>>16)&255)/255.f};}
}
Resources::Resources(const std::filesystem::path& directory){
    require(!std::filesystem::is_symlink(directory)&&std::filesystem::is_directory(directory),"Missing/unsafe model directory");
    for(const char* n:{"Morrowind.esm","Morrowind.bsa"})
        require(std::filesystem::is_regular_file(std::filesystem::symlink_status(directory/n)),"Missing/nonregular private input");
    OpenMWIOSBsaVfs::addExistingMorrowindBSA(vfs,directory/"Morrowind.bsa",encoder);vfs.buildIndex();
}
osg::Matrix placement(const ESM::CellRef& r){
    require(std::isfinite(r.mScale)&&r.mScale>0&&r.mScale<=100,"Invalid placement scale");
    for(unsigned i=0;i<3;++i)require(std::isfinite(r.mPos.pos[i])&&std::isfinite(r.mPos.rot[i]),"Nonfinite CELL placement");
    // Same non-actor convention as RenderingManager: negative X,Y,Z quaternions.
    auto q=osg::Quat(r.mPos.rot[0],osg::Vec3(-1,0,0))*osg::Quat(r.mPos.rot[1],osg::Vec3(0,-1,0))
        *osg::Quat(r.mPos.rot[2],osg::Vec3(0,0,-1));
    return osg::Matrix::scale(r.mScale,r.mScale,r.mScale)*osg::Matrix::rotate(q)
        *osg::Matrix::translate(r.mPos.pos[0],r.mPos.pos[1],r.mPos.pos[2]);
}
Environment load(const std::filesystem::path& directory,const std::string& cellName){
    Resources resources(directory);ToUTF8::Utf8Encoder encoder(ToUTF8::WINDOWS_1252);
    ESM::ESMReader reader;reader.setEncoder(&encoder);reader.open(directory/"Morrowind.esm");
    require(reader.getGameFiles().empty(),"Only standalone base master supported; plugins require ESMStore integration");
    std::map<std::string,Base> objects;std::vector<ESM::CellRef> references;
    Environment result;result.cell=cellName;result.scene=new osg::Group;bool found=false;
    unsigned records=0;std::set<unsigned> refnums;
    while(reader.hasMoreRecs()){
        require(++records<=1000000,"ESM record budget exceeded");
        auto type=reader.getRecName();reader.getRecHeader();
        if(type=="STAT")base<ESM::Static>(reader,objects,"STAT");
        else if(type=="ACTI")base<ESM::Activator>(reader,objects,"ACTI");
        else if(type=="CONT")base<ESM::Container>(reader,objects,"CONT");
        else if(type=="DOOR")base<ESM::Door>(reader,objects,"DOOR");
        else if(type=="MISC")base<ESM::Miscellaneous>(reader,objects,"MISC");
        else if(type=="LIGH")base<ESM::Light>(reader,objects,"LIGH");
        else if(type=="CELL"){
            ESM::Cell cell;bool deleted=false;cell.load(reader,deleted,false);
            if(lower(cell.mName)!=lower(cellName)){reader.skipRecord();continue;}
            require(!found&&!deleted&&!cell.isExterior(),"Missing/deleted/duplicate/non-interior CELL");found=true;
            require((cell.mData.mFlags&(ESM::Cell::HasWater|ESM::Cell::QuasiEx))==0,"Water/weather cells require full scene manager");
            require(cell.hasAmbient(),"CELL lacks ambient lighting");result.ambient=rgb(cell.mAmbi.mAmbient);
            ESM::CellRef reference;bool removed=false,moved=false;ESM::MovedCellRef movedRef;
            while(ESM::Cell::getNextRef(reader,reference,removed,movedRef,moved,ESM::Cell::GetNextRefMode::LoadAll)){
                require(!moved,"Moved references require plugin merge support");
                require(++result.references<=512,"CELL reference budget exceeded");
                require(refnums.insert(reference.mRefNum.mIndex).second,"Duplicate CELL reference number");
                if(removed){++result.deletedReferences;continue;}
                placement(reference);references.push_back(reference);
            }
            require(!reader.hasMoreSubs(),"Unprocessed CELL reference data");
        }else reader.skipRecord();
    }
    require(found,"Selected interior not found");
    std::map<std::string,Model> models;std::set<std::string> textures;bool entry=false;
    for(const auto& reference:references){
        const std::string id=lower(std::string(reference.mRefID.getRefIdString()));
        const auto it=objects.find(id);require(it!=objects.end()&&!it->second.deleted,"Missing/unsupported base ID "+id);
        const auto& b=it->second;
        if(id=="northmarker"){++result.markers;continue;} // editor/map orientation, never scene geometry
        const auto matrix=placement(reference);
        std::optional<std::size_t> lightIndex;
        if(b.type=="LIGH"){
            if(b.light.mFlags&(ESM::Light::Flicker|ESM::Light::FlickerSlow|ESM::Light::Pulse|ESM::Light::PulseSlow))++result.timeVaryingLights;
            if(b.light.mFlags&ESM::Light::OffDefault)++result.disabledLights;
            require(b.light.mRadius>=0&&b.light.mRadius<=100000,"Invalid light radius");
            if(!(b.light.mFlags&ESM::Light::OffDefault)&&b.light.mRadius>0){
                require(result.lights.size()<8,"Point-light budget exceeded");
                lightIndex=result.lights.size();
                result.lights.push_back({osg::Vec3f(reference.mPos.pos[0],reference.mPos.pos[1],reference.mPos.pos[2]),
                    rgb(b.light.mColor)*((b.light.mFlags&ESM::Light::Negative)?-1.f:1.f),float(b.light.mRadius)});
            }
        }
        if(b.model.empty()){
            require(b.type=="LIGH","Missing model for non-light base ID "+id);++result.modelLessLights;continue;
        }
        auto key=lower(b.model);std::replace(key.begin(),key.end(),'\\','/');
        auto model=models.find(key);
        if(model==models.end()){
            require(models.size()<128,"Unique model budget exceeded");
            try{model=models.emplace(key,loadMesh(resources,b.model)).first;}
            catch(const std::exception& e){throw std::runtime_error("G2 cell="+cellName+" base="+id+" model="+key+": "+e.what());}
            result.models.push_back(model->second.resourceKey);
            for(const auto& t:model->second.textureKeys)textures.insert(t);
        }
        const Model& owned=model->second;
        if(lightIndex&&owned.hasLightOffset)result.lights[*lightIndex].position=osg::Vec3f(owned.lightOffset*matrix);
        osg::ref_ptr<osg::MatrixTransform> instance=new osg::MatrixTransform(matrix);
        instance->setName(id+"#"+std::to_string(reference.mRefNum.mIndex));instance->addChild(owned.scene);
        result.scene->addChild(instance);++result.instances;
        result.vertices+=owned.vertices;result.triangles+=owned.triangles;result.shapes+=owned.shapes;
        result.collisionBranches+=owned.collisionBranches;result.particleBranches+=owned.particleBranches;
        require(result.vertices<=2000000&&result.triangles<=2000000,"Instanced geometry budget exceeded");
        // A real load-door reference supplies an interior entry, not a hardcoded arrangement.
        if(b.type=="DOOR"&&reference.mTeleport&&!entry){
            result.entry={reference.mPos.pos[0],reference.mPos.pos[1],reference.mPos.pos[2]+96};
            result.entryYaw=-reference.mPos.rot[2];entry=true;
        }
    }
    require(result.instances>0,"Interior contains no renderable models");
    require(entry,"Interior needs a placed teleport door for camera entry");
    // Point inward toward the computed room bounds instead of guessing which
    // side of a placed door is inside. This is a free-fly camera, not physics.
    osg::ComputeBoundsVisitor bounds;result.scene->accept(bounds);auto box=bounds.getBoundingBox();
    require(box.valid(),"Invalid environment bounds");
    auto inward=osg::Vec3d(box.center())-result.entry;inward.z()=0;
    require(inward.length2()>0,"Cannot derive entry direction");inward.normalize();
    result.entry+=inward*100;result.entryYaw=std::atan2(-inward.x(),inward.y());
    result.textures.assign(textures.begin(),textures.end());result.decodedBytes=resources.decodedBytes;
    result.samplerCount=resources.samplers.size();
    result.samplerBytes=resources.samplerBytes;
    return result;
}
}
