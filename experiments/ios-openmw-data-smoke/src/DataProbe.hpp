#ifndef OPENMW_IOS_DATA_PROBE_HPP
#define OPENMW_IOS_DATA_PROBE_HPP
#include <filesystem>
#include <string>

namespace OpenMWIOSDataSmoke
{
    struct ProbeResult
    {
        std::string objectId;
        std::string model;
        std::string resourceKey;
        std::string payload;
    };
    // Genuine OpenMW parsing and resource retrieval. Throws on a failed check.
    ProbeResult readResource(const std::filesystem::path& esm, const std::filesystem::path& bsa);
}
#endif
