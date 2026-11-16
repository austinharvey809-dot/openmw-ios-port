#include "World.hpp"
#include "SceneAudit.hpp"
#include <osg/MatrixTransform>
#include <osgDB/Registry>
#include <algorithm>
#include <cstdio>
#include <iostream>
USE_OSGPLUGIN(dds)
USE_OSGPLUGIN(tga)
USE_OSGPLUGIN(bmp)
USE_OSGPLUGIN(png)
USE_OSGPLUGIN(jpeg)
USE_OSGPLUGIN(osg)
USE_SERIALIZER_WRAPPER_LIBRARY(osg)

namespace {
unsigned checks = 0;
void require(bool value, const char* reason) {
    ++checks; std::fprintf(stderr, "G6 render assertion=%u result=%s\n", checks, value ? "PASS" : "FAIL");
    if (!value) throw std::runtime_error(reason);
}
struct Placement : osg::NodeVisitor {
    std::string name;
    osg::Vec3d expected;
    bool found = false;
    Placement(std::string value, osg::Vec3d position)
        : NodeVisitor(TRAVERSE_ALL_CHILDREN), name(std::move(value)), expected(position) {}
    void apply(osg::MatrixTransform& node) override {
        if (node.getName() == name && (node.getMatrix().getTrans() - expected).length() < 1e-5) found = true;
        traverse(node);
    }
};
}
int main(int argc, char** argv) {
    auto* original = std::cout.rdbuf(std::cerr.rdbuf());
    try {
        if (argc != 4) throw std::runtime_error("authored-directory shaders defaults required");
        const std::filesystem::path directory = argv[1];
        G6::LiveWorld world({directory / "Morrowind.esm"}, argv[3]);
        G6::Resources assets({{directory / "Morrowind.bsa"}, {}}, argv[2]);
        auto initial = G6::prepare(world, assets, {});
        require(initial->cells == 9 && initial->instances == 10, "Genuine authored scene inventory mismatch");
        G6::SceneAudit audit; initial->scene->accept(audit);
        require(audit.geometry > 0 && !audit.programs.empty(), "Genuine NifOsg geometry/program graph absent");
        const auto& cell = *world.cells.find(-2, -9);
        const auto values = world.objects(cell);
        const auto object = std::find_if(values.begin(), values.end(), [](const auto& value) {
            return value.reference.mRefNum.mIndex == 5;
        });
        require(object != values.end(), "Canonical live floor reference missing");
        const auto handle = object->handle;
        world.setEnabled(handle, false);
        auto disabled = G6::prepare(world, assets, {});
        require(disabled->instances + 1 == initial->instances, "Renderer ignored genuine RefData enable state");
        require(initial->instances == 10, "Preparing a new scene mutated the old graph");
        disabled.reset(); world.setEnabled(handle, true);
        auto position = object->reference.mPos; position.pos[0] += 64; position.rot[2] += .5f;
        world.setPosition(handle, position);
        auto changed = G6::prepare(world, assets, {});
        Placement placement(object->reference.mRefID.toDebugString(), {position.pos[0], position.pos[1], position.pos[2]});
        changed->scene->accept(placement);
        require(placement.found, "Actual OSG placement did not come from live RefData");
        require(world.diagnostics().successfulLoads == 9, "Scene preparation reloaded or duplicated canonical cells");
        const auto registered = world.diagnostics().registeredObjects;
        initial.reset(); assets.expire(1000); changed.reset();
        require(world.diagnostics().registeredObjects == registered, "Retiring geometry discarded genuine live state");
        require(world.inspect(handle).reference.mPos.pos[0] == position.pos[0], "Live state did not survive scene retirement");
        world.clear(); require(world.diagnostics().registeredObjects == 0, "Explicit world retirement retained registry objects");
        std::cout.rdbuf(original); std::printf("{\"status\":\"PASS\",\"checks\":%u,\"scope\":\"CPU genuine live ownership to NifOsg graph; no GPU execution\"}\n", checks); return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "G6 render checks_completed=%u: %s\n", checks, error.what());
        std::cout.rdbuf(original); return 1;
    }
}
