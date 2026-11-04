// SPDX-License-Identifier: GPL-3.0-or-later
#import "Audit.hpp"
#include <cstdio>

int main(int argc, char** argv)
{
    @autoreleasepool
    {
        if (argc != 3) return 2;
        NSData* capsData = [NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[1]]];
        NSData* reqData = [NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]];
        if (!capsData || !reqData) return 2;
        NSError* error = nil;
        NSDictionary* caps = [NSJSONSerialization JSONObjectWithData:capsData options:0 error:&error];
        NSDictionary* requirements = [NSJSONSerialization JSONObjectWithData:reqData options:0 error:&error];
        if (error || ![caps isKindOfClass:NSDictionary.class] || ![requirements isKindOfClass:NSDictionary.class]) return 2;
        NSDictionary* report = evaluateCapabilities(caps, requirements);
        NSData* output = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingSortedKeys error:&error];
        if (!output || error) return 1;
        std::fwrite(output.bytes, 1, output.length, stdout);
        std::fputc('\n', stdout);
        return 0;
    }
}
