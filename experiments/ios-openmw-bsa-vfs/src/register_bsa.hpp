#ifndef OPENMW_IOS_BSA_VFS_REGISTER_BSA_HPP
#define OPENMW_IOS_BSA_VFS_REGISTER_BSA_HPP

#include <filesystem>

namespace VFS { class Manager; }
namespace ToUTF8 { class StatelessUtf8Encoder; }

namespace OpenMWIOSBsaVfs
{
    // The encoder is borrowed by the real archive adapter. Its owner must keep
    // it alive until the manager resets/destroys this archive. No index rebuild
    // is implicit: the caller uses Manager::buildIndex() after registration.
    void addExistingMorrowindBSA(VFS::Manager& manager, const std::filesystem::path& path,
        const ToUTF8::StatelessUtf8Encoder& encoder);
}

#endif
