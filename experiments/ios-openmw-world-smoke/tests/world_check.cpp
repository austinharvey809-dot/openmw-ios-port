#include "Session.hpp"
#include "SceneAudit.hpp"
#include "GLES3Terrain.hpp"
#include "InputProfile.hpp"
#include "Notifications.hpp"
#include <components/debug/debuglog.hpp>
#include <osgDB/Registry>
#include <iostream>
#include <sstream>
#include <thread>
#include <cstdio>
#include <osg/Depth>
#include <osg/Uniform>
#include <iterator>
// Supplemental shared-desktop providers also register the same real readers.
USE_OSGPLUGIN(dds)
USE_OSGPLUGIN(tga)
USE_OSGPLUGIN(bmp)
USE_OSGPLUGIN(png)
USE_OSGPLUGIN(jpeg)
USE_OSGPLUGIN(osg)
USE_SERIALIZER_WRAPPER_LIBRARY(osg)

namespace {
void require(bool ok,const std::string& message){if(!ok)throw std::runtime_error("G4 test: "+message);}
template<class F> void rejection(F action,const std::string& expected){
    try{action();}catch(const std::exception& e){require(std::string(e.what()).find(expected)!=std::string::npos,"Wrong rejection: "+std::string(e.what()));return;}
    throw std::runtime_error("G4 test: expected rejection missing: "+expected);
}
void settle(G4::Session& session,double& now,const G4::Session::Acceptance& accept={}){
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(15);
    while(session.loading()){
        require(std::chrono::steady_clock::now()<deadline,"Asynchronous world load timed out");
        session.update(now+=.001,accept);std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}
}
int main(int argc,char** argv){
    // Genuine upstream logging uses cout. Keep diagnostics on stderr and reserve
    // the C stdout stream for a single machine-readable result.
    auto* original=std::cout.rdbuf(std::cerr.rdbuf());
    try{
        if(argc<4||argc>5)throw std::runtime_error("data-directory shaders case [shader-output] required");
        const std::filesystem::path directory=argv[1];const std::string mode=argv[3];
        std::vector<std::filesystem::path> content={directory/"Morrowind.esm"};
        if(std::filesystem::is_regular_file(directory/"Authored.esp"))content.push_back(directory/"Authored.esp");
        if(mode=="load-order")std::reverse(content.begin(),content.end());
        if(mode=="duplicate-content")content.push_back(content.front());
        auto index=std::make_unique<G4::WorldIndex>(content);
        G4::ResourcePaths paths{{directory/"Morrowind.bsa"},{}};
        if(std::filesystem::is_regular_file(directory/"Authored.bsa"))paths.archives.push_back(directory/"Authored.bsa");
        if(std::filesystem::is_directory(directory/"loose"))paths.looseDirectories.push_back(directory/"loose");
        auto assets=std::make_unique<G4::Resources>(paths,argv[2]);
        if(mode=="missing-mesh")assets->instance("does-not-exist.nif");
        const bool interior=mode.starts_with("inspect-interior:");
        auto area=G4::prepare(*index,*assets,interior?G4::Location{mode.substr(17),0,0}:G4::Location{});
        require(area->cells==(interior?1:9),"Unexpected cell count");
        if(mode=="plugin-delete")require(area->references==9,"Plugin deletion did not remove original reference");
        if(mode=="plugin-new")require(area->references==11,"Plugin reference incorrectly collided with master refnum");
        if(mode=="plugin-override"){
            const auto* cell=index->cells.find(-2,-9);const auto refs=index->references(*cell);
            auto floor=std::find_if(refs.begin(),refs.end(),[](const auto& ref){return ref.mRefNum.mIndex==5;});
            require(refs.size()==2&&floor!=refs.end()&&floor->mPos.pos[2]==64,"Plugin placement failed to override master reference");
        }
        if(mode=="plugin-move"){
            const auto from=index->references(*index->cells.find(-2,-9)),to=index->references(*index->cells.find(-1,-9));
            require(std::none_of(from.begin(),from.end(),[](const auto& r){return r.mRefNum.mIndex==5;}),"Moved master ref remained in source cell");
            require(std::any_of(to.begin(),to.end(),[](const auto& r){return r.mRefNum.mIndex==5&&r.mRefNum.mContentFile==0&&r.mPos.pos[2]==64;}),"Moved reference lease/master mapping lost");
        }
        if(mode=="plugin-palette"){
            require(index->lands.find(-2,-9)->getPlugin()==1,"Plugin LAND ownership lost");
            require(index->textures.search(0,1)&&index->textures.search(0,1)->getNormalized().value()=="plugin.dds","Per-plugin LTEX palette lost");
            require(index->textures.search(0,0)->getNormalized().value()=="fixture.dds","Master LTEX palette overwritten");
        }
        if(mode=="loose-override"||mode=="last-bsa-wins"){
            const auto stream=assets->vfs.get(VFS::Path::Normalized("textures/fixture.dds"));
            const std::string bytes{std::istreambuf_iterator<char>(*stream),{}};
            require(bytes.ends_with(mode=="loose-override"?"G4-loose-priority":"G4-last-archive"),"Genuine VFS precedence selected the wrong resource");
        }
        G4::SceneAudit audit;area->scene->accept(audit);
        require(area->terrainPasses==audit.terrainPasses&&area->drawables==audit.geometry&&area->programs==audit.programs.size(),"Prepared pass/program diagnostics differ from genuine graph");
        require(!audit.programs.empty()&&(interior||audit.terrainPasses>0),"Genuine model/terrain shaders were not produced");
        if(argc==5)audit.dump(argv[4]);
        const auto cells=area->cells,references=area->references,instances=area->instances,collisions=area->physics->objectCount();
        if(mode=="placement"||mode=="good"){
            ESM::CellRef reference;reference.blank();reference.mScale=2;reference.mPos.pos[0]=10;
            reference.mPos.rot[2]=osg::PI/2;
            const auto point=osg::Vec3d(1,0,0)*G4::placement(reference);
            require(std::abs(point.x()-10)<1e-5&&std::abs(point.y()+2)<1e-5,"Original rotation/scale convention changed");
            const auto* state=area->scene->getStateSet();osg::Vec4 diffuse;
            require(state&&state->getUniform("material.diffuse")&&state->getUniform("material.diffuse")->get(diffuse)&&diffuse.r()>0,"Inherited genuine default material is missing/black");
            require(state->getAttribute(osg::StateAttribute::DEPTH)&&state->getMode(GL_CULL_FACE)==osg::StateAttribute::ON,"Default depth/culling lost");
            if(mode=="good"){
                // Clear authored LAND away from the fixture door's raised quad.
                area->physics->start({-13000,-69000,16});osg::Vec3d eye;
                for(unsigned i=0;i<240;++i)eye=area->physics->move({},G3::Physics::FixedStep);
                require(area->physics->grounded(),"Genuine terrain character failed to ground");const auto before=eye;
                for(unsigned i=0;i<120;++i)eye=area->physics->move({0,180,0},G3::Physics::FixedStep);
                require(eye.y()-before.y()>100&&std::abs(eye.z()-before.z())<5,"Grounded traversal did not advance on genuine terrain: dy="+std::to_string(eye.y()-before.y())+" dz="+std::to_string(eye.z()-before.z()));
            }
        }
        if(mode=="cache"){
            const auto one=assets->instance("Authored/quad.nif"),two=assets->instance("Authored/quad.nif");
            require(one!=two,"SceneManager returned a shared mutable instance");
            assets->expire(0);assets->expire(100);G4::SceneAudit alive;one->accept(alive);
            require(!alive.programs.empty(),"Cache expiry destroyed a live instance");
        }
        if(mode=="notification-concurrency"||mode=="notification-lifetime"){
            std::atomic<unsigned> calls{0};osg::ref_ptr<G4::NotificationSink> sink=new G4::NotificationSink([&](const auto&){++calls;});
            std::vector<std::thread> writers;
            for(unsigned i=0;i<4;++i)writers.emplace_back([&]{for(unsigned n=0;n<1000;++n)sink->notify(osg::WARN,"authored log line");});
            for(auto& writer:writers)writer.join();
            require(calls==4000&&sink->warnings()==4000,"Concurrent notification counter/callback lost updates");
            sink->close();sink->notify(osg::WARN,"after close");require(calls==4000,"Closed sink invoked a dead callback");
            if(mode=="notification-lifetime"){
                auto* original=osg::getNotifyHandler();
                rejection([&]{G4::NotificationScope scope([](const auto&){});throw std::runtime_error("authored constructor failure");},"constructor failure");
                require(osg::getNotifyHandler()==original,"Constructor failure left a global callback installed");
                std::thread closingWriter([&]{for(unsigned i=0;i<1000;++i)sink->notify(osg::WARN,"closing");});
                sink->close();closingWriter.join();require(calls==4000,"Sink close raced callback lifetime");
            }
        }
        if(mode=="cache-clock"){
            Resource::GenericObjectCache<std::string,std::shared_ptr<int>> cache;auto held=std::make_shared<int>(7);
            cache.addEntryToObjectCache("held",held);cache.addEntryToObjectCache("unheld",std::make_shared<int>(8));
            cache.update(10,5);cache.update(14,5);require(cache.getStats().mSize==2,"Cache expired before reference-time delay");
            cache.update(16,5);require(cache.getStats().mSize==1&&cache.getStats().mExpired==1&&*held==7,"Expiry failed to preserve external owner");
            cache.clear();require(*held==7,"Clear destroyed a live cache owner");
        }
        if(mode=="maintenance-clock"){
            area.reset();G4::Session session(std::move(index),std::move(assets));double now=0;
            auto pump=[&]{const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
                while(session.maintenanceRuns+session.maintenanceFailures==0){
                    require(std::chrono::steady_clock::now()<deadline,"Maintenance result timed out");
                    session.update(now+=.001,{},100);std::this_thread::sleep_for(std::chrono::milliseconds(1));
                }};
            session.update(now,{},std::numeric_limits<double>::quiet_NaN());pump();
            require(session.maintenanceFailures==1&&session.failedLoads==0&&session.lastError.empty()&&session.lastMaintenanceError.find("cache-maintenance")!=std::string::npos,"Maintenance failure masqueraded as world-load failure");
            require(session.cacheStats.contains("Node Count")&&session.cacheStats.contains("Image Count"),"Genuine cache counters missing");
            session.memoryWarning();session.update(now+=.001,{},100);session.shutdown();session.update(now+=.001,{},100);
            require(session.lastCacheReferenceTime==100&&session.loads==1,"Cache used a mismatched animation/uptime epoch");
        }
        if(mode=="device-rejection"||mode=="shutdown"){
            area.reset();G4::Session session(std::move(index),std::move(assets));double now=0;
            const auto* original=session.scene()->getChild(0);session.area().physics->start({-8000,-68000,16});session.update(now);
            if(mode=="shutdown"){session.shutdown();}
            else{
                unsigned attempts=0;
                settle(session,now,[&](const G4::Area&){++attempts;throw std::runtime_error("authored shader link rejection");});
                require(attempts==1&&session.loads==1&&session.transitions==0&&session.failedLoads==1&&session.scene()->getChild(0)==original,"Rejected device scene was published");
                require(session.lastError.find("stage=device-prepare")!=std::string::npos&&session.peakResidentCells==15,"Rejected scene diagnostics missing");
                session.reset();session.area().physics->start({-8000,-68000,16});session.update(now+=.001);
                const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
                while(!session.loading()){
                    require(std::chrono::steady_clock::now()<deadline,"Recovery request waited indefinitely behind maintenance");
                    session.update(now+=.001);std::this_thread::sleep_for(std::chrono::milliseconds(1));
                }
                settle(session,now,[&](const G4::Area& candidate){require(candidate.cells==6,"Invalid accepted candidate");});
                require(session.loads==2&&session.area().location.x==-1&&session.lastError.empty(),"Recovery did not commit the validated replacement: loads="+std::to_string(session.loads)+" x="+std::to_string(session.area().location.x)+" error="+session.lastError);
            }
        }
        if(mode=="door"){
            require(!area->doors.empty(),"Genuine door destination was not discovered");
            const auto door=area->doors.front();const auto location=G4::destination(door);
            require(location.interior=="Seyda Neen, Fargoth's House","Wrong genuine interior destination");
            auto room=G4::prepare(*index,*assets,location);require(room->cells==1&&!room->doors.empty(),"Interior door missing");
            require(G4::destination(room->doors.front()).interior.empty(),"Genuine return destination missing");
        }
        if(mode=="locked-door"){
            G4::Door door{};door.locked=true;G4::destination(door);
            throw std::runtime_error("G4 test: locked door incorrectly accepted");
        }
        if(mode=="unload"){
            area.reset();assets->system.clearCache();
            area=G4::prepare(*index,*assets,{});require(area->cells==9,"Terrain/resource reload failed");
        }
        if(mode=="gles-terrain"){
            osg::ref_ptr<Terrain::TerrainDrawable> drawable=new Terrain::TerrainDrawable;
            osg::ref_ptr<osg::StateSet> pass=new osg::StateSet;
            osg::ref_ptr<osg::Depth> depth=new osg::Depth;
            pass->setAttribute(depth);pass->setMode(GL_BLEND,osg::StateAttribute::ON);
            pass->setAttribute(new osg::Enablei(GL_BLEND,1));drawable->setPasses({pass});
            G4::GLES3Terrain adapter;adapter.apply(*drawable);
            const auto* adapted=drawable->getPasses().front().get();
            require(adapter.omittedNormalsStates==1&&adapted!=pass&&pass->getAttributeList().size()==2,"Normals-only platform state was not copied/removed");
            require(adapted->getAttribute(osg::StateAttribute::DEPTH)==depth&&adapted->getMode(GL_BLEND)==osg::StateAttribute::ON,"Color/depth semantics changed");
            pass->setAttribute(new osg::Enablei(GL_BLEND,0));drawable->setPasses({pass});
            rejection([&]{adapter.apply(*drawable);},"unsupported indexed terrain capability");
        }
        if(mode=="input-profile"){
            G4::InputProfile profile;const std::string hash(64,'a');
            profile.files={{"Morrowind.esm",hash},{"Morrowind.bsa",hash}};
            profile.verify(directory,[&](const auto&){return hash;});
            rejection([&]{profile.verify(directory,[](const auto&){return std::string(64,'b');});},"SHA-256 mismatch");
            profile.files["unexpected"] = hash;
            rejection([&]{profile.verify(directory,[&](const auto&){return hash;});},"inventory mismatch");
            rejection([&]{G4::InputProfile::resolve(directory,"../escape");},"unsafe private profile");
            rejection([&]{G4::InputProfile::resolve(directory,"C:/escape");},"unsafe private profile");
        }
        if(mode=="stream"||mode=="stream-rollback"||mode=="door-transition"){
            area.reset();G4::Session session(std::move(index),std::move(assets));double now=0;
            if(mode=="door-transition"){
                const auto door=session.area().doors.front();
                session.navigation.eye=door.position+osg::Vec3d(0,-60,64);session.navigation.yaw=0;
                session.activate();require(session.loading(),"Door activation did not stage genuine destination");settle(session,now);
                require(session.transitions==1&&session.area().location.interior==door.cell,"Door destination was not committed");
            }else{
                const auto* original=session.scene()->getChild(0);
                session.area().physics->start({-8000,-68000,16});session.update(now);
                require(session.loading()&&session.scene()->getChild(0)==original,"Streaming replaced active scene before completion");
                settle(session,now);
                if(mode=="stream")require(session.loads==2&&session.failedLoads==0&&session.area().location.x==-1,"Adjacent world window not committed");
                else{
                    require(session.failedLoads==1&&session.loads==1&&session.scene()->getChild(0)==original&&session.lastError.find("stage=world-load")!=std::string::npos,"Failed load did not retain old scene and exact diagnostic");
                    for(unsigned i=0;i<50;++i)session.update(now+=.001);
                    require(session.failedLoads==1&&!session.loading(),"Failed scene entered retry churn");session.reset();
                }
            }
            session.suspend();const auto eye=session.navigation.eye;session.update(now+10000);
            require((session.navigation.eye-eye).length()<1,"Stream/door resume simulated background time");
        }
        if(mode=="session"||mode=="suspend"||mode=="invalid-destination"){
            area.reset();G4::Session session(std::move(index),std::move(assets));
            const auto entry=session.navigation.eye;
            session.navigation.forward=1;session.suspend();session.update(10000);
            require((session.navigation.eye-entry).length()<1,"Resume simulated background time");
            require(session.navigation.forward==0,"Suspend retained movement input");
            session.memoryWarning();session.update(10000.01);
        }
        std::ostringstream report;report<<"{\"status\":\"PASS\",\"scope\":\"CPU only; native/device acceptance UNVERIFIED\",\"cells\":"<<cells
            <<",\"references\":"<<references<<",\"instances\":"<<instances<<",\"collision_objects\":"<<collisions
            <<",\"programs\":"<<audit.programs.size()<<",\"terrain_passes\":"<<audit.terrainPasses;
        if(mode.starts_with("inspect")){
            report<<",\"omitted_normals_states\":"<<area->omittedNormalsStates<<",\"exclusions\":{";bool first=true;
            for(const auto& [type,count]:area->exclusions){if(!first)report<<',';first=false;report<<'"'<<type<<"\":"<<count;}
            report<<"},\"doors\":[";first=true;
            for(const auto& door:area->doors){
                if(!first)report<<',';first=false;report<<"{\"destination\":\"";
                for(char c:door.cell){if(c=='"'||c=='\\')report<<'\\';report<<c;}
                report<<"\",\"locked\":"<<(door.locked?"true":"false")<<",\"trapped\":"<<(door.trapped?"true":"false")<<'}';
            }report<<']';
        }
        if(mode=="inspect-stream"){
            area.reset();G4::Session session(std::move(index),std::move(assets));double now=0;
            for(unsigned i=0;i<240;++i)session.navigation.eye=session.area().physics->move({},G3::Physics::FixedStep);
            require(session.area().physics->grounded(),"Original arrival did not ground with genuine shapes/terrain");
            const auto before=session.navigation.eye;
            for(unsigned i=0;i<60;++i)session.navigation.eye=session.area().physics->move({0,180,0},G3::Physics::FixedStep);
            require((session.navigation.eye-before).length()>20,"Original grounded movement probe did not advance");
            for(int direction:{1,-1}){
                const auto expected=session.area().location.x+direction;
                session.area().physics->start(session.navigation.eye+osg::Vec3d(direction*8192,0,-88));
                session.update(now+=.001);require(session.loading(),"Original neighboring cell did not stage");settle(session,now);
                require(session.area().location.x==expected&&session.failedLoads==0,"Original neighboring window failed: "+session.lastError);
            }
            auto activate=[&](const G4::Door& door){
                const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(15);
                do{
                    session.navigation.eye=door.position+osg::Vec3d(0,-60,64);session.navigation.yaw=0;
                    session.activate();if(session.loading())break;
                    require(std::chrono::steady_clock::now()<deadline,"Original door activation timed out: "+session.lastError);
                    session.update(now+=.001);std::this_thread::sleep_for(std::chrono::milliseconds(1));
                }while(true);
                settle(session,now);require(session.failedLoads==0,"Original door load failed: "+session.lastError);
            };
            const auto entry=std::find_if(session.area().doors.begin(),session.area().doors.end(),[](const auto& door){return !door.locked&&!door.trapped&&!door.cell.empty();});
            require(entry!=session.area().doors.end(),"No unlocked original interior door");const auto door=*entry;
            activate(door);require(session.area().location.interior==door.cell,"Original interior destination differs");
            const auto exit=std::find_if(session.area().doors.begin(),session.area().doors.end(),[](const auto& item){return !item.locked&&!item.trapped&&item.cell.empty();});
            require(exit!=session.area().doors.end(),"No unlocked original return door");activate(*exit);
            require(session.area().location.interior.empty()&&session.transitions==2&&session.loads==5,"Original exterior return not committed");
            report<<",\"cpu_world_loads\":"<<session.loads<<",\"cpu_door_transitions\":"<<session.transitions
                <<",\"cpu_arrival_grounded_and_movement\":true"
                <<",\"cpu_transition_scope\":\"Original destination records and scene commits; test repositions camera, no device/traversal claim\"";
        }
        report<<"}\n";
        std::cout.rdbuf(original);const auto text=report.str();std::fwrite(text.data(),1,text.size(),stdout);return 0;
    }catch(const std::exception& e){std::cout.rdbuf(original);std::cerr<<e.what()<<'\n';return 1;}
}
