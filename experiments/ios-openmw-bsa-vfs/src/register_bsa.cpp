#include "register_bsa.hpp"

#include <components/bsa/bsafile.hpp>
#include <components/vfs/bsaarchive.hpp>
#include <components/vfs/manager.hpp>

#include <memory>
#include <stdexcept>

namespace OpenMWIOSBsaVfs
{
    void addExistingMorrowindBSA(VFS::Manager& manager, const std::filesystem::path& path,
        const ToUTF8::StatelessUtf8Encoder& encoder)
    {
        // BSAFile::open creates missing archives. Validate before constructing
        // the real adapter; this is an input policy, not a replacement reader.
        if (!std::filesystem::is_regular_file(path))
            throw std::runtime_error("BSA input must be an existing regular file");
        if (Bsa::BSAFile::detectVersion(path) != Bsa::BsaVersion::Uncompressed)
            throw std::runtime_error("BSA input must be original uncompressed Morrowind format");
        manager.addArchive(std::make_unique<VFS::BsaArchive<Bsa::BSAFile>>(path, &encoder));
    }
}
