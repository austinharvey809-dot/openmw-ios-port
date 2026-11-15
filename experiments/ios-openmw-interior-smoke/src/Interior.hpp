#pragma once
#include <components/resource/objectcache.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <osg/Group>
#include <osg/Image>
#include <osg/Matrix>
#include <osg/Texture2D>
#include <components/esm3/cellref.hpp>
#include <filesystem>
#include <cstdint>
#include <string>
#include <vector>
#include <map>
#include <tuple>

namespace G2 {
inline constexpr char CellName[]="Seyda Neen, Fargoth's House";
struct Model {
    osg::ref_ptr<osg::Group> scene;
    unsigned vertices=0,triangles=0,shapes=0,collisionBranches=0,particleBranches=0;
    std::string resourceKey;
    std::vector<std::string> textureKeys;
    osg::Vec3d lightOffset;
    bool hasLightOffset=false;
};
struct Resources {
    ToUTF8::StatelessUtf8Encoder encoder{ToUTF8::WINDOWS_1252};
    VFS::Manager vfs;
    Resource::GenericObjectCache<std::string,osg::ref_ptr<osg::Image>> images;
    std::map<std::tuple<std::string,std::uint32_t,std::uint32_t>,osg::ref_ptr<osg::Texture2D>> samplers;
    std::size_t decodedBytes=0;
    std::size_t samplerBytes=0;
    explicit Resources(const std::filesystem::path& directory);
};
struct Light {osg::Vec3f position;osg::Vec3f color;float radius;};
struct Environment {
    osg::ref_ptr<osg::Group> scene;
    std::string cell;
    std::vector<std::string> models,textures;
    std::vector<Light> lights;
    osg::Vec3f ambient;
    osg::Vec3d entry;
    double entryYaw=0;
    unsigned references=0,instances=0,markers=0,modelLessLights=0,deletedReferences=0;
    unsigned timeVaryingLights=0,disabledLights=0;
    unsigned vertices=0,triangles=0,shapes=0,collisionBranches=0,particleBranches=0;
    std::size_t decodedBytes=0;
    unsigned samplerCount=0;
    std::size_t samplerBytes=0;
};
osg::Matrix placement(const ESM::CellRef& reference);
Model loadMesh(Resources& resources,const std::string& model);
Environment load(const std::filesystem::path& directory,const std::string& cell=CellName);
}
