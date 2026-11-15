#include "Exterior.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadcell.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/esm3/loadacti.hpp>
#include <components/esm3/loadcont.hpp>
#include <components/esm3/loaddoor.hpp>
#include <components/esm3/loadmisc.hpp>
#include <components/esm3/loadligh.hpp>
#include <components/esm3/loadltex.hpp>
#include <components/nifbullet/bulletnifloader.hpp>
#include <osg/MatrixTransform>
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace G3 {
namespace {
void require(bool ok,const std::string& text){if(!ok)throw std::runtime_error("G3 "+text);}
std::string lower(std::string s){for(char& c:s){if(c>='A'&&c<='Z')c+=32;if(c=='\\')c='/';}return s;}
struct Base {std::string type,model;bool deleted=false;};
template<class T> void base(ESM::ESMReader& reader,std::map<std::string,Base>& bases,const std::string& type){
    T value{};bool deleted=false;value.load(reader,deleted);
    require(bases.emplace(lower(std::string(value.mId.getRefIdString())),Base{type,value.mModel.getOriginal(),deleted}).second,"Duplicate base ID");
}
bool excludedModel(const std::string& key){
    // These actual resources require particle/animated-scene integration. No substitute is drawn.
    return key=="chimney_smoke02.nif"||key=="l/light_fire.nif"||key=="l/light_logpile10.nif"||key=="r/siltstrider.nif";
}
bool marker(const std::string& key){return key=="editormarker.nif"||key=="editormarker_box_01.nif"||key=="marker_prison.nif"||key=="marker_north.nif";}
}
Environment load(const std::filesystem::path& directory){
    G2::Resources resources(directory);ToUTF8::Utf8Encoder encoder(ToUTF8::WINDOWS_1252);
    ESM::ESMReader reader;reader.setEncoder(&encoder);reader.open(directory/"Morrowind.esm");
    require(reader.getGameFiles().empty(),"Plugins require genuine ESMStore integration");
    std::map<std::string,Base> bases;std::map<Coord,ESM::Land> lands;
    std::map<unsigned,std::string> textures;std::vector<ESM::CellRef> references;
    Environment result;result.cell="Seyda Neen exterior (-3..-1,-10..-8)";result.scene=new osg::Group;
    result.physics=std::make_shared<Physics>();result.ambient={.35f,.35f,.35f};
    std::set<Coord> cells;std::set<unsigned> numbers;bool spawn=false;unsigned records=0;
    while(reader.hasMoreRecs()){
        require(++records<=1000000,"ESM record budget exceeded");
        auto type=reader.getRecName();reader.getRecHeader();
        if(type=="STAT")base<ESM::Static>(reader,bases,"STAT");
        else if(type=="ACTI")base<ESM::Activator>(reader,bases,"ACTI");
        else if(type=="CONT")base<ESM::Container>(reader,bases,"CONT");
        else if(type=="DOOR")base<ESM::Door>(reader,bases,"DOOR");
        else if(type=="MISC")base<ESM::Miscellaneous>(reader,bases,"MISC");
        else if(type=="LIGH")base<ESM::Light>(reader,bases,"LIGH");
        else if(type=="LTEX"){
            ESM::LandTexture value;bool deleted=false;value.load(reader,deleted);
            require(!deleted&&textures.emplace(value.mIndex,value.mTexture.getOriginal()).second,"Deleted/duplicate LTEX");
        }else if(type=="LAND"){
            ESM::Land value;bool deleted=false;value.load(reader,deleted);
            // Keep a one-cell data halo for the genuine blendmap sampler.
            if(value.mX>=-4&&value.mX<=0&&value.mY>=-11&&value.mY<=-7)
                require(!deleted&&lands.emplace(Coord(value.mX,value.mY),std::move(value)).second,"Deleted/duplicate LAND");
        }else if(type=="CELL"){
            ESM::Cell cell;bool deleted=false;cell.load(reader,deleted,false);
            const bool wanted=cell.isExterior()&&selected(cell.mData.mX,cell.mData.mY);
            const bool entrance=!cell.isExterior()&&cell.mName==G2::CellName;
            if(!wanted&&!entrance){reader.skipRecord();continue;}
            require(!deleted,"Deleted selected CELL");
            if(wanted)require(cells.emplace(cell.mData.mX,cell.mData.mY).second,"Duplicate exterior CELL");
            ESM::CellRef r;bool removed=false,moved=false;ESM::MovedCellRef movedRef;
            while(ESM::Cell::getNextRef(reader,r,removed,movedRef,moved,ESM::Cell::GetNextRefMode::LoadAll)){
                require(!moved,"Moved references require ESMStore");
                if(removed){if(wanted)++result.deletedReferences;continue;}
                if(entrance&&r.mTeleport&&r.mDestCell.empty()){
                    require(!spawn,"Ambiguous Fargoth exterior arrival");
                    for(unsigned i=0;i<3;++i)require(std::isfinite(r.mDoorDest.pos[i])&&std::isfinite(r.mDoorDest.rot[i]),"Invalid arrival position");
                    result.entry={r.mDoorDest.pos[0],r.mDoorDest.pos[1],r.mDoorDest.pos[2]+88};
                    result.entryYaw=-r.mDoorDest.rot[2];spawn=true;
                }
                if(wanted){
                    require(++result.references<=4096,"Reference budget exceeded");
                    require(numbers.insert(r.mRefNum.mIndex).second,"Duplicate reference number");
                    G2::placement(r);references.push_back(r);
                }
            }
        }else if(type=="NPC_"||type=="CREA"||type=="LEVC"||type=="LEVI"||type=="INGR"||type=="BOOK"||type=="WEAP"||type=="ALCH"||type=="ARMO"||type=="CLOT"||type=="APPA"||type=="PROB"||type=="LOCK"||type=="REPA"){
            auto id=reader.getHNString("NAME");
            require(bases.emplace(lower(id),Base{type.toString(),{},false}).second,"Duplicate excluded base ID");reader.skipRecord();
        }else reader.skipRecord();
    }
    require(cells.size()==9,"Missing selected exterior CELL");result.cells=cells.size();require(spawn,"Missing genuine Fargoth arrival door");
    require(selected(int(std::floor(result.entry.x()/8192)),int(std::floor(result.entry.y()/8192))),"Arrival outside selected cells");
    buildTerrain(result,resources,lands,textures);
    std::map<std::string,G2::Model> models;std::map<std::string,std::shared_ptr<Resource::BulletShape>> collision;
    std::set<std::string> textureKeys;
    for(const auto& r:references){
        const auto id=lower(std::string(r.mRefID.getRefIdString()));auto it=bases.find(id);
        require(it!=bases.end()&&!it->second.deleted,"Missing/deleted base ID "+id);
        const auto& b=it->second;
        if(b.type!="STAT"&&b.type!="ACTI"&&b.type!="CONT"&&b.type!="DOOR"&&b.type!="MISC"&&b.type!="LIGH"){
            ++result.excludedReferences;++result.exclusions["record-type:"+b.type];continue;
        }
        if(b.model.empty()){require(b.type=="LIGH","Missing model "+id);++result.modelLessLights;continue;}
        auto key=lower(b.model);
        if(marker(key)){++result.markers;continue;}
        if(excludedModel(key)){++result.excludedEffects;++result.exclusions["animated-or-effect:"+key];continue;}
        try {
            auto model=models.find(key);
            if(model==models.end()){
                require(models.size()<256,"Model budget exceeded");
                model=models.emplace(key,G3::loadMesh(resources,b.model)).first;result.models.push_back(model->second.resourceKey);
                auto path=VFS::Path::Normalized(model->second.resourceKey);Nif::NIFFile file(path);Nif::Reader parser(file,&resources.encoder);parser.parse(resources.vfs.get(path));
                collision[key]=NifBullet::BulletNifLoader().load(file);
                require(!collision[key]->isAnimated(),"Animated collision requires upstream actor/scene integration");
            }
            const auto& owned=model->second;const auto matrix=G2::placement(r);
            osg::ref_ptr<osg::MatrixTransform> instance=new osg::MatrixTransform(matrix);instance->setName(id+"#"+std::to_string(r.mRefNum.mIndex));instance->addChild(owned.scene);
            result.scene->addChild(instance);result.physics->add(collision.at(key),matrix);
            ++result.instances;result.vertices+=owned.vertices;result.triangles+=owned.triangles;result.shapes+=owned.shapes;
            result.collisionBranches+=owned.collisionBranches;result.particleBranches+=owned.particleBranches;
            textureKeys.insert(owned.textureKeys.begin(),owned.textureKeys.end());
            require(result.triangles<=2000000,"Triangle budget exceeded");
            if(b.type=="DOOR"&&r.mTeleport){
                for(unsigned i=0;i<3;++i)require(std::isfinite(r.mDoorDest.pos[i])&&std::isfinite(r.mDoorDest.rot[i]),"Invalid door destination");
                result.doors.push_back({{r.mPos.pos[0],r.mPos.pos[1],r.mPos.pos[2]},r.mDoorDest,r.mDestCell});
            }
        }catch(const std::exception& e){throw std::runtime_error("G3 base="+id+" model="+key+": "+e.what());}
    }
    require(result.instances>0,"No exterior objects");
    textureKeys.insert(result.textures.begin(),result.textures.end());result.textures.assign(textureKeys.begin(),textureKeys.end());
    result.decodedBytes=resources.decodedBytes;result.samplerBytes=resources.samplerBytes;result.samplerCount=resources.samplers.size();
    result.physics->start(result.entry-osg::Vec3d(0,0,88));return result;
}
}
