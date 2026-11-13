#include "TextureAdapter.hpp"
#include <components/nif/data.hpp>
#include <components/nif/property.hpp>
#include <components/nif/texture.hpp>
#include <algorithm>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
void check(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
template<class T> T& record(G1C::Parsed& p, unsigned index) {
    auto* value = dynamic_cast<T*>(p.file->mRecords.at(index).get());
    check(value != nullptr, "Missing genuine test record"); return *value;
}
}
int main(int argc, char** argv) {
    try {
        check(argc == 5, "Usage: openmw-textured-nif-check directory archive nif-sha256 texture-sha256");
        const std::filesystem::path directory(argv[1]);
        const std::string archive(argv[2]), nifSHA(argv[3]), textureSHA(argv[4]);
        auto parsed = G1C::read(directory, archive, nifSHA);
        const auto& source = record<Nif::NiTriShapeData>(*parsed, 2);
        const auto positions = source.mVertices;
        const auto triangles = source.mTriangles;
        const auto uv = source.mUVList;
        const auto diffuse = record<Nif::NiMaterialProperty>(*parsed, 5).mDiffuse;
        auto result = G1C::convert(*parsed, textureSHA);
        check(result.geometry.positions == positions && result.geometry.indices == triangles
            && result.uv == uv.at(0) && result.diffuse == osg::Vec4f(diffuse, 1), "Source equivalence failed");
        const auto* array = dynamic_cast<const osg::Vec2Array*>(result.geometry.drawable->getVertexAttribArray(6));
        check(array && std::equal(array->begin(), array->end(), uv.at(0).begin(), uv.at(0).end())
            && &(*array)[0] != uv.at(0).data(), "UV array ownership/equivalence failed");
        const auto* colors = dynamic_cast<const osg::Vec4Array*>(result.geometry.drawable->getColorArray());
        check(colors && colors->size() == 3 && std::all_of(colors->begin(), colors->end(),
            [&](const auto& color) { return color == result.diffuse; }), "OSG decoded material differs");
        parsed.reset(); // Destroy all parser records, encoder and VFS; converter already cleared its real cache.
        check(result.image.valid() && result.texture->getImage() == result.image.get()
            && result.image->data()[0] == 255 && result.image->data()[1] == 32
            && result.geometry.drawable->getBoundingBox().valid(), "Owned scene invalid after resource release");
        check(result.texture->getFilter(osg::Texture::MIN_FILTER) == osg::Texture::NEAREST
            && result.texture->getFilter(osg::Texture::MAG_FILTER) == osg::Texture::NEAREST
            && result.texture->getWrap(osg::Texture::WRAP_S) == osg::Texture::CLAMP_TO_EDGE
            && result.texture->getWrap(osg::Texture::WRAP_T) == osg::Texture::CLAMP_TO_EDGE
            && !result.texture->getUseHardwareMipMapGeneration(), "OSG sampler differs from decoded policy");
        const auto geometrySHA = G1A::geometrySHA256(result.geometry);
        unsigned negatives = 0;
        if (archive == "textured.bsa") {
            const auto reject = [&](const char* diagnostic, const std::function<void(G1C::Parsed&)>& mutate) {
                auto candidate = G1C::read(directory, archive, nifSHA);
                mutate(*candidate);
                try { (void)G1C::convert(*candidate, textureSHA); }
                catch (const std::exception& error) {
                    check(std::string(error.what()).find(diagnostic) != std::string::npos,
                        "Negative failed at wrong gate"); ++negatives; return;
                }
                throw std::runtime_error("Invalid textured record accepted");
            };
            reject("UV set", [](auto& p) { record<Nif::NiTriShapeData>(p, 2).mUVList.clear(); });
            reject("UV set", [](auto& p) { record<Nif::NiTriShapeData>(p, 2).mUVList[0].pop_back(); });
            reject("UV coordinate", [](auto& p) { record<Nif::NiTriShapeData>(p, 2).mUVList[0][0].x() = -1; });
            reject("UV coordinate", [](auto& p) { record<Nif::NiTriShapeData>(p, 2).mUVList[0][0].y() = std::numeric_limits<float>::infinity(); });
            reject("sampler", [](auto& p) { record<Nif::NiTexturingProperty>(p, 3).mTextures[0].mFilter = 1; });
            reject("sampler", [](auto& p) { record<Nif::NiTexturingProperty>(p, 3).mTextures[0].mUVSet = 1; });
            reject("diffuse/alpha", [](auto& p) { record<Nif::NiMaterialProperty>(p, 5).mDiffuse.x() = std::numeric_limits<float>::quiet_NaN(); });
            reject("opaque", [](auto& p) { record<Nif::NiMaterialProperty>(p, 5).mAlpha = .5f; });
            reject("Unsafe texture", [](auto& p) { record<Nif::NiSourceTexture>(p, 4).mFile = "/private.tga"; });
            reject("mipmaps", [](auto& p) { record<Nif::NiSourceTexture>(p, 4).mPrefs.mUseMipMaps = Nif::NiSourceTexture::MipMapFormat::Yes; });
            reject("out of range", [](auto& p) { record<Nif::NiTriShapeData>(p, 2).mTriangles[2] = 3; });
        }
        std::cout << "{\"status\":\"PASS\",\"source_equivalence\":true,\"parser_vfs_cache_released\":true,"
            << "\"negative_cases\":" << negatives << ",\"vertices\":3,\"triangles\":1,\"uv_sets\":1,"
            << "\"cache_hits\":" << result.cacheStats.mHit << ",\"geometry_sha256\":\"" << geometrySHA
            << "\",\"pixels_sha256\":\"" << result.pixelsSHA256 << "\",\"texture_key\":\"" << result.textureKey
            << "\",\"scope\":\"CPU parsing/resource/owned OSG data; no GPU claim\"}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << "FAIL G1C: " << error.what() << '\n'; return 1; }
}
