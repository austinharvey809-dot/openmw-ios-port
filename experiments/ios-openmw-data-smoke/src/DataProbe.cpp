#include "DataProbe.hpp"
#include "FixtureExpectations.hpp"
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <bit>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace OpenMWIOSDataSmoke
{
    namespace
    {
        void require(bool value, const char* message)
        {
            if (!value) throw std::runtime_error(message);
        }
    }

    ProbeResult readResource(const std::filesystem::path& esm, const std::filesystem::path& bsa)
    {
        static_assert(std::endian::native == std::endian::little, "Native TES3/BSA words require little endian");
        require(std::filesystem::is_regular_file(esm) && std::filesystem::is_regular_file(bsa), "Missing bundled fixture");
        // Both real readers borrow their encoders. They must outlive all users.
        ToUTF8::Utf8Encoder esmEncoder(ToUTF8::WINDOWS_1252);
        const ToUTF8::StatelessUtf8Encoder archiveEncoder(ToUTF8::WINDOWS_1252);
        ESM::ESMReader reader;
        reader.setEncoder(&esmEncoder);
        reader.open(esm);
        require(reader.getVer() == ESM::VER_130 && reader.getHeader().mData.type == 1
            && reader.getRecordCount() == 1, "TES3 header mismatch");
        require(reader.hasMoreRecs() && reader.getRecName() == "STAT", "Missing STAT record");
        reader.getRecHeader();
        ESM::Static object;
        bool deleted = false;
        object.load(reader, deleted);
        require(!deleted && !object.mModel.empty(), "Deleted or model-less STAT");
        require(!reader.hasMoreSubs() && !reader.hasMoreRecs() && object.mRecordFlags == 0
            && reader.getFileOffset() == std::filesystem::file_size(esm), "STAT framing mismatch");
        require(object.mId == std::string_view("eiosstatic") && object.mId.getRefIdString() == Expected::ObjectId,
            "STAT ID mismatch");
        require(object.mModel.getOriginal() == Expected::Model, "STAT MODL mismatch");
        const auto key = VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized());
        require(key.view() == Expected::ResourceKey, "Normalized mesh resource key mismatch");
        Files::IStreamPtr resource;
        {
            VFS::Manager manager;
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, bsa, archiveEncoder);
            require(!manager.exists(key), "Index unexpectedly built during registration");
            manager.buildIndex();
            require(manager.exists(key), "Referenced model resource is missing");
            resource = manager.get(key);
        } // The returned stream owns a real constrained file handle.
        std::string bytes(Expected::Payload.size() + 8, '?');
        resource->read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        require(resource->gcount() == static_cast<std::streamsize>(Expected::Payload.size()), "Resource boundary mismatch");
        require(bytes.substr(Expected::Payload.size()) == std::string(8, '?'), "Read crossed resource boundary");
        bytes.resize(Expected::Payload.size());
        const std::string wanted(reinterpret_cast<const char*>(Expected::Payload.data()), Expected::Payload.size());
        require(bytes == wanted, "Resource payload bytes differ");
        resource->clear();
        resource->seekg(-1, std::ios::end);
        require(resource->get() == static_cast<unsigned char>(wanted.back())
            && resource->get() == std::char_traits<char>::eof(), "Bounded resource seek/EOF mismatch");
        return {object.mId.getRefIdString(), object.mModel.getOriginal(), key.value(), std::move(bytes)};
    }
}
