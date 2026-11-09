// Genuine BSA/VFS traversal; all archive bytes are original synthetic fixtures.
#include "register_bsa.hpp"

#include <components/files/conversion.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>
#include <components/vfs/recursivedirectoryiterator.hpp>

#include <bit>
#include <filesystem>
#include <iostream>
#include <iterator>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>

namespace
{
    using Payloads = std::map<std::string, std::string>;
    const std::string mesh = "meshes/iosprobe.bin";
    const std::string encodedName = "textures/caf\xc3\xa9x.txt";
    const std::string baseMesh("\x00OMW\xff\nVFS\0", 10);
    const std::string overrideMesh("Override original payload.\x00\xfe", 28);
    const Payloads basePayloads = {
        {mesh, baseMesh},
        {encodedName, "Encoded archive filename; original synthetic bytes.\n"},
        {"docs/onlybase.txt", "Base-only original payload.\n"},
    };

    void require(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }

    std::set<std::string> names(const VFS::Manager& manager)
    {
        std::set<std::string> result;
        for (const auto& path : manager.getRecursiveDirectoryIterator())
            result.insert(path.value());
        return result;
    }

    void checkIndex(const VFS::Manager& manager, const Payloads& expected)
    {
        std::set<std::string> wanted;
        for (const auto& [name, payload] : expected) wanted.insert(name);
        if (names(manager) != wanted)
            throw std::runtime_error("Unexpected or missing synthetic resource table");
    }

    void checkPayload(const VFS::Manager& manager, const std::string& path, const std::string& expected)
    {
        const VFS::Path::Normalized key(path);
        require(manager.exists(key), "Expected resource missing");
        auto stream = manager.get(key);
        // Oversized read must stop exactly at the entry boundary, even though
        // other payloads follow it in the same physical archive.
        std::string buffer(expected.size() + 8, '?');
        stream->read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        require(stream->gcount() == static_cast<std::streamsize>(expected.size()), "Payload range length mismatch");
        require(buffer.substr(0, expected.size()) == expected, "Payload bytes differ");
        require(buffer.substr(expected.size()) == std::string(8, '?'), "Archive stream crossed payload boundary");
        stream->clear();
        stream->seekg(static_cast<std::streamoff>(expected.size() + 1));
        require(stream->fail(), "Out-of-range archive seek should fail");
        stream->clear();
        stream->seekg(-1, std::ios::end);
        require(stream->get() == static_cast<unsigned char>(expected.back()), "Seek from entry end failed");
        require(stream->get() == std::char_traits<char>::eof(), "Entry EOF leaked adjacent bytes");
    }

    void requireMissing(const VFS::Manager& manager, const VFS::Path::Normalized& key)
    {
        require(!manager.exists(key), "Unexpected VFS existence result");
        require(!manager.find(VFS::Path::NormalizedView(key)), "Missing resource returned a stream");
        bool threw = false;
        try { auto stream = manager.get(key); }
        catch (const std::runtime_error&) { threw = true; }
        require(threw, "Missing VFS get must throw");
    }

    std::string contents(std::istream& stream)
    {
        return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
    }

    void integration(const std::filesystem::path& base, const std::filesystem::path& overlay,
        const ToUTF8::StatelessUtf8Encoder& encoder)
    {
        VFS::Manager manager;
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, base, encoder);
        requireMissing(manager, VFS::Path::Normalized(mesh)); // Registration does not build the index.
        manager.buildIndex();
        checkIndex(manager, basePayloads);
        for (const auto& [name, payload] : basePayloads) checkPayload(manager, name, payload);

        const VFS::Path::Normalized mixed(R"(\\MESHES\\\\IOSPROBE.BIN)");
        require(mixed.view() == mesh, "ASCII case/slash/leading-separator normalization differs");
        checkPayload(manager, mixed.value(), baseMesh);
        require(manager.getStem(VFS::Path::NormalizedView("textures/caf\xc3\xa9x.txt")) == "Caf\xc3\xa9X",
            "Real CP1252-to-UTF8 stem conversion failed");
        require(manager.getLastModified(VFS::Path::NormalizedView("meshes/iosprobe.bin"))
            == std::filesystem::last_write_time(base), "Archive timestamp delegation failed");
        const VFS::Path::Normalized dotted("Meshes/../Textures/Caf\xc3\xa9X.TXT");
        require(dotted.view() == "meshes/../textures/caf\xc3\xa9x.txt", "Dot components unexpectedly resolved");
        requireMissing(manager, dotted); // VFS normalization is not filesystem canonicalization.
        requireMissing(manager, VFS::Path::Normalized("textures/caf\xc3\x89x.txt")); // No Unicode case folding.
        requireMissing(manager, VFS::Path::Normalized("meshes/absent.bin"));
        bool rejectedView = false;
        try { const VFS::Path::NormalizedView bad("Meshes\\IOSProbe.BIN"); }
        catch (const std::invalid_argument&) { rejectedView = true; }
        require(rejectedView, "NormalizedView must not accept an unnormalized path");

