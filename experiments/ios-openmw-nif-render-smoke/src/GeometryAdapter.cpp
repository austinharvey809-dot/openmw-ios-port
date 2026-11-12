#include "GeometryAdapter.hpp"
#include "G1AExpectations.hpp"
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/nif/data.hpp>
#include <components/nif/node.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <osg/Vec3d>
#include <CommonCrypto/CommonDigest.h>
#include <bit>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>

namespace G1A
{
    namespace
    {
        void require(bool value, const char* message)
        {
            if (!value) throw std::runtime_error(message);
        }

        void regular(const std::filesystem::path& path)
        {
            require(std::filesystem::is_regular_file(std::filesystem::symlink_status(path)),
                "Input must be a regular, non-symlink file");
        }

        void identity(const Nif::NiTransform& transform)
        {
            require(transform.isIdentity(), "Unsupported transform");
            // Check every component explicitly, including off-diagonals and NaNs.
            // Never rely on an approximate or incomplete identity predicate.
            require(transform.mScale == 1.f, "Unsupported transform scale");
            for (unsigned row = 0; row < 3; ++row)
            {
                require(transform.mTranslation[row] == 0.f, "Unsupported transform translation");
                for (unsigned col = 0; col < 3; ++col)
                    require(transform.mRotation.mValues[row][col] == (row == col ? 1.f : 0.f),
                        "Unsupported transform rotation");
            }
        }
    }

    std::string sha256(const std::string& bytes)
    {
        require(bytes.size() <= std::numeric_limits<CC_LONG>::max(), "SHA-256 input too large");
        unsigned char digest[CC_SHA256_DIGEST_LENGTH];
        require(CC_SHA256(bytes.data(), static_cast<CC_LONG>(bytes.size()), digest), "SHA-256 failed");
        constexpr char hex[] = "0123456789abcdef";
        std::string result;
        for (unsigned char value : digest)
        {
            result.push_back(hex[value >> 4]);
            result.push_back(hex[value & 15]);
        }
        return result;
    }

