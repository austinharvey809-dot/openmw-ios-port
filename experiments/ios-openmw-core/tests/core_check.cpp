// Exercise actual OpenMW data code. This is a host fixture, not an Engine instance.
#include <components/files/constrainedfilestream.hpp>
#include <components/files/conversion.hpp>
#include <components/files/openfile.hpp>
#include <components/vfs/archive.hpp>
#include <components/vfs/file.hpp>
#include <components/vfs/manager.hpp>
#include <components/vfs/pathutil.hpp>
#include <components/vfs/recursivedirectoryiterator.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace
{
    void require(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }

    std::string contents(std::istream& stream)
    {
        return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
    }

    // A test-only archive adapter; Manager, normalization and the bounded file
    // reader are real OpenMW implementations. No BSA/FileSystemArchive claim.
    class SliceFile final : public VFS::File
    {
        std::filesystem::path mPath;
        std::size_t mStart;
    public:
        SliceFile(std::filesystem::path path, std::size_t start) : mPath(std::move(path)), mStart(start) {}
        Files::IStreamPtr open() override { return Files::openConstrainedFileStream(mPath, mStart, 2); }
        std::filesystem::file_time_type getLastModified() const override { return std::filesystem::last_write_time(mPath); }
        std::string getStem() const override { return Files::pathToUnicodeString(mPath.stem()); }
    };

    class SliceArchive final : public VFS::Archive
    {
        VFS::Path::Normalized mName{"meshes/ios-probe.bin"};
        SliceFile mFile;
    public:
        SliceArchive(const std::filesystem::path& path, std::size_t start) : mFile(path, start) {}
        void listResources(VFS::FileMap& out) override { out[mName] = &mFile; }
        bool contains(VFS::Path::NormalizedView name) const override { return name.value() == mName.view(); }
        std::string getDescription() const override { return "isolated bounded-file fixture"; }
    };
}

int main(int argc, char** argv)
{
    try
    {
        require(argc == 2, "Pass the fixture path inside the owned test/build directory");
        const std::filesystem::path path(argv[1]);
        {
            std::ofstream file(path, std::ios::binary | std::ios::trunc);
            file.exceptions(std::ios::badbit | std::ios::failbit);
            file << "0123456789";
        }
        auto full = Files::openBinaryInputFileStream(path);
        require(contents(*full) == "0123456789", "OpenMW binary file read failed");
        auto bounded = Files::openConstrainedFileStream(path, 2, 4);
        require(contents(*bounded) == "2345", "Bounded stream escaped its range");
        bounded->clear(); bounded->seekg(1);
        require(contents(*bounded) == "345", "Bounded relative seek failed");

        const std::string unicode = "probe-\xc3\xa9.bin";
        require(Files::pathToUnicodeString(Files::pathFromUnicodeString(std::string_view(unicode))) == unicode,
                "UTF-8 path round trip failed");
        const VFS::Path::Normalized name(R"(\Meshes\\IOS-PROBE.BIN)");
        require(name.view() == "meshes/ios-probe.bin", "OpenMW VFS normalization failed");
        VFS::Manager vfs;
        vfs.addArchive(std::make_unique<SliceArchive>(path, 2));
        vfs.buildIndex();
        auto first = vfs.get(name);
        require(contents(*first) == "23", "VFS file dispatch failed");
        vfs.addArchive(std::make_unique<SliceArchive>(path, 6));
        vfs.buildIndex();
        auto last = vfs.get(name);
        require(contents(*last) == "67", "Last-added archive did not take priority");
        unsigned entries = 0;
        for (const auto& entry : vfs.getRecursiveDirectoryIterator("MESHES\\"))
        {
            require(entry.view() == name.view(), "Unexpected VFS index entry");
            ++entries;
        }
        require(entries == 1, "VFS recursive index range failed");
        require(!vfs.find(VFS::Path::NormalizedView("missing.bin")), "Missing VFS resource unexpectedly found");
        bool threw = false;
        try { auto missing = vfs.get(VFS::Path::NormalizedView("missing.bin")); }
        catch (const std::runtime_error&) { threw = true; }
        require(threw, "Missing VFS resource did not report failure");
        vfs.reset();
        require(!vfs.exists(name), "VFS reset retained the file index");
        std::cout << "OpenMW data-core host checks passed; OMW::Engine was not instantiated.\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
