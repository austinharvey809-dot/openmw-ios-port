// Executable native tests: no assert(), so Release builds cannot disable checks.
#include "GeometryAdapter.hpp"
#include <components/nif/data.hpp>
#include <components/nif/node.hpp>
#include <algorithm>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace
{
    void check(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }
    Nif::NiNode& root(Nif::NIFFile& file) { return dynamic_cast<Nif::NiNode&>(*file.mRecords.at(0)); }
    Nif::NiTriShape& shape(Nif::NIFFile& file) { return dynamic_cast<Nif::NiTriShape&>(*file.mRecords.at(1)); }
    Nif::NiTriShapeData& data(Nif::NIFFile& file)
    {
        return dynamic_cast<Nif::NiTriShapeData&>(*file.mRecords.at(2));
    }
    void inspectOwned(const G1A::OwnedGeometry& owned)
    {
        const std::vector<osg::Vec3f> expected{{0, 0, 0}, {1, 0, 0}, {0, 1, 0}};
        const std::vector<unsigned short> indices{0, 1, 2};
        check(owned.positions == expected && owned.indices == indices, "Fixture geometry differs");
        check(owned.geode.valid() && owned.geode->getNumDrawables() == 1
            && owned.geode->getDrawable(0) == owned.drawable.get(), "Invalid owned Geode");
        check(owned.drawable->getNumPrimitiveSets() == 1, "Expected one primitive set");
        const auto* array = dynamic_cast<const osg::Vec3Array*>(owned.drawable->getVertexArray());
        const auto* primitive = dynamic_cast<const osg::DrawElementsUShort*>(owned.drawable->getPrimitiveSet(0));
        check(array && array->size() == expected.size()
            && std::equal(array->begin(), array->end(), expected.begin()), "OSG vertices differ");
        check(primitive && primitive->getMode() == GL_TRIANGLES && primitive->size() == 3
            && std::equal(primitive->begin(), primitive->end(), indices.begin()), "OSG primitive differs");
        check(!owned.drawable->getUseDisplayList() && owned.drawable->getUseVertexBufferObjects()
            && owned.drawable->getUseVertexArrayObject(), "Wrong VBO/VAO representation");
        const auto& bound = owned.drawable->getBoundingBox();
        check(bound.valid() && bound.xMin() == 0.f && bound.xMax() == 1.f
            && bound.yMin() == 0.f && bound.yMax() == 1.f && bound.zMin() == 0.f && bound.zMax() == 0.f,
            "Decoded OSG bounds differ");
    }
}

