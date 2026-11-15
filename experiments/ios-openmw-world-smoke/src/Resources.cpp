#include "Resources.hpp"
#include <components/misc/osguservalues.hpp>
#include <components/misc/resourcehelpers.hpp>
#include <components/resource/imagemanager.hpp>
#include <components/resource/niffilemanager.hpp>
#include <components/resource/scenemanager.hpp>
#include <components/shader/shadermanager.hpp>
#include <components/vfs/filesystemarchive.hpp>
#include <experiments/ios-openmw-bsa-vfs/src/register_bsa.hpp>
#include <osg/NodeVisitor>
#include <osg/Drawable>
#include <osg/StateSet>
#include <osg/Texture>
#include <osg/Stats>
#include <osgDB/Registry>
#include <cmath>
#include <stdexcept>

#ifdef OSG_LIBRARY_STATIC
// ImageManager already forces the six legacy image readers. The separately
// compiled osg2 translation unit also needs a reference in a static executable.
USE_OSGPLUGIN(osg2)
#endif

namespace G4 {
namespace {
struct CheckImages : osg::NodeVisitor {
    osg::Image* warning;
    explicit CheckImages(osg::Image* value):NodeVisitor(TRAVERSE_ALL_CHILDREN),warning(value){}
    void check(osg::StateSet* state){
        if(!state)return;
        for(unsigned unit=0;unit<state->getTextureAttributeList().size();++unit){
            auto* texture=dynamic_cast<osg::Texture*>(state->getTextureAttribute(unit,osg::StateAttribute::TEXTURE));
            if(!texture)continue;
            for(unsigned image=0;image<texture->getNumImages();++image){
                auto* data=texture->getImage(image);
                if(!data || data==warning || !data->data() || data->s()<=0 || data->t()<=0)
                    throw std::runtime_error("G4 upstream image fallback or invalid image at texture unit "+std::to_string(unit));
            }
        }
    }
    void apply(osg::Node& node)override{check(node.getStateSet());traverse(node);}
    void apply(osg::Drawable& node)override{check(node.getStateSet());}
};
}
Resources::Resources(const ResourcePaths& paths,const std::filesystem::path& shaders):system(&vfs,5,&encoder){
    for(const auto& archive:paths.archives)OpenMWIOSBsaVfs::addExistingMorrowindBSA(vfs,archive,encoder);
    for(const auto& directory:paths.looseDirectories){
        if(!std::filesystem::is_directory(directory))throw std::runtime_error("G4 loose resource directory is missing");
        vfs.addArchive(std::make_unique<VFS::FileSystemArchive>(directory));
    }
    vfs.buildIndex();
    system.setExpiryDelay(5);
    collision=std::make_unique<Resource::BulletShapeManager>(&vfs,system.getSceneManager(),system.getNifFileManager(),5);
    system.addResourceManager(collision.get());
    auto* scenes=system.getSceneManager();scenes->setShaderPath(shaders);
    scenes->setSupportsNormalsRT(false);
    auto defines=Shader::getDefaultDefines();
    defines["forcePPL"]="1";defines["simpleLighting"]="0";defines["maxLights"]="8";
    defines["lightingMethodClustered"]="0";defines["shadows_enabled"]="0";
    defines["disableNormals"]="1";
    defines["shadow_texture_unit_list"]="";defines["useShadowDebugOverlay"]="0";
    defines["perspectiveShadowMaps"]="0";defines["disableNormalOffsetShadows"]="0";
    defines["shadowNormalOffset"]="0.0";defines["limitShadowMapDistance"]="0";
    scenes->getShaderManager().setGlobalDefines(defines);
    scenes->setUnRefImageDataAfterApply(false); // Retain data until context-loss policy is physically verified.
}
Resources::~Resources(){system.removeResourceManager(collision.get());}
osg::ref_ptr<osg::Node> Resources::instance(const std::string& model){
    std::lock_guard registry(CapabilityRegistryMutex);
    try{
        const auto path=Misc::ResourceHelpers::correctMeshPath(VFS::Path::Normalized(model));
        if(!path.value().ends_with(".nif"))throw std::runtime_error("Only genuine NIF model resources are accepted");
        // The upstream scene loader catches failures and draws marker_error. Require
        // the genuine source hash so that fallback cannot satisfy our success gate.
        const auto parsed=system.getNifFileManager()->get(path);
        const auto scene=system.getSceneManager()->getTemplate(path,false);
        std::string actual;
        if(!scene || !scene->getUserValue(Misc::OsgUserValues::sFileHash,actual) || actual!=parsed->mHash)
            throw std::runtime_error("SceneManager source hash mismatch/error-marker fallback");
        CheckImages check(system.getImageManager()->getWarningImage());const_cast<osg::Node*>(scene.get())->accept(check);
        return system.getSceneManager()->getInstance(scene.get());
    }catch(const std::exception& e){throw std::runtime_error("G4 stage=ResourceSystem/SceneManager/NifOsg model="+model+": "+e.what());}
}
void Resources::expire(double referenceTime){
    if(!std::isfinite(referenceTime)||referenceTime<0)throw std::runtime_error("G4 invalid cache reference time");
    system.updateCache(referenceTime);
}
std::map<std::string,double> Resources::statistics()const{
    osg::ref_ptr<osg::Stats> stats=new osg::Stats("G4 resource caches");
    system.reportStats(0,stats);
    return stats->getAttributeMap(0);
}
}
