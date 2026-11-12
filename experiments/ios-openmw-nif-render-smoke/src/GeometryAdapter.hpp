#pragma once
#include <components/nif/niffile.hpp>
#include <osg/Geode>
#include <osg/Geometry>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace G1A
{
    struct ParsedResource
    {
        std::unique_ptr<Nif::NIFFile> file;
        std::string objectId, model, resourceKey, resourceSHA256;
    };

    // No pointers or references into ParsedResource/NIFFile are retained here.
    struct OwnedGeometry
    {
        std::vector<osg::Vec3f> positions;
        std::vector<unsigned short> indices;
        osg::ref_ptr<osg::Geometry> drawable;
        osg::ref_ptr<osg::Geode> geode;
    };

    ParsedResource readResource(const std::filesystem::path& fixtures);
    OwnedGeometry copyGeometry(const Nif::NIFFile& file);
    std::string sha256(const std::string& bytes);
    std::string geometrySHA256(const OwnedGeometry& geometry);
}
