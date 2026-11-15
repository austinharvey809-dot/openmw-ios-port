#pragma once
#include <components/resource/resourcesystem.hpp>
#include <components/resource/bulletshapemanager.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <osg/Node>
#include <filesystem>
#include <memory>
#include <mutex>
#include <vector>
#include <map>

namespace G4 {
// Upstream's process-wide GL capability registry is initialized/retired only
// while image loaders are outside it. Ordinary rendering does not take this lock.
inline std::recursive_mutex CapabilityRegistryMutex;
struct ResourcePaths {
    std::vector<std::filesystem::path> archives;
    std::vector<std::filesystem::path> looseDirectories;
};
// Lifetime order matters: upstream managers reference VFS and the encoder.
class Resources {
    ToUTF8::StatelessUtf8Encoder encoder{ToUTF8::WINDOWS_1252};
public:
    VFS::Manager vfs;
    Resource::ResourceSystem system;
    std::unique_ptr<Resource::BulletShapeManager> collision;
    explicit Resources(const ResourcePaths& paths,const std::filesystem::path& shaders);
    ~Resources();
    osg::ref_ptr<osg::Node> instance(const std::string& model);
    void expire(double referenceTime);
    std::map<std::string,double> statistics()const;
};
}
