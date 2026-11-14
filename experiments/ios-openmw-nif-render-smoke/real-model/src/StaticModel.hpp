#pragma once
#include "GeometryAdapter.hpp"
#include <osg/Group>
#include <filesystem>
namespace G1D {
struct Model { osg::ref_ptr<osg::Group> scene; unsigned vertices=0,triangles=0,shapes=0; std::string resourceKey; std::vector<std::string> textureKeys; };
Model load(const std::filesystem::path& directory,const std::string& objectId);
}
