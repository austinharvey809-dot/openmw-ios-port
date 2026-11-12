#include "NifProbe.hpp"
#include <charconv>
#include <sstream>
// Reuse the exact successful genuine G0B operations and geometry checks in-process.
// No subprocess, replacement parser, or changes to the preserved source.
#define main G0BParserMain
#include "../../ios-openmw-nif-smoke/tests/nif_parse_check.cpp"
#undef main

namespace G0C {
namespace {
struct Capture {
    std::ostringstream out, err;
    std::streambuf *oldOut = std::cout.rdbuf(out.rdbuf()), *oldErr = std::cerr.rdbuf(err.rdbuf());
    ~Capture() { std::cout.rdbuf(oldOut); std::cerr.rdbuf(oldErr); }
};
struct Case { const char *mode, *bsa, *nif, *marker; };
constexpr Case cases[] = {
    {"positive", "triangle-candidate.bsa", "triangle-candidate.nif", "PASS genuine OpenMW NIF parse"},
    {"invalid", "invalid-header.bsa", "invalid-header.nif", "PASS genuine parser rejected invalid"},
    {"truncated", "truncated.bsa", "truncated.nif", "PASS genuine parser rejected truncated"},
    {"invalid-reference", "invalid-reference.bsa", "invalid-reference.nif", "PASS genuine parser rejected invalid-reference"},
    {"missing", "missing-resource.bsa", "triangle-candidate.nif", "PASS missing resource rejected"},
    {"positive", "triangle-candidate.bsa", "invalid-header.nif", "VFS NIF bytes differ"}
};
}
CaseResult runCase(std::size_t index, const std::filesystem::path& fixtures) {
    if (index >= std::size(cases)) throw std::runtime_error("Unknown G0C case");
    const auto& test = cases[index];
    std::string args[] = {"g0c-in-process", test.mode, (fixtures / "valid.esm").string(),
        (fixtures / test.bsa).string(), (fixtures / test.nif).string()};
    char *argv[] = {args[0].data(), args[1].data(), args[2].data(), args[3].data(), args[4].data()};
    CaseResult result;
    result.mode = index == 5 ? "wrong-resource-bytes" : test.mode;
    {
        Capture capture;
        result.exitCode = G0BParserMain(5, argv);
        result.output = capture.out.str(); result.error = capture.err.str();
    }
    result.passed = index == 5 ? result.exitCode != 0 && result.error.find(test.marker) != std::string::npos
        : result.exitCode == 0 && result.output.find(test.marker) != std::string::npos;
    if (index == 0 && result.passed) {
        // These numbers are emitted from actual decoded records by G0B inspectParsed.
        for (const char *field : {"records", "roots", "geometry", "vertices", "triangles"}) {
            const std::string key = std::string(field) + "=";
            auto start = result.output.find(key);
            if (start == std::string::npos) throw std::runtime_error("Missing decoded count");
            start += key.size();
            std::size_t count = 0;
            const auto parsed = std::from_chars(result.output.data() + start, result.output.data() + result.output.size(), count);
            if (parsed.ec != std::errc() || (parsed.ptr != result.output.data() + result.output.size()
                && *parsed.ptr != ' ' && *parsed.ptr != '\n')) throw std::runtime_error("Malformed decoded count");
            result.counts[field] = count;
        }
        const ToUTF8::StatelessUtf8Encoder encoder(ToUTF8::WINDOWS_1252);
        VFS::Manager manager;
        OpenMWIOSBsaVfs::addExistingMorrowindBSA(manager, fixtures / test.bsa, encoder);
        manager.buildIndex();
        auto stream = manager.get(VFS::Path::NormalizedView("meshes/test.nif"));
        result.payload.assign(std::istreambuf_iterator<char>(*stream), std::istreambuf_iterator<char>());
    }
    return result;
}
}
