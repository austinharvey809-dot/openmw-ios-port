#include <components/esm/position.hpp>
#include <components/esm3/esmreader.hpp>
#include <components/files/openfile.hpp>
#include <components/toutf8/toutf8.hpp>

#include <bit>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>

namespace
{
    void require(bool value, const char* message)
    {
        if (!value) throw std::runtime_error(message);
    }

    void mathCheck()
    {
        ESM::Position first{{1, 2, 3}, {4, 5, 6}};
        ESM::Position later = first;
        later.pos[2] = 4;
        const osg::Vec3f vector = first.asVec3();
        require(vector.length2() == 14 && first.asRotationVec3().z() == 6 && first < later,
            "Real OSG Vec3f/Position operations failed");
        // This real executable must link these operations and the full reader
        // without libosg, ANGLE, GL or GUI libraries. Headers alone are no link proof.
    }

    void open(ESM::ESMReader& reader, const std::filesystem::path& path, bool strict)
    {
        if (strict)
        {
            auto stream = Files::openBinaryInputFileStream(path);
            // Explicit caller policy. The engine's default path API enables
            // badbit only; this does not silently alter its short-read behavior.
            stream->exceptions(std::ios::badbit | std::ios::failbit);
            reader.open(std::move(stream), path);
        }
        else reader.open(path);
    }

    void parse(ESM::ESMReader& reader, const std::filesystem::path& path, int type, bool strict)
    {
        open(reader, path, strict);
        require(reader.isOpen() && reader.getFileSize() == std::filesystem::file_size(path), "File opening/size mismatch");
        require(reader.getVer() == ESM::VER_130, "Wrong TES3 version");
        require(reader.getHeader().mData.type == type && reader.getRecordCount() == 1, "Wrong header type/count");
        require(reader.getAuthor() == "Original Caf\xc3\xa9 fixture", "Real Windows-1252 author decoding failed");
        require(reader.getDesc() == "Original synthetic TES3 fixture; no game data.", "Description mismatch");
        require(reader.getGameFiles().empty() && reader.getFormatVersion() == ESM::DefaultFormatVersion, "Legacy header metadata mismatch");
        require(!reader.hasMoreSubs() && reader.hasMoreRecs() && reader.getFileOffset() == 324, "TES3 framing mismatch");
        require(reader.getRecName() == "GMST", "Wrong record identifier");
        reader.getRecHeader();
        require(reader.getRecordFlags() == 0, "Wrong record flags");
        require(reader.peekNextSub("NAME"), "Missing NAME tag");
        const ESM::RefId id = reader.getHNRefId("NAME");
        require(id == std::string_view("iiosprobe") && id.getRefIdString() == "iIOSProbe", "Genuine RefId semantics mismatch");
        require(reader.getSubSize() == 10, "Wrong NAME payload length");
        require(!reader.isNextSub("NOPE"), "Unexpected synthetic subrecord"); // Cache INTV on mismatch.
        std::int32_t value = 0;
        reader.getHNT(value, "INTV");
        require(reader.getSubSize() == 4 && value == -1234567, "INTV payload mismatch");
        require(!reader.hasMoreSubs() && !reader.hasMoreRecs(), "Unexpected trailing records/bytes");
        require(reader.getFileOffset() == 370, "Reader crossed expected file boundary");
    }
}

int main(int argc, char** argv)
{
    static_assert(std::endian::native == std::endian::little, "Inspected TES3 reader uses native integer words");
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559, "TES3 fixture requires IEEE-754 float32");
    try
    {
        require(argc == 3 || argc == 4, "Usage: openmw-esm-check mode existing-input [header-type]");
        const std::string_view mode(argv[1]);
        const std::filesystem::path path(argv[2]);
        ToUTF8::Utf8Encoder encoder(ToUTF8::WINDOWS_1252); // Reader borrows; encoder outlives it.
        ESM::ESMReader reader;
        reader.setEncoder(&encoder);
        if (mode == "reject-missing")
        {
            require(!std::filesystem::exists(path), "Missing-input path already exists");
            bool rejected = false;
            try { reader.open(path); }
            catch (const std::system_error& error) { std::cout << error.what() << '\n'; rejected = true; }
            require(rejected && !std::filesystem::exists(path), "Missing input was accepted/created");
            std::cout << "REJECTED missing file by genuine OpenMW file helper\n";
            return 0;
        }
        require(std::filesystem::is_regular_file(path), "Fixture input must already be a regular file");
        const bool strict = mode == "strict-read" || mode == "strict-reject";
        if (mode == "reject" || mode == "strict-reject")
        {
            bool rejected = false;
            try { parse(reader, path, 1, strict); }
            catch (const std::ios_base::failure& error)
            {
                if (!strict) throw;
                std::cout << error.what() << '\n';
                rejected = true;
            }
            catch (const std::runtime_error& error)
            {
                if (strict || !std::string_view(error.what()).starts_with("ESM Error: ")) throw;
                std::cout << error.what() << '\n';
                rejected = true;
            }
            require(rejected, "Expected genuine reader/explicit strict I/O rejection");
            std::cout << (strict ? "REJECTED short read by explicit caller stream policy\n" : "REJECTED by genuine ESM reader check\n");
            return 0;
        }
        require((mode == "read" || mode == "strict-read") && argc == 4, "Unknown fixture mode or missing header type");
        require(std::string_view(argv[3]) == "0" || std::string_view(argv[3]) == "1", "Invalid expected header type");
        const int type = argv[3][0] - '0';
        mathCheck();
        parse(reader, path, type, strict);
        bool eofRejected = false;
        try { reader.getRecName(); }
        catch (const std::runtime_error& error)
        {
            eofRejected = std::string_view(error.what()).starts_with("ESM Error: No more records");
        }
        require(eofRejected, "End-of-file record traversal must reject");
        reader.close();
        require(!reader.isOpen(), "Reader did not close");
        open(reader, path, strict); // Genuine reader reuse and skip, no writer APIs.
        require(reader.getRecName() == "GMST", "Reopen failed");
        reader.getRecHeader();
        require(reader.getContext().leftRec == 30, "Wrong declared GMST record size");
        reader.skipRecord();
        require(!reader.hasMoreRecs() && !reader.hasMoreSubs() && reader.getFileOffset() == 370, "Record skip framing mismatch");
        reader.close();
        std::cout << "OpenMW ESM fixture passed; genuine reader and OSG math linked; synthetic data only.\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
