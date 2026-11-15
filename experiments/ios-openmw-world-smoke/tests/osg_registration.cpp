#include <osgDB/Registry>
#include <osgDB/ObjectWrapper>
#include <cstdio>
USE_OSGPLUGIN(dds)
USE_OSGPLUGIN(tga)
USE_OSGPLUGIN(bmp)
USE_OSGPLUGIN(png)
USE_OSGPLUGIN(jpeg)
USE_OSGPLUGIN(osg)
USE_OSGPLUGIN(osg2)
USE_SERIALIZER_WRAPPER_LIBRARY(osg)

// A real link/host-runtime check, not a GPU or device rendering acceptance gate.
int main(){
    auto* registry=osgDB::Registry::instance();
    for(const auto* extension:{"dds","tga","bmp","png","jpeg","osg","osgt"})
        if(!registry->getReaderWriterForExtension(extension)){
            std::fprintf(stderr,"Missing genuine static reader: %s\n",extension);return 1;
        }
    auto* wrapper=registry->getObjectWrapperManager()->findWrapper("osg::BufferIndexBinding");
    if(!wrapper||!wrapper->getSerializer("Target")){
        std::fprintf(stderr,"Missing genuine BufferIndexBinding.Target serializer\n");return 1;
    }
    return 0;
}
