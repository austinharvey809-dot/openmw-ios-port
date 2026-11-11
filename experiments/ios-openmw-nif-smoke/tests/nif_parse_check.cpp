// G0A host candidate check. Only OpenMW's Nif::Reader may authorize PASS.
#include "register_bsa.hpp"
#include <components/esm3/esmreader.hpp>
#include <components/esm3/loadstat.hpp>
#include <components/nif/data.hpp>
#include <components/nif/niffile.hpp>
#include <components/nif/node.hpp>
#include <components/toutf8/toutf8.hpp>
#include <components/vfs/manager.hpp>

#include <bit>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <string_view>

namespace
{
    void require(bool condition, const char* message)
    {
        if (!condition) throw std::runtime_error(message);
    }

    std::string readFile(const std::filesystem::path& path)
    {
        std::ifstream input(path, std::ios::binary);
        require(input.good(), "Candidate NIF file missing");
        return { std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>() };
    }

    void inspectParsed(const Nif::NIFFile& file)
    {
        require(file.mVersion == Nif::NIFFile::VER_MW, "Parsed NIF version is not Morrowind 4.0.0.2");
        require(file.mRoots.size() == 1 && file.mRoots[0], "Parsed root list differs");
        const auto* root = dynamic_cast<const Nif::NiNode*>(file.mRoots[0]);
        require(root && root->mChildren.size() == 1 && !root->mChildren[0].empty(), "Parsed NiNode child missing");
        const auto* shape = dynamic_cast<const Nif::NiTriShape*>(root->mChildren[0].getPtr());
        require(shape && !shape->mData.empty(), "Parsed NiTriShape/data relationship missing");
        const auto* data = dynamic_cast<const Nif::NiTriShapeData*>(shape->mData.getPtr());
        require(data, "Decoded data is not NiTriShapeData");
        const std::size_t vertices = data->mVertices.size();
        const std::size_t indices = data->mTriangles.size();
        std::size_t geometry = 0;
        for (const auto& record : file.mRecords)
            if (dynamic_cast<const Nif::NiTriShape*>(record.get())) ++geometry;
        require(vertices == data->mNumVertices && indices == 3 * data->mNumTriangles
                && indices % 3 == 0, "Decoded geometry counts inconsistent");
        for (const auto index : data->mTriangles)
            require(index < vertices, "Decoded triangle index out of range");
        require(file.mRecords.size() == 3 && geometry == 1 && vertices == 3 && indices == 3,
            "Parsed candidate does not contain the intended three-record triangle");
        std::cout << "PASS genuine OpenMW NIF parse version=4.0.0.2 records=" << file.mRecords.size()
                  << " roots=" << file.mRoots.size() << " geometry=" << geometry << " vertices=" << vertices
                  << " triangles=" << indices / 3 << '\n';
    }
}

int main(int argc, char** argv)
{
    static_assert(std::endian::native == std::endian::little, "Synthetic TES3/BSA/NIF requires little endian");
    try
    {
        require(argc == 5, "Usage: reader positive|invalid|truncated|invalid-reference|missing existing.esm input.bsa expected.nif");
        const std::string_view mode(argv[1]);
        require(mode == "positive" || mode == "invalid" || mode == "truncated"
                || mode == "invalid-reference" || mode == "missing",
            "Unknown test mode");
        const auto esm = std::filesystem::path(argv[2]);
        const auto bsa = std::filesystem::path(argv[3]);
        const auto expected = std::filesystem::path(argv[4]);
        require(std::filesystem::is_regular_file(esm) && std::filesystem::is_regular_file(bsa),
            "ESM/BSA input missing");

        ToUTF8::Utf8Encoder esmEncoder(ToUTF8::WINDOWS_1252);
        const ToUTF8::StatelessUtf8Encoder archiveEncoder(ToUTF8::WINDOWS_1252);
        ESM::ESMReader reader;
        reader.setEncoder(&esmEncoder);
        reader.open(esm);
        require(reader.getVer() == ESM::VER_130 && reader.getRecordCount() == 1
            && reader.hasMoreRecs() && reader.getRecName() == "STAT", "Expected synthetic ESM STAT missing");
        reader.getRecHeader();
        ESM::Static object;
        bool deleted = false;
        object.load(reader, deleted);
        require(!deleted && !object.mModel.empty() && !reader.hasMoreSubs() && !reader.hasMoreRecs(),
            "STAT model/framing invalid");
        require(object.mId.getRefIdString() == "eIOSStatic" && object.mModel.getOriginal() == "TeSt.NIF",
            "STAT provenance mismatch");
        const auto key = VFS::Path::join(VFS::Path::NormalizedView("meshes"), object.mModel.getNormalized());
        require(key.view() == "meshes/test.nif", "Unexpected normalized resource path");

        VFS::Manager vfs;
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(vfs, bsa, archiveEncoder);
        vfs.buildIndex();
        if (mode == "missing")
        {
            require(!vfs.exists(key), "Missing-resource fixture unexpectedly resolves");
            std::cout << "PASS missing resource rejected\n";
            return 0;
        }
        require(vfs.exists(key), "Referenced NIF is missing from BSA/VFS");
        const std::string wanted = readFile(expected);
        auto resource = vfs.get(key);
        const std::string returned{ std::istreambuf_iterator<char>(*resource), std::istreambuf_iterator<char>() };
        require(returned == wanted, "VFS NIF bytes differ from candidate file");
        resource = vfs.get(key); // Fresh genuine bounded stream for the parser.
        Nif::NIFFile file(key);
        Nif::Reader nifReader(file, &archiveEncoder);
        if (mode == "positive")
        {
            nifReader.parse(std::move(resource));
            inspectParsed(file);
            return 0;
        }
        try
        {
            nifReader.parse(std::move(resource));
        }
        catch (const std::exception& error)
        {
            std::cout << "PASS genuine parser rejected " << mode << ": " << error.what() << '\n';
            return 0;
        }
        throw std::runtime_error("Invalid candidate parsed without an error");
    }
    catch (const std::exception& error)
    {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