        // Open before rebuilding. No VFS::File/entry pointer may outlive its archive.
        auto retained = manager.get(VFS::Path::Normalized(mesh));
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, overlay, encoder);
        checkPayload(manager, mesh, baseMesh); // Old index remains until rebuild.
        requireMissing(manager, VFS::Path::Normalized("docs/onlyoverride.txt"));
        manager.buildIndex();
        Payloads merged = basePayloads;
        merged[mesh] = overrideMesh;
        merged["docs/onlyoverride.txt"] = "Override-only original payload.\n";
        checkIndex(manager, merged);
        for (const auto& [name, payload] : merged) checkPayload(manager, name, payload);
        require(manager.getArchive(VFS::Path::Normalized(mesh)) == "BSA: " + Files::pathToUnicodeString(overlay),
            "Last-added duplicate archive should win");
        manager.reset();
        require(names(manager).empty(), "Reset did not clear index");
        requireMissing(manager, VFS::Path::Normalized(mesh));
        require(contents(*retained) == baseMesh, "Open stream did not survive index rebuild and archive reset");

        Files::IStreamPtr afterDestruction;
        {
            VFS::Manager reversed;
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(reversed, overlay, encoder);
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(reversed, base, encoder);
            reversed.buildIndex();
            merged[mesh] = baseMesh;
            checkIndex(reversed, merged);
            for (const auto& [name, payload] : merged) checkPayload(reversed, name, payload);
            require(reversed.getArchive(VFS::Path::Normalized(mesh)) == "BSA: " + Files::pathToUnicodeString(base),
                "Reversed registration order should reverse duplicate precedence");
            afterDestruction = reversed.get(VFS::Path::Normalized(mesh));
        }
        require(contents(*afterDestruction) == baseMesh, "Open payload stream did not survive manager destruction");
    }
}

int main(int argc, char** argv)
{
    static_assert(std::endian::native == std::endian::little, "Inspected original BSA reader uses native words");
    try
    {
        require(argc >= 3, "Usage: openmw-bsa-vfs-check verify base.bsa overlay.bsa | reject-archive path | reject-index path");
        // Declare before all managers: real adapters borrow this encoder.
        const ToUTF8::StatelessUtf8Encoder encoder(ToUTF8::WINDOWS_1252);
        const std::string_view mode(argv[1]);
        if (mode == "verify")
        {
            require(argc == 4, "verify needs exactly two fixture paths");
            integration(argv[2], argv[3], encoder);
            std::cout << "OpenMW BSA/VFS integration passed; synthetic payloads only; no world loaded.\n";
        }
        else if (mode == "reject-archive")
        {
            require(argc == 3, "reject-archive needs one fixture path");
            VFS::Manager manager;
            bool rejected = false;
            try { OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, argv[2], encoder); }
            catch (const std::runtime_error& error)
            {
                const std::string_view message(error.what());
                if (!message.starts_with("BSA input must be")) throw;
                rejected = true;
            }
            require(rejected, "Expected input-policy rejection");
            manager.buildIndex();
            require(names(manager).empty(), "Rejected archive was registered");
            std::cout << "REJECTED by existing-file/original-format input policy\n";
        }
        else if (mode == "reject-index")
        {
            require(argc == 3, "reject-index needs one fixture path");
            VFS::Manager manager;
            OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, argv[2], encoder);
            manager.buildIndex();
            bool rejected = false;
            try { checkIndex(manager, basePayloads); }
            catch (const std::runtime_error& error)
            {
                if (std::string_view(error.what()) != "Unexpected or missing synthetic resource table") throw;
                rejected = true;
            }
            require(rejected, "Expected synthetic manifest mismatch");
            std::cout << "REJECTED unexpected/missing synthetic VFS index entry\n";
        }
        else throw std::runtime_error("Unknown fixture mode");
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
