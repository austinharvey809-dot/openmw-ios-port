#include "TextureAdapter.hpp"
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/misc/resourcehelpers.hpp>
#include <components/resource/objectcache.hpp>
#include <components/nif/node.hpp>
#include <components/nif/data.hpp>
#include <components/nif/property.hpp>
#include <components/nif/texture.hpp>
#include <osg/Uniform>
#include <osgDB/Registry>
#include <osgDB/Options>
#include <algorithm>
#include <cmath>
#include <iterator>
#include <sstream>
#include <stdexcept>

USE_OSGPLUGIN(tga)

namespace G1C
{
    namespace
    {
        void require(bool condition, const char* message)
        {
            if (!condition) throw std::runtime_error(message);
        }
        std::string bytes(VFS::Manager& vfs, VFS::Path::NormalizedView path)
        {
            auto stream = vfs.get(path);
            return {std::istreambuf_iterator<char>(*stream), std::istreambuf_iterator<char>()};
        }
        void safeTextureReference(const std::string& name)
        {
            require(!name.empty() && name.front() != '/' && name.front() != '\\'
                && name.find(':') == std::string::npos && name.find('\0') == std::string::npos,
                "Unsafe texture reference");
            std::string segment;
            for (char c : name + '/')
            {
                if (c == '/' || c == '\\')
                {
                    require(!segment.empty() && segment != "." && segment != "..", "Unsafe texture reference");
                    segment.clear();
                }
                else segment += c;
            }
        }
    }

