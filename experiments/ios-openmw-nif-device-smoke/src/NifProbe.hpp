#pragma once
#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
namespace G0C {
struct CaseResult {
    std::string mode, output, error, payload;
    int exitCode{};
    bool passed{};
    std::map<std::string, std::size_t> counts;
};
CaseResult runCase(std::size_t index, const std::filesystem::path& fixtures);
}
