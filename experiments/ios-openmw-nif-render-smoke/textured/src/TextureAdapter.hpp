#pragma once
#include "GeometryAdapter.hpp"
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <components/resource/cachestats.hpp>
#include <osg/Image>
#include <osg/Texture2D>

namespace G1C
{
    struct Parsed
    {
        ToUTF8::StatelessUtf8Encoder encoder{ToUTF8::WINDOWS_1252};
        VFS::Manager vfs;
        std::unique_ptr<Nif::NIFFile> file;
        std::string nifSHA256;
    };
    struct Scene
    {
        G1A::OwnedGeometry geometry;
        std::vector<osg::Vec2f> uv;
        osg::Vec4f diffuse;
        osg::ref_ptr<osg::Image> image;
        osg::ref_ptr<osg::Texture2D> texture;
        std::string nifSHA256, textureSHA256, pixelsSHA256, textureKey;
        Resource::CacheStats cacheStats;
    };
    std::unique_ptr<Parsed> read(const std::filesystem::path& directory,
        const std::string& archive, const std::string& expectedNifSHA256);
    // Consumes ownership of the three genuine geometry records after copying property data.
    Scene convert(Parsed& parsed, const std::string& expectedTextureSHA256);
    Scene load(const std::filesystem::path& directory, const std::string& archive,
        const std::string& expectedNifSHA256, const std::string& expectedTextureSHA256);
}