int main(int argc, char** argv)
{
    try
    {
        check(argc == 2, "Usage: openmw-nif-geometry-check fixture-directory");
        const auto fixtures = std::filesystem::path(argv[1]);
        auto parsed = G1A::readResource(fixtures);
        auto owned = G1A::copyGeometry(*parsed.file);
        const auto& source = data(*parsed.file);
        check(owned.positions == source.mVertices && owned.indices == source.mTriangles,
            "Source-to-adapter values differ");
        check(owned.positions.data() != source.mVertices.data() && owned.indices.data() != source.mTriangles.data(),
            "Adapter aliases parser memory");
        const auto* osgVertices = dynamic_cast<const osg::Vec3Array*>(owned.drawable->getVertexArray());
        const auto* osgIndices = dynamic_cast<const osg::DrawElementsUShort*>(owned.drawable->getPrimitiveSet(0));
        check(osgVertices && osgIndices && osgVertices->size() == source.mVertices.size()
            && osgIndices->size() == source.mTriangles.size()
            && std::equal(osgVertices->begin(), osgVertices->end(), source.mVertices.begin())
            && std::equal(osgIndices->begin(), osgIndices->end(), source.mTriangles.begin()),
            "Source-to-OSG values differ");
        check(&(*osgVertices)[0] != source.mVertices.data() && &(*osgIndices)[0] != source.mTriangles.data(),
            "OSG aliases parser memory");
        const auto digest = G1A::geometrySHA256(owned);
        data(*parsed.file).mVertices.clear();
        data(*parsed.file).mTriangles.clear();
        parsed.file.reset();
        inspectOwned(owned); // Evaluate actual arrays and lazy bounds after parser destruction.
        check(G1A::geometrySHA256(owned) == digest, "Geometry changed after parser release");

        std::vector<std::string> rejected;
        const auto reject = [&](const char* name, const char* diagnostic,
                                const std::function<void(Nif::NIFFile&)>& mutate) {
            auto candidate = G1A::readResource(fixtures); // Start with a genuine parse for every mutation.
            mutate(*candidate.file);
            try { (void)G1A::copyGeometry(*candidate.file); }
            catch (const std::runtime_error& error)
            {
                check(std::string(error.what()).find(diagnostic) != std::string::npos,
                    "Negative failed at the wrong validation gate");
                rejected.emplace_back(name);
                return;
            }
            throw std::runtime_error(std::string("Invalid geometry accepted: ") + name);
        };
        reject("vertex-count", "vertices", [](auto& f) { data(f).mVertices.pop_back(); });
        reject("vertex-metadata", "vertices", [](auto& f) { data(f).mNumVertices = 4; });
        reject("triangle-grouping", "triangle", [](auto& f) { data(f).mTriangles.pop_back(); });
        reject("triangle-metadata", "triangle", [](auto& f) { data(f).mNumTriangles = 2; });
        reject("nonfinite-nan", "Nonfinite", [](auto& f) { data(f).mVertices[0].x() = std::numeric_limits<float>::quiet_NaN(); });
        reject("nonfinite-infinity", "Nonfinite", [](auto& f) { data(f).mVertices[0].y() = std::numeric_limits<float>::infinity(); });
        reject("index-range", "out of range", [](auto& f) { data(f).mTriangles[2] = 3; });
        reject("repeated-index", "Repeated", [](auto& f) { data(f).mTriangles[2] = 1; });
        reject("collinear", "Degenerate", [](auto& f) { data(f).mVertices[2] = osg::Vec3f(2, 0, 0); });
        reject("root-translation", "transform", [](auto& f) { root(f).mTransform.mTranslation.x() = 1; });
        reject("shape-scale", "transform", [](auto& f) { shape(f).mTransform.mScale = 2; });
        reject("root-offdiagonal", "transform", [](auto& f) { root(f).mTransform.mRotation.mValues[0][1] = .25f; });
        reject("shape-rotation", "transform", [](auto& f) { shape(f).mTransform.mRotation.mValues[0][0] = 0; });
        reject("nan-transform", "transform", [](auto& f) { shape(f).mTransform.mScale = std::numeric_limits<float>::quiet_NaN(); });
        reject("wrong-version", "4.0.0.2", [](auto& f) { f.mVersion = 0; });
        reject("missing-root", "one root", [](auto& f) { f.mRoots.clear(); });
        reject("wrong-root-type", "NiNode", [](auto& f) { f.mRoots[0] = f.mRecords[1].get(); });
        reject("missing-child", "NiNode", [](auto& f) { root(f).mChildren.clear(); });
        reject("missing-data-reference", "NiTriShape", [](auto& f) { shape(f).mData = Nif::NiGeometryDataPtr(nullptr); });
        reject("missing-record", "three records", [](auto& f) { f.mRecords.pop_back(); });
        std::cout << "{\"status\":\"PASS\",\"scope\":\"structural OSG geometry; no GPU rendering\","
            << "\"object_id\":\"" << parsed.objectId << "\",\"model\":\"" << parsed.model
            << "\",\"resource_key\":\"" << parsed.resourceKey << "\",\"resource_sha256\":\"" << parsed.resourceSHA256
            << "\",\"geometry_sha256\":\"" << digest << "\",\"records\":3,\"roots\":1,\"geometry\":1,"
            << "\"vertices\":3,\"triangles\":1,\"source_equivalence\":true,\"parser_released\":true,"
            << "\"negative_cases\":[";
        for (std::size_t i = 0; i < rejected.size(); ++i)
            std::cout << (i ? "," : "") << '"' << rejected[i] << '"';
        std::cout << "]}\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << "FAIL G1A geometry: " << error.what() << '\n';
        return 1;
    }
}