    ParsedResource readResource(const std::filesystem::path& fixtures)
    {
        require(std::filesystem::is_directory(fixtures) && !std::filesystem::is_symlink(fixtures),
            "Missing or linked fixture directory");
        for (const char* name : {"valid.esm", "triangle-candidate.bsa", "triangle-candidate.nif"})
            regular(fixtures / name);
        ToUTF8::Utf8Encoder esmEncoder(ToUTF8::WINDOWS_1252);
        const ToUTF8::StatelessUtf8Encoder encoder(ToUTF8::WINDOWS_1252);
        ESM::ESMReader reader;
        reader.setEncoder(&esmEncoder);
        reader.open(fixtures / "valid.esm");
        require(reader.getVer() == ESM::VER_130 && reader.getRecordCount() == 1
            && reader.hasMoreRecs() && reader.getRecName() == "STAT", "Expected one synthetic STAT");
        reader.getRecHeader();
        ESM::Static object;
        bool deleted = false;
        object.load(reader, deleted);
        require(!deleted && !object.mModel.empty() && !reader.hasMoreSubs() && !reader.hasMoreRecs(),
            "Invalid STAT framing/model");
        require(object.mId.getRefIdString() == "eIOSStatic" && object.mModel.getOriginal() == "TeSt.NIF",
            "Unexpected STAT identity");
        const auto key = VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized());
        require(key.view() == "meshes/test.nif", "Unexpected ESM-selected resource");
        VFS::Manager manager;
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, fixtures / "triangle-candidate.bsa", encoder);
        manager.buildIndex();
        require(manager.exists(key), "Missing ESM-selected BSA resource");
        auto stream = manager.get(key);
        const std::string bytes{std::istreambuf_iterator<char>(*stream), std::istreambuf_iterator<char>()};
        const auto digest = sha256(bytes);
        require(digest == ExpectedNifSHA256, "VFS NIF SHA-256 mismatch");
        std::ifstream comparison(fixtures / "triangle-candidate.nif", std::ios::binary);
        require(comparison.good(), "Missing NIF comparator");
        const std::string expected{std::istreambuf_iterator<char>(comparison), std::istreambuf_iterator<char>()};
        require(bytes == expected, "VFS NIF bytes differ from comparator");
        auto file = std::make_unique<Nif::NIFFile>(key);
        Nif::Reader nifReader(*file, &encoder);
        nifReader.parse(manager.get(key)); // A fresh bounded genuine VFS stream, never the comparator.
        return {std::move(file), "eIOSStatic", object.mModel.getOriginal(), std::string(key.view()), digest};
    }

    OwnedGeometry copyGeometry(const Nif::NIFFile& file)
    {
        require(file.mVersion == Nif::NIFFile::VER_MW, "Expected NIF 4.0.0.2");
        require(file.mRecords.size() == 3 && file.mRoots.size() == 1 && file.mRoots[0],
            "Expected three records and one root");
        const auto* root = dynamic_cast<const Nif::NiNode*>(file.mRoots[0]);
        require(root && root == file.mRecords[0].get() && root->mChildren.size() == 1
            && !root->mChildren[0].empty(), "Invalid NiNode relationship");
        const auto* shape = dynamic_cast<const Nif::NiTriShape*>(root->mChildren[0].getPtr());
        require(shape && shape == file.mRecords[1].get() && !shape->mData.empty(),
            "Invalid NiTriShape relationship");
        const auto* data = dynamic_cast<const Nif::NiTriShapeData*>(shape->mData.getPtr());
        require(data && data == file.mRecords[2].get(), "Invalid NiTriShapeData relationship");
        identity(root->mTransform);
        identity(shape->mTransform);
        const auto& positions = data->mVertices;
        const auto& indices = data->mTriangles;
        require(positions.size() == 3 && positions.size() == data->mNumVertices,
            "Expected three consistent vertices");
        require(indices.size() == 3 && indices.size() % 3 == 0 && data->mNumTriangles == 1,
            "Expected one consistent grouped triangle");
        for (const auto& vertex : positions)
            for (unsigned axis = 0; axis < 3; ++axis)
                require(std::isfinite(vertex[axis]), "Nonfinite vertex");
        for (auto index : indices) require(index < positions.size(), "Triangle index out of range");
        require(indices[0] != indices[1] && indices[1] != indices[2] && indices[2] != indices[0],
            "Repeated triangle index");
        const osg::Vec3d a(positions[indices[0]]), b(positions[indices[1]]), c(positions[indices[2]]);
        const auto area = ((b - a) ^ (c - a)).length2();
        require(std::isfinite(area) && area > 0., "Degenerate triangle");

        OwnedGeometry result;
        result.positions = positions;
        result.indices = indices;
        osg::ref_ptr<osg::Vec3Array> vertices = new osg::Vec3Array;
        vertices->assign(result.positions.begin(), result.positions.end());
        osg::ref_ptr<osg::DrawElementsUShort> triangles = new osg::DrawElementsUShort(GL_TRIANGLES);
        triangles->assign(result.indices.begin(), result.indices.end());
        result.drawable = new osg::Geometry;
        result.drawable->setVertexArray(vertices.get());
        result.drawable->addPrimitiveSet(triangles.get());
        result.drawable->setUseDisplayList(false);
        result.drawable->setUseVertexBufferObjects(true);
        result.drawable->setUseVertexArrayObject(true);
        result.geode = new osg::Geode;
        result.geode->addDrawable(result.drawable.get());
        return result;
    }

    std::string geometrySHA256(const OwnedGeometry& geometry)
    {
        static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
        std::string bytes = "G1A-geometry-v1";
        const auto append = [&bytes](std::uint32_t value, unsigned width) {
            for (unsigned i = 0; i < width; ++i) bytes.push_back(static_cast<char>((value >> (8 * i)) & 255));
        };
        append(static_cast<std::uint32_t>(geometry.positions.size()), 4);
        append(static_cast<std::uint32_t>(geometry.indices.size()), 4);
        for (const auto& vertex : geometry.positions)
            for (unsigned axis = 0; axis < 3; ++axis) append(std::bit_cast<std::uint32_t>(vertex[axis]), 4);
        for (auto index : geometry.indices) append(index, 2);
        return sha256(bytes);
    }
}
