#include "Session.hpp"
#include <chrono>
#include <stdexcept>

namespace G4 {
namespace {
ESM::Position initialArrival(WorldIndex& index){
    const auto* cell=index.cells.find("Seyda Neen, Fargoth's House");std::optional<ESM::Position> result;
    for(const auto& ref:index.references(*cell))if(ref.mTeleport&&ref.mDestCell.empty()&&index.base(ref.mRefID).type=="DOOR"){
        for(unsigned i=0;i<3;++i)if(!std::isfinite(ref.mDoorDest.pos[i])||!std::isfinite(ref.mDoorDest.rot[i]))
            throw std::runtime_error("G4 nonfinite original placement/destination");
        if(result)throw std::runtime_error("G4 ambiguous original arrival door");result=ref.mDoorDest;
    }
    if(!result)throw std::runtime_error("G4 missing original arrival door");return *result;
}
}
Session::Session(std::unique_ptr<WorldIndex> store,std::unique_ptr<Resources> assets)
    :index(std::move(store)),resources(std::move(assets)){
    if(!index||!resources)throw std::runtime_error("G4 missing genuine world systems");
    const auto begin=std::chrono::steady_clock::now();
    const auto entry=initialArrival(*index);const osg::Vec3d feet(entry.pos[0],entry.pos[1],entry.pos[2]);
    current=prepare(*index,*resources,exteriorAt(feet));root->addChild(current->scene);++loads;
    entryEye=feet+osg::Vec3d(0,0,88);entryYaw=-entry.rot[2];
    navigation.attach(current->physics,entryEye,entryYaw);
    lastPreparationMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
    peakResidentCells=current->cells;peakResidentInstances=current->instances;cacheStats=resources->statistics();
}
void Session::shutdown(){
    // Join outside CapabilityRegistryMutex: the worker may be waiting for it.
    if(pending.valid())try{
        auto unused=pending.get();
        std::lock_guard registry(CapabilityRegistryMutex);unused.area.reset();
    }catch(...){}
}
Session::~Session(){
    shutdown();std::lock_guard registry(CapabilityRegistryMutex);
    root->removeChildren(0,root->getNumChildren());current.reset();
}
void Session::request(Location location,osg::Vec3d eye,double yaw){
    if(pending.valid())return;
    navigation.suspend();pendingScene=true;
    requestStart=std::chrono::steady_clock::now();
    pending=std::async(std::launch::async,[this,location=std::move(location),eye,yaw]{
        const auto begin=std::chrono::steady_clock::now();
        std::lock_guard registry(CapabilityRegistryMutex);
        std::unique_ptr<Area> area;
        try{area=prepare(*index,*resources,location);}
        catch(const std::exception& e){throw std::runtime_error("G4 stage=world-load destination="+
            (location.interior.empty()?std::to_string(location.x)+","+std::to_string(location.y):location.interior)+": "+e.what());}
        const auto milliseconds=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
        return Prepared{std::move(area),eye,yaw,milliseconds,resources->statistics()};
    });
}
void Session::update(double now,const Acceptance& accept,double cacheReferenceTime){
    if(!std::isfinite(now)||now<0)return;
    std::lock_guard registry(CapabilityRegistryMutex);
    if(pending.valid()&&pending.wait_for(std::chrono::seconds(0))==std::future_status::ready){
        const auto commitStart=std::chrono::steady_clock::now();
        try{
            auto ready=pending.get();
            cacheStats=std::move(ready.caches);
            if(ready.area){
                peakResidentCells=std::max(peakResidentCells,current->cells+ready.area->cells);
                peakResidentInstances=std::max(peakResidentInstances,current->instances+ready.area->instances);
                lastPreparationMs=ready.milliseconds;
                const auto begin=std::chrono::steady_clock::now();
                try{if(accept)accept(*ready.area);}
                catch(const std::exception& e){
                    lastAcceptanceMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
                    throw std::runtime_error("G4 stage=device-prepare before scene commit: "+std::string(e.what()));
                }
                lastAcceptanceMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
                // Actual device program acceptance precedes publication. Failure
                // destroys only the candidate, retaining the old scene/physics.
                root->removeChild(current->scene);auto retired=std::move(current);current=std::move(ready.area);
                retiredSteps+=retired->physics->steps;retiredDroppedSeconds+=retired->physics->droppedSeconds;
                root->addChild(current->scene);navigation.attach(current->physics,ready.eye,ready.yaw);++loads;
                entryEye=ready.eye;entryYaw=ready.yaw;
                if(pendingDoor)++transitions;
                failedLocation.reset();lastError.clear();
                retired.reset(); // Worker has finished all registry mutation.
            }else{++maintenanceRuns;lastMaintenanceMs=ready.milliseconds;lastMaintenanceError.clear();}
        }catch(const std::exception& e){
            if(pendingScene){++failedLoads;lastError=e.what();navigation.suspend();
                if(current->location.interior.empty())failedLocation=exteriorAt(navigation.eye);
            }else{++maintenanceFailures;lastMaintenanceError="G4 stage=cache-maintenance: "+std::string(e.what());}
        }
        if(pendingScene){
            lastCommitMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-commitStart).count();
            maxCommitMs=std::max(maxCommitMs,lastCommitMs);
            lastLoadLatencyMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-requestStart).count();
        }
        pendingScene=false;pendingDoor=false;
    }
    navigation.update(now,pendingScene||failedLocation.has_value());
    if(!pending.valid()&&activationQueued){activationQueued=false;activate();}
    if(!pending.valid()&&current->location.interior.empty()){
        const auto next=exteriorAt(navigation.eye);
        if(next!=current->location && (!failedLocation || *failedLocation!=next)){
            request(next,navigation.eye,navigation.yaw);return;
        }
    }
    if(!pending.valid()&&(now>=nextMaintenance||memoryPressure.load())){
        nextMaintenance=now+1;
        const bool clear=memoryPressure.exchange(false);
        // The device supplies OSG reference time, never the independent animation
        // simulation clock or CADisplayLink/device-uptime epoch.
        const auto reference=cacheReferenceTime==-1?now:cacheReferenceTime;
        const bool invalid=!std::isfinite(reference)||reference<0||reference<lastCacheReferenceTime;
        if(!invalid)lastCacheReferenceTime=reference;
        if(clear)++cacheClears;
        pending=std::async(std::launch::async,[this,reference,clear,invalid]{
            std::lock_guard registry(CapabilityRegistryMutex);
            const auto begin=std::chrono::steady_clock::now();
            if(invalid)throw std::runtime_error("invalid/backward cache reference clock");
            if(clear)resources->system.clearCache();else resources->expire(reference);
            return Prepared{{},{},0,std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count(),resources->statistics()};
        });
    }
}
void Session::activate(){
    if(pending.valid()){if(!pendingScene)activationQueued=true;return;}
    const auto* door=activationDoor(*current,navigation.eye,navigation.direction());if(!door)return;
    try{
        const auto location=destination(*door);
        const auto& entry=door->destination;request(location,{entry.pos[0],entry.pos[1],entry.pos[2]+88},-entry.rot[2]);pendingDoor=true;
    }catch(const std::exception& e){lastError=e.what();}
}
void Session::reset(){
    if(pendingScene)return;
    activationQueued=false;
    navigation.attach(current->physics,entryEye,entryYaw);failedLocation.reset();lastError.clear();
}
}
