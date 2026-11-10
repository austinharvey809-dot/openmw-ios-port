#import "DataCheck.hpp"
#import <CommonCrypto/CommonDigest.h>
#import <TargetConditionals.h>
#include "DataProbe.hpp"
#include "FixtureExpectations.hpp"
#include <limits>
#include <stdexcept>
#include <string>

namespace
{
    void Require(bool value, NSString *message)
    {
        if (!value) throw std::runtime_error(message.UTF8String ?: "Data validation failure");
    }

    NSString *Text(const char *value) { return [NSString stringWithUTF8String:value]; }

    NSString *Digest(NSData *data)
    {
        Require(data != nil && data.length <= std::numeric_limits<CC_LONG>::max(), @"Missing/oversized hash input");
        unsigned char hash[CC_SHA256_DIGEST_LENGTH];
        Require(CC_SHA256(data.bytes, static_cast<CC_LONG>(data.length), hash) != nullptr, @"SHA-256 failed");
        NSMutableString *result = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
        for (unsigned char value : hash) [result appendFormat:@"%02x", value];
        return result;
    }

    NSData *Read(NSURL *url)
    {
        Require(url != nil, @"Missing resource URL");
        NSNumber *regular = nil, *symbolic = nil;
        NSError *error = nil;
        Require([url getResourceValue:&regular forKey:NSURLIsRegularFileKey error:&error] && regular.boolValue,
            @"Fixture must be an existing regular file");
        Require([url getResourceValue:&symbolic forKey:NSURLIsSymbolicLinkKey error:&error] && !symbolic.boolValue,
            @"Symbolic input files are not accepted");
        NSData *data = [NSData dataWithContentsOfURL:url options:0 error:&error];
        Require(data != nil, error.localizedDescription ?: @"Resource read failed");
        return data;
    }

    NSDictionary *Object(NSData *data)
    {
        NSError *error = nil;
        id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
        Require([value isKindOfClass:NSDictionary.class], error.localizedDescription ?: @"Expected JSON object");
        return value;
    }

    NSDictionary *Snapshot(NSURL *directory)
    {
        NSError *error = nil;
        NSArray<NSURL *> *files = [NSFileManager.defaultManager contentsOfDirectoryAtURL:directory
            includingPropertiesForKeys:@[NSURLIsRegularFileKey, NSURLIsSymbolicLinkKey] options:0 error:&error];
        Require(files != nil && files.count == 3, @"Unexpected or missing fixture directory entries");
        NSMutableDictionary *result = [NSMutableDictionary dictionary];
        NSSet *expected = [NSSet setWithArray:@[@"valid.esm", @"base.bsa", @"fixtures.json"]];
        for (NSURL *url in files)
        {
            Require([expected containsObject:url.lastPathComponent], @"Unexpected fixture file");
            NSData *data = Read(url);
            result[url.lastPathComponent] = @{@"sha256": Digest(data), @"size": @(data.length)};
        }
        return result;
    }
}

