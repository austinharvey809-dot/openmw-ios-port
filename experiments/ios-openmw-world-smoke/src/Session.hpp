#pragma once
#include "Traversal.hpp"
#include "World.hpp"
#include <atomic>
#include <future>
#include <optional>
#include <functional>

namespace G4 {
// A deliberately small platform coordinator around genuine upstream systems.
// Only the render thread attaches/detaches scene roots. At most one worker job
// mutates the index/resource-manager registry; the entire world is never loaded.
class Session {
    struct Prepared {
        std::unique_ptr<Area> area;osg::Vec3d eye;double yaw;double milliseconds=0;
        std::map<std::string,double> caches;
    };
    std::unique_ptr<WorldIndex> index;
    std::unique_ptr<Resources> resources;
    std::unique_ptr<Area> current;
    std::future<Prepared> pending;
    osg::ref_ptr<osg::Group> root=new osg::Group;
    std::atomic<bool> memoryPressure{false};
    double nextMaintenance=0;
    std::chrono::steady_clock::time_point requestStart;
    bool pendingScene=false,pendingDoor=false;
    bool activationQueued=false;
    unsigned long long retiredSteps=0;
    double retiredDroppedSeconds=0;
    std::optional<Location> failedLocation;
    osg::Vec3d entryEye;
    double entryYaw=0;
    void request(Location location,osg::Vec3d eye,double yaw);
public:
    using Acceptance=std::function<void(const Area&)>;
    Traversal navigation;
    unsigned loads=0,transitions=0,failedLoads=0;
    std::string lastError;
    double lastPreparationMs=0;
    double lastCommitMs=0,maxCommitMs=0,lastAcceptanceMs=0,lastLoadLatencyMs=0;
    unsigned maintenanceRuns=0,maintenanceFailures=0,cacheClears=0;
    unsigned peakResidentCells=0,peakResidentInstances=0;
    double lastMaintenanceMs=0,lastCacheReferenceTime=-1;
    std::string lastMaintenanceError;
    std::map<std::string,double> cacheStats;
    Session(std::unique_ptr<WorldIndex> store,std::unique_ptr<Resources> assets);
    ~Session();
    Session(const Session&)=delete;
    Session& operator=(const Session&)=delete;
    osg::Group* scene()const{return root;}
    const Area& area()const{return *current;}
    bool loading()const{return pendingScene;}
    // Device acceptance runs on the current GL thread BEFORE scene publication.
    // CPU harnesses omit it; CPU completion never implies shader acceptance.
    void update(double now,const Acceptance& accept={},double cacheReferenceTime=-1);
    void shutdown();
    void activate();
    void reset();
    unsigned long long physicsSteps()const{return retiredSteps+current->physics->steps;}
    double droppedPhysicsSeconds()const{return retiredDroppedSeconds+current->physics->droppedSeconds;}
    void memoryWarning(){memoryPressure=true;}
    void suspend(){navigation.suspend();activationQueued=false;}
};
}