    std::unique_ptr<Parsed> read(const std::filesystem::path& directory,
        const std::string& archive, const std::string& expectedNifSHA256)
    {
        require(archive.find_first_of("/\\:") == std::string::npos && archive != "..", "Unsafe archive name");
        require(std::filesystem::is_directory(directory) && !std::filesystem::is_symlink(directory),
            "Missing/linked resource directory");
        for (const auto& path : {directory / "textured.esm", directory / archive})
            require(std::filesystem::is_regular_file(std::filesystem::symlink_status(path)), "Missing/nonregular resource input");
        ESM::ESMReader reader;
        ToUTF8::Utf8Encoder esmEncoder(ToUTF8::WINDOWS_1252);
        reader.setEncoder(&esmEncoder);
        reader.open(directory / "textured.esm");
        require(reader.getVer() == ESM::VER_130 && reader.getRecordCount() == 1 && reader.hasMoreRecs()
            && reader.getRecName() == "STAT", "Expected synthetic STAT");
        reader.getRecHeader();
        ESM::Static object;
        bool deleted = false;
        object.load(reader, deleted);
        require(!deleted && !reader.hasMoreSubs() && !reader.hasMoreRecs()
            && object.mId.getRefIdString() == "eIOSStatic" && object.mModel.getOriginal() == "TeXtUrEd.NIF",
            "Unexpected STAT/model identity");
        auto result = std::make_unique<Parsed>();
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(result->vfs, directory / archive, result->encoder);
        result->vfs.buildIndex();
        const auto key = VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized());
        require(key.view() == "meshes/textured.nif", "Unexpected normalized model key");
        const auto data = bytes(result->vfs, key);
        result->nifSHA256 = G1A::sha256(data);
        require(result->nifSHA256 == expectedNifSHA256, "NIF resource SHA-256 mismatch");
        result->file = std::make_unique<Nif::NIFFile>(key);
        Nif::Reader parser(*result->file, &result->encoder);
        try { parser.parse(result->vfs.get(key)); }
        catch (const std::exception& error) {
            throw std::runtime_error(std::string("Genuine NIF parse rejected: ") + error.what());
        }
        return result;
    }

    Scene convert(Parsed& parsed, const std::string& expectedTextureSHA256)
    {
        auto& file = *parsed.file;
        require(file.mVersion == Nif::NIFFile::VER_MW && file.mRecords.size() == 6 && file.mRoots.size() == 1,
            "Expected six-record textured MW NIF");
        auto* root = dynamic_cast<Nif::NiNode*>(file.mRecords[0].get());
        auto* shape = dynamic_cast<Nif::NiTriShape*>(file.mRecords[1].get());
        auto* data = dynamic_cast<Nif::NiTriShapeData*>(file.mRecords[2].get());
        auto* property = dynamic_cast<Nif::NiTexturingProperty*>(file.mRecords[3].get());
        auto* source = dynamic_cast<Nif::NiSourceTexture*>(file.mRecords[4].get());
        auto* material = dynamic_cast<Nif::NiMaterialProperty*>(file.mRecords[5].get());
        require(root && shape && data && property && source && material && file.mRoots[0] == root,
            "Invalid textured record types/root");
        require(shape->mProperties.size() == 2 && !shape->mProperties[0].empty() && !shape->mProperties[1].empty()
            && shape->mProperties[0].getPtr() == property && shape->mProperties[1].getPtr() == material,
            "Invalid material/texturing property relationship");
        require(property->mTextures.size() == 1 && property->mTextures[0].mEnabled
            && property->mApplyMode == Nif::NiTexturingProperty::ApplyMode::Modulate
            && property->mShaderTextures.empty(), "Unsupported base-texture treatment");
        const auto& binding = property->mTextures[0];
        require(!binding.mSourceTexture.empty() && binding.mSourceTexture.getPtr() == source,
            "Invalid source-texture relationship");
        require(binding.mUVSet == 0 && binding.mClamp == 0 && binding.mFilter == 0 && !binding.mHasTransform,
            "Unsupported sampler/UV transform");
        require(source->mExternal == 1 && source->mIsStatic == 1
            && source->mPrefs.mUseMipMaps == Nif::NiSourceTexture::MipMapFormat::No
            && source->mPrefs.mPixelLayout == Nif::NiSourceTexture::PixelLayout::TrueColor
            && source->mPrefs.mAlphaFormat == Nif::NiSourceTexture::AlphaFormat::Smooth,
            "Unsupported texture storage/mipmaps");
        require(data->mUVList.size() == 1 && data->mUVList[0].size() == 3, "Expected one complete UV set");
        Scene result;
        result.uv = data->mUVList[0];
        for (const auto& uv : result.uv)
            for (unsigned i = 0; i < 2; ++i)
                require(std::isfinite(uv[i]) && uv[i] >= 0 && uv[i] <= 1, "Invalid UV coordinate");
        result.diffuse = osg::Vec4f(material->mDiffuse, material->mAlpha);
        for (unsigned i = 0; i < 4; ++i)
            require(std::isfinite(result.diffuse[i]) && result.diffuse[i] >= 0 && result.diffuse[i] <= 1,
                "Invalid diffuse/alpha");
        require(result.diffuse.a() == 1.f, "Only opaque unlit material is supported");
        safeTextureReference(source->mFile);
        const auto key = Misc::ResourceHelpers::correctTexturePath(VFS::Path::Normalized(source->mFile), parsed.vfs);
        result.textureKey = std::string(key.value());
        require(result.textureKey == "textures/patterns/niftest.tga" && parsed.vfs.exists(key), "Missing/unexpected texture resource");
        const auto textureBytes = bytes(parsed.vfs, key);
        result.textureSHA256 = G1A::sha256(textureBytes);
        require(result.textureSHA256 == expectedTextureSHA256, "Texture resource SHA-256 mismatch");
        // Real engine cache + pinned OSG decoder. No warning-image or loose-file fallback.
        Resource::GenericObjectCache<std::string, osg::ref_ptr<osg::Image>> cache;
        const auto image = [&]() -> osg::ref_ptr<osg::Image> {
            if (auto existing = cache.getRefFromObjectCache(result.textureKey)) return existing;
            auto* decoder = osgDB::Registry::instance()->getReaderWriterForExtension("tga");
            require(decoder != nullptr, "Pinned static TGA decoder unavailable");
            std::istringstream input(textureBytes, std::ios::binary);
            osg::ref_ptr<osgDB::Options> options = new osgDB::Options("ignoreTga2Fields");
            auto decoded = decoder->readImage(input, options.get());
            require(decoded.success() && decoded.getImage(), "TGA decode rejected");
            osg::ref_ptr<osg::Image> value = decoded.getImage();
            require(value->s() == 8 && value->t() == 8 && value->r() == 1 && value->getPixelFormat() == GL_RGBA
                && value->getDataType() == GL_UNSIGNED_BYTE && value->getOrigin() == osg::Image::BOTTOM_LEFT
                && value->isDataContiguous() && value->getTotalSizeInBytes() == 256, "Unexpected decoded image layout");
            value->setFileName(result.textureKey);
            cache.addEntryToObjectCache(result.textureKey, value);
            return value;
        };
        result.image = image();
        require(image().get() == result.image.get(), "Engine resource cache did not reuse image");
        result.cacheStats = cache.getStats();
        require(result.cacheStats.mHit == 1 && result.cacheStats.mSize == 1, "Unexpected engine cache statistics");
        cache.clear();
        result.pixelsSHA256 = G1A::sha256(std::string(reinterpret_cast<const char*>(result.image->data()), 256));
        // Project only the actual three geometry records for the unchanged G1A validator.
        // Property/source records stay alive in file until every value has been copied.
        Nif::NIFFile geometry(file.mPath);
        geometry.mVersion = file.mVersion;
        geometry.mRoots = file.mRoots;
        for (unsigned i = 0; i < 3; ++i) geometry.mRecords.push_back(std::move(file.mRecords[i]));
        result.geometry = G1A::copyGeometry(geometry);
        result.nifSHA256 = parsed.nifSHA256;
        osg::ref_ptr<osg::Vec2Array> uv = new osg::Vec2Array;
        uv->assign(result.uv.begin(), result.uv.end());
        result.geometry.drawable->setVertexAttribArray(6, uv.get(), osg::Array::BIND_PER_VERTEX);
        osg::ref_ptr<osg::Vec4Array> colors = new osg::Vec4Array;
        colors->assign(result.geometry.positions.size(), result.diffuse);
        result.geometry.drawable->setColorArray(colors.get(), osg::Array::BIND_PER_VERTEX);
        result.texture = new osg::Texture2D(result.image.get());
        result.texture->setUnRefImageDataAfterApply(false);
        result.texture->setFilter(osg::Texture::MIN_FILTER, osg::Texture::NEAREST);
        result.texture->setFilter(osg::Texture::MAG_FILTER, osg::Texture::NEAREST);
        result.texture->setWrap(osg::Texture::WRAP_S, osg::Texture::CLAMP_TO_EDGE);
        result.texture->setWrap(osg::Texture::WRAP_T, osg::Texture::CLAMP_TO_EDGE);
        result.texture->setUseHardwareMipMapGeneration(false);
        auto* state = result.geometry.geode->getOrCreateStateSet();
        state->setTextureAttribute(0, result.texture.get(), osg::StateAttribute::ON);
        state->addUniform(new osg::Uniform("baseTexture", 0));
        return result;
    }

    Scene load(const std::filesystem::path& directory, const std::string& archive,
        const std::string& expectedNifSHA256, const std::string& expectedTextureSHA256)
    {
        auto parsed = read(directory, archive, expectedNifSHA256);
        return convert(*parsed, expectedTextureSHA256);
    }
}