NSDictionary *RunDataCheck(NSURL *fixtureDirectory, NSURL *buildMetadata)
{
    using namespace OpenMWIOSDataSmoke;
    NSMutableDictionary *result = [@{@"schema_version": @1, @"status": @"FAIL",
        @"session_id": NSUUID.UUID.UUIDString,
        @"started_utc": [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]],
        @"genuine_openmw_call_completed": @NO, @"inputs_unchanged": NSNull.null,
        @"scope": @"Genuine OpenMW STAT-to-VFS data check; synthetic bytes; no NIF rendering or full engine"} mutableCopy];
    NSMutableArray *events = [NSMutableArray array];
    result[@"events"] = events;
    const double start = NSProcessInfo.processInfo.systemUptime;
    try
    {
#if !TARGET_OS_IPHONE || TARGET_OS_SIMULATOR
        Require(false, @"This experiment requires an iPhoneOS device executable");
#endif
        [events addObject:@"Checking bundled fixture and build provenance hashes before parsing"];
        NSData *build = Read(buildMetadata);
        Require([Digest(build) isEqualToString:Text(Expected::BuildMetadataSHA256)], @"Build metadata hash mismatch");
        NSDictionary *metadata = Object(build);
        Require([metadata[@"source_commit"] isEqualToString:Text(Expected::SourceCommit)]
            && [metadata[@"osg_revision"] isEqualToString:Text(Expected::OSGRevision)], @"Build provenance mismatch");
        result[@"build"] = metadata;
        NSData *manifestData = Read([fixtureDirectory URLByAppendingPathComponent:@"fixtures.json"]);
        Require([Digest(manifestData) isEqualToString:Text(Expected::FixtureManifestSHA256)], @"Fixture manifest hash mismatch");
        NSDictionary *manifest = Object(manifestData);
        Require([manifest[@"schema_version"] isEqual:@1], @"Fixture manifest schema mismatch");
        NSDictionary *before = Snapshot(fixtureDirectory);
        result[@"inputs_before"] = before;
        NSDictionary *inputs = manifest[@"inputs"];
        Require([inputs isKindOfClass:NSDictionary.class] && inputs.count == 2, @"Invalid input manifest");
        for (NSString *name in @[@"valid.esm", @"base.bsa"])
            Require([before[name] isEqual:inputs[name]], @"Bundled input size/SHA-256 mismatch");
        [events addObject:@"Executing genuine ESMReader, Static::load, BsaArchive and VFS::Manager"];
        const auto esmURL = [fixtureDirectory URLByAppendingPathComponent:@"valid.esm"];
        const auto bsaURL = [fixtureDirectory URLByAppendingPathComponent:@"base.bsa"];
        const auto parsed = readResource(std::filesystem::path(esmURL.fileSystemRepresentation),
            std::filesystem::path(bsaURL.fileSystemRepresentation));
        result[@"genuine_openmw_call_completed"] = @YES;
        // DataProbe checked byte-for-byte equality. Hash the actual retrieved stream bytes too.
        NSData *payload = [NSData dataWithBytes:parsed.payload.data() length:parsed.payload.size()];
        NSString *payloadHash = Digest(payload);
        result[@"object_id"] = Text(parsed.objectId.c_str());
        result[@"model"] = Text(parsed.model.c_str());
        result[@"resource_key"] = Text(parsed.resourceKey.c_str());
        result[@"resource_size"] = @(parsed.payload.size());
        result[@"resource_sha256"] = payloadHash;
        Require([payloadHash isEqualToString:Text(Expected::PayloadSHA256)], @"Retrieved resource SHA-256 mismatch");
        NSDictionary *after = Snapshot(fixtureDirectory);
        result[@"inputs_after"] = after;
        Require([before isEqual:after], @"Input tree was modified or an unexpected file was created");
        result[@"inputs_unchanged"] = @YES;
        [events addObject:@"Exact resource bytes/SHA-256, bounded stream and unchanged input tree verified"];
        result[@"status"] = @"PASS"; // Only after real engine calls and all integrity checks.
    }
    catch (const std::exception& error)
    {
        result[@"error"] = Text(error.what()) ?: @"Unknown C++ failure";
        [events addObject:@"FAIL: data check did not complete; no successful device execution is asserted"];
        // Preserve integrity findings after a failed parser/resource check too.
        // An unavailable post-failure snapshot remains UNKNOWN, never assumed unchanged.
        if (result[@"inputs_before"])
        {
            try
            {
                NSDictionary *after = Snapshot(fixtureDirectory);
                result[@"inputs_after"] = after;
                result[@"inputs_unchanged"] = @([result[@"inputs_before"] isEqual:after]);
            }
            catch (const std::exception& integrityError)
            {
                result[@"integrity_check_error"] = Text(integrityError.what()) ?: @"Post-failure snapshot unavailable";
            }
        }
    }
    result[@"elapsed_ms"] = @((NSProcessInfo.processInfo.systemUptime - start) * 1000.0);
    result[@"finished_utc"] = [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]];
    return result;
}
