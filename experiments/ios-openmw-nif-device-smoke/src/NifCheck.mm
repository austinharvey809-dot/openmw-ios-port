#import "NifCheck.hpp"
#import <CommonCrypto/CommonDigest.h>
#import <TargetConditionals.h>
#include "NifProbe.hpp"
#include "G0CExpectations.hpp"
#include <limits>
#include <stdexcept>

namespace {
void Check(bool value, const char *message) { if (!value) throw std::runtime_error(message); }
NSString *Text(const char *text) { return [NSString stringWithUTF8String:text]; }
NSData *Read(NSURL *url) {
    NSNumber *regular = nil, *link = nil;
    Check([url getResourceValue:&regular forKey:NSURLIsRegularFileKey error:nil] && regular.boolValue,
        "Resource must be a regular file");
    Check([url getResourceValue:&link forKey:NSURLIsSymbolicLinkKey error:nil] && !link.boolValue, "Linked resource");
    NSData *data = [NSData dataWithContentsOfURL:url];
    Check(data != nil, "Cannot read resource"); return data;
}
NSString *Digest(NSData *data) {
    Check(data != nil && data.length <= std::numeric_limits<CC_LONG>::max(), "Invalid SHA-256 input");
    unsigned char value[CC_SHA256_DIGEST_LENGTH];
    Check(CC_SHA256(data.bytes, (CC_LONG)data.length, value) != nullptr, "SHA-256 failed");
    NSMutableString *text = [NSMutableString new];
    for (auto byte : value) [text appendFormat:@"%02x", byte]; return text;
}
NSDictionary *Object(NSData *data) {
    id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    Check([object isKindOfClass:NSDictionary.class], "Invalid JSON object"); return object;
}
NSDictionary *Snapshot(NSURL *directory) {
    NSArray<NSURL *> *files = [NSFileManager.defaultManager contentsOfDirectoryAtURL:directory
        includingPropertiesForKeys:nil options:0 error:nil];
    NSSet *names = [NSSet setWithArray:@[@"valid.esm", @"triangle-candidate.nif", @"triangle-candidate.bsa",
        @"invalid-header.nif", @"invalid-header.bsa", @"truncated.nif", @"truncated.bsa",
        @"invalid-reference.nif", @"invalid-reference.bsa", @"missing-resource.bsa",
        @"fixture-manifest.json", @"nif-source-sha256.json"]];
    Check(files != nil && files.count == names.count, "Fixture inventory mismatch");
    NSMutableDictionary *snapshot = [NSMutableDictionary new];
    for (NSURL *file in files) {
        Check([names containsObject:file.lastPathComponent], "Unexpected fixture entry");
        NSData *data = Read(file);
        snapshot[file.lastPathComponent] = @{@"sha256": Digest(data), @"size": @(data.length)};
    }
    return snapshot;
}
}
NSDictionary *RunNifCheck(NSURL *fixtureDirectory, NSURL *buildMetadata) {
    NSMutableDictionary *result = [@{@"schema_version": @1, @"status": @"FAIL",
        @"scope": @"G0C genuine NIF parsing; synthetic resources; no rendering",
        @"session_id": NSUUID.UUID.UUIDString,
        @"started_utc": [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]],
        @"inputs_unchanged": NSNull.null} mutableCopy];
    NSMutableArray *cases = [NSMutableArray new]; result[@"cases"] = cases;
    NSDictionary *before = nil;
    const double start = NSProcessInfo.processInfo.systemUptime;
    try {
#if !TARGET_OS_IPHONE || TARGET_OS_SIMULATOR
        Check(false, "Physical iPhoneOS executable required");
#endif
        NSData *buildData = Read(buildMetadata);
        Check([Digest(buildData) isEqualToString:Text(G0CExpected::BuildSHA256)], "Build metadata hash mismatch");
        NSDictionary *metadata = Object(buildData); result[@"build"] = metadata;
        Check([metadata[@"source_commit"] isEqualToString:Text(G0CExpected::SourceCommit)]
            && [metadata[@"osg_revision"] isEqualToString:Text(G0CExpected::OSGRevision)], "Build provenance mismatch");
        before = Snapshot(fixtureDirectory); result[@"inputs_before"] = before;
        NSData *manifestData = Read([fixtureDirectory URLByAppendingPathComponent:@"fixture-manifest.json"]);
        Check([Digest(manifestData) isEqualToString:Text(G0CExpected::ManifestSHA256)], "Fixture manifest hash mismatch");
        NSDictionary *manifest = Object(manifestData);
        NSDictionary *files = manifest[@"files"];
        Check([files isKindOfClass:NSDictionary.class] && files.count == 10, "Invalid fixture manifest");
        for (NSString *name in files) Check([before[name] isEqual:files[name]], "Fixture size/hash mismatch");
        Check([manifest[@"status"] isEqualToString:@"candidate-unvalidated-by-openmw-parser"], "Unexpected fixture status");
        NSDictionary *hashes = metadata[@"resources_sha256"];
        for (NSString *name in before) {
            Check([before[name][@"sha256"] isEqual:hashes[[@"Fixtures/" stringByAppendingString:name]]],
                "Source/fixture provenance hash mismatch");
        }
        for (std::size_t index = 0; index < 6; ++index) {
            const auto observed = G0C::runCase(index, std::filesystem::path(fixtureDirectory.fileSystemRepresentation));
            NSMutableDictionary *entry = [@{@"mode": Text(observed.mode.c_str()), @"passed": @(observed.passed),
                @"exit_code": @(observed.exitCode), @"stdout": Text(observed.output.c_str()) ?: @"",
                @"stderr": Text(observed.error.c_str()) ?: @""} mutableCopy];
            [cases addObject:entry];
            NSDictionary *after = Snapshot(fixtureDirectory); result[@"inputs_after"] = after;
            result[@"inputs_unchanged"] = @([before isEqual:after]);
            Check([before isEqual:after], "Parser modified inputs");
            Check(observed.passed, "Genuine G0B parser case failed");
            if (index == 0) {
                NSMutableDictionary *counts = [NSMutableDictionary new];
                for (const auto& [name, value] : observed.counts) counts[Text(name.c_str())] = @(value);
                result[@"decoded"] = counts;
                NSString *hash = Digest([NSData dataWithBytes:observed.payload.data() length:observed.payload.size()]);
                Check([hash isEqualToString:Text(G0CExpected::PayloadSHA256)], "Actual VFS resource SHA-256 mismatch");
                result[@"resource_sha256"] = hash;
                result[@"object_id"] = @"eIOSStatic"; result[@"model"] = @"TeSt.NIF";
                result[@"resource_key"] = @"meshes/test.nif";
            }
        }
        Check(cases.count == 6 && [result[@"inputs_unchanged"] isEqual:@YES], "Incomplete negative/integrity evidence");
        for (NSDictionary *entry in cases) Check([entry[@"passed"] isEqual:@YES], "Skipped or failed parser case");
        result[@"genuine_parser_suite_completed"] = @YES;
        result[@"status"] = @"PASS";
    } catch (const std::exception& error) {
        result[@"error"] = Text(error.what()) ?: @"Unknown parser failure";
        if (before) {
            try {
                NSDictionary *after = Snapshot(fixtureDirectory); result[@"inputs_after"] = after;
                result[@"inputs_unchanged"] = @([before isEqual:after]);
            } catch (const std::exception& failure) { result[@"integrity_error"] = Text(failure.what()); }
        }
    }
    result[@"elapsed_ms"] = @((NSProcessInfo.processInfo.systemUptime - start) * 1000);
    result[@"finished_utc"] = [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]];
    return result;
}
