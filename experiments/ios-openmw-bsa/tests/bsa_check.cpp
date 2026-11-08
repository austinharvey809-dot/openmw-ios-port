// Reads original synthetic bytes using the real OpenMW BSA implementation.
#include <components/bsa/bsafile.hpp>
#include <components/vfs/pathutil.hpp>

#include <bit>
#include <filesystem>
#include <iostream>
#include <istream>
#include <iterator>
#include <map>
#include <stdexcept>
#include <string>

namespace
{
    void require(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }
    std::string contents(std::istream& input)
    {
        return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
    }
}

int main(int argc, char** argv)
{
    static_assert(std::endian::native == std::endian::little, "The inspected reader uses native little-endian words");
    try
    {
        require(argc == 3, "Usage: openmw-bsa-check existing-fixture.bsa read|reject");
        const std::filesystem::path path(argv[1]);
        const std::string mode(argv[2]);
        require(mode == "read" || mode == "reject", "Unknown fixture mode");
        // BSAFile::open creates an archive if missing. Do not exercise that writer
        // behavior here; both positive and negative reader cases must already exist.
        require(std::filesystem::is_regular_file(path), "Synthetic input file must already exist");
        if (mode == "reject")
        {
            try
            {
                Bsa::BSAFile reader;
                reader.open(path);
            }
            catch (const std::runtime_error& error)
            {
                std::cout << "REJECTED by OpenMW BSA reader: " << error.what() << '\n';
                return 0;
            }
            throw std::runtime_error("OpenMW accepted a malformed/unsupported synthetic archive");
        }
        require(Bsa::BSAFile::detectVersion(path) == Bsa::BsaVersion::Uncompressed, "Version detection failed");
        Bsa::BSAFile reader;
        reader.open(path);
        const auto& files = reader.getList();
        require(files.size() == 2, "Expected two BSA directory entries");
        require(files[0].mOffset < files[1].mOffset, "Reader did not sort entries by payload offset");
        const std::map<std::string, std::string> expected = {
            {"Meshes\\IOSProbe.BIN", std::string("\x00OMW\xff\nARCH", 10)},
            {"Textures\\IOSProbe.TXT", "Original synthetic archive payload.\n"},
        };
        for (const auto& entry : files)
        {
            const auto found = expected.find(std::string(entry.name()));
            require(found != expected.end(), "Unexpected BSA filename");
            require(entry.mFileSize == found->second.size(), "Unexpected BSA payload length");
            auto stream = reader.getFile(&entry);
            require(contents(*stream) == found->second, "Archive payload mismatch or range overread");
            stream->clear();
            stream->seekg(1);
            require(contents(*stream) == found->second.substr(1), "Archive stream seek failed");
            const VFS::Path::Normalized normalized(entry.name());
            require(normalized.view().starts_with("meshes/") || normalized.view().starts_with("textures/"),
                    "Existing VFS path normalization failed");
        }
        // A payload stream owns its file handle independently of the parsed table.
        const std::string retainedExpected = expected.at(std::string(files.front().name()));
        auto retained = reader.getFile(&files.front());
        reader.close();
        require(reader.getList().empty(), "Archive close did not clear directory entries");
        require(contents(*retained) == retainedExpected, "Payload stream lifetime depended on directory entry");
        std::cout << "OpenMW BSA payload checks passed; synthetic data only; no ESM/NIF/world loaded.\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
