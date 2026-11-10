// Genuine high-level STAT loading and VFS streams. Synthetic bytes are NOT NIF data.
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>

#include <bit>
#include <filesystem>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>

namespace
{
    const std::string basePayload("\x00OMW-E\xff\n\x00synthetic-model", 24);
    const std::string overlayPayload("Override-E\x00\xfe", 12);

    void require(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }

    void load(ESM::ESMReader& reader, ESM::Static& object, bool& deleted,
        const std::filesystem::path& file, bool esp, bool normalizedVariant)
    {
        reader.open(file); // Genuine path API; no writer and no substituted reader.
        require(reader.getVer() == ESM::VER_130, "TES3 version mismatch");
        require(reader.getHeader().mData.type == (esp ? 0 : 1), "TES3 kind mismatch");
        require(reader.getRecordCount() == 1, "Synthetic header record count mismatch");
        if (!reader.hasMoreRecs()) throw std::runtime_error("fixture: missing STAT record");
        require(reader.getRecName() == "STAT", "Record is not STAT");
        reader.getRecHeader();
        object.load(reader, deleted);
        require(!reader.hasMoreSubs() && !reader.hasMoreRecs(), "Unexpected trailing data");
        require(reader.getFileOffset() == std::filesystem::file_size(file), "STAT traversal boundary mismatch");
        require(object.mRecordFlags == 0, "STAT flags mismatch");
        require(object.mId == std::string_view("eiosstatic") && object.mId.getRefIdString() == "eIOSStatic",
            "High-level NAME/RefId extraction mismatch");
        if (deleted) throw std::runtime_error("fixture: deleted STAT is not a resource request");
        if (object.mModel.empty()) throw std::runtime_error("fixture: STAT has no model");
        require(object.mModel.getOriginal() == (normalizedVariant ? R"(\\TeSt.NIF)" : "TeSt.NIF"),
            "High-level MODL extraction mismatch");
        require(object.mModel.getNormalized().view() == "test.nif", "MODL normalization mismatch");
    }

    void checkBytes(std::istream& stream, const std::string& expected)
    {
        std::string bytes(expected.size() + 8, '?');
        stream.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        require(stream.gcount() == static_cast<std::streamsize>(expected.size()), "Resource bounds mismatch");
        require(bytes.substr(0, expected.size()) == expected, "Resource payload mismatch");
        require(bytes.substr(expected.size()) == std::string(8, '?'), "Read crossed entry boundary");
        stream.clear();
        stream.seekg(static_cast<std::streamoff>(expected.size() + 1));
        require(stream.fail(), "Out-of-range seek unexpectedly succeeded");
        stream.clear();
        stream.seekg(-1, std::ios::end);
        require(stream.get() == static_cast<unsigned char>(expected.back()), "End-relative seek failed");
        require(stream.get() == std::char_traits<char>::eof(), "Resource EOF leaked adjacent data");
        stream.clear();
        stream.seekg(0);
        const std::string again{std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
        require(again == expected, "Resource rewind/read mismatch");
    }

    void resolve(const ESM::Static& object, const std::filesystem::path& base,
        const std::filesystem::path& overlay, const ToUTF8::StatelessUtf8Encoder& encoder,
        std::string_view mode)
    {
        // Explicit mesh-category policy using the public VFS API. Matches the
        // prefix used by ResourceHelpers::correctMeshPath; that larger TU is NOT linked.
        const auto key = VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized());
        require(key.view() == "meshes/test.nif", "Model-category resource key mismatch");
        Files::IStreamPtr afterDestruction;
        const std::string& expected = mode == "base-first" ? overlayPayload : basePayload;
        {
            VFS::Manager manager;
            if (mode == "overlay-first") OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, overlay, encoder);
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, base, encoder);
            require(!manager.exists(key), "Registration unexpectedly built index");
            if (mode == "base-first") OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, overlay, encoder);
            manager.buildIndex();
            if (mode == "missing-resource")
            {
                require(!manager.exists(key) && !manager.find(VFS::Path::NormalizedView(key)), "Missing resource exists");
                bool rejected = false;
                try { auto stream = manager.get(key); }
                catch (const std::runtime_error& error)
                {
                    rejected = std::string_view(error.what()) == "Resource 'meshes/test.nif' not found";
                }
                require(rejected, "Missing get did not fail as expected");
                std::cout << "PASS missing-resource\n";
                return;
            }
            auto retained = manager.get(key);
            checkBytes(*retained, expected);
            retained->clear();
            retained->seekg(0);
            manager.reset();
            require(!manager.exists(key), "Manager reset failed");
            checkBytes(*retained, expected); // Open stream survives archive destruction.
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager,
                mode == "base-first" ? overlay : base, encoder);
            manager.buildIndex();
            afterDestruction = manager.get(key);
        }
        checkBytes(*afterDestruction, expected);
        std::cout << "PASS resource: genuine STAT -> original BSA/VFS; synthetic bytes only\n";
    }
}

int main(int argc, char** argv)
{
    static_assert(std::endian::native == std::endian::little, "TES3/BSA fixture requires native little-endian words");
    try
    {
        require(argc == 5, "Usage: openmw-esm-vfs-check mode existing.esm base.bsa overlay.bsa");
        const std::string_view mode(argv[1]);
        const std::filesystem::path esm(argv[2]), base(argv[3]), overlay(argv[4]);
        ToUTF8::Utf8Encoder esmEncoder(ToUTF8::WINDOWS_1252);
        const ToUTF8::StatelessUtf8Encoder archiveEncoder(ToUTF8::WINDOWS_1252);
        ESM::ESMReader reader;
        reader.setEncoder(&esmEncoder);
        ESM::Static object;
        bool deleted = false;
        if (mode == "missing-esm")
        {
            require(!std::filesystem::exists(esm), "Missing ESM sentinel exists");
            bool rejected = false;
            try { reader.open(esm); }
            catch (const std::system_error&) { rejected = true; }
            require(rejected && !std::filesystem::exists(esm), "Missing ESM was accepted/created");
            std::cout << "PASS missing-esm\n";
            return 0;
        }
        require(std::filesystem::is_regular_file(esm), "ESM must already exist");
        if (mode == "reject-esm" || mode == "missing-record" || mode == "reject-policy")
        {
            bool rejected = false;
            try { load(reader, object, deleted, esm, false, false); }
            catch (const std::runtime_error& error)
            {
                const std::string_view message(error.what());
                rejected = mode == "reject-esm" ? message.starts_with("ESM Error: ")
                    : mode == "missing-record" ? message == "fixture: missing STAT record"
                    : message == "fixture: deleted STAT is not a resource request" || message == "fixture: STAT has no model";
                if (!rejected) throw;
            }
            require(rejected, "Expected ESM/policy rejection did not occur");
            std::cout << "PASS " << mode << '\n';
            return 0;
        }
        load(reader, object, deleted, esm, mode == "esp", mode == "normalized");
        if (mode == "reject-archive")
        {
            VFS::Manager manager;
            bool rejected = false;
            try { OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, base, archiveEncoder); }
            catch (const std::runtime_error& error)
            {
                if (!std::string_view(error.what()).starts_with("BSA input must be")) throw;
                rejected = true;
            }
            require(rejected, "Expected existing-file/original-format rejection did not occur");
            std::cout << "PASS reject-archive\n";
            return 0;
        }
        require(mode == "read" || mode == "esp" || mode == "normalized" || mode == "base-first"
            || mode == "overlay-first" || mode == "missing-resource", "Unknown fixture mode");
        resolve(object, base, overlay, archiveEncoder, mode);
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
