// SPDX-License-Identifier: GPL-3.0-or-later
#import "Audit.hpp"
#import <CoreFoundation/CoreFoundation.h>

namespace
{
    bool boolean(id value) { return value && CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID(); }
    bool number(id value) { return [value isKindOfClass:NSNumber.class] && !boolean(value); }
    bool dictionary(id value) { return [value isKindOfClass:NSDictionary.class]; }
    bool array(id value) { return [value isKindOfClass:NSArray.class]; }

    bool version(id value)
    {
        if (!array(value) || [value count] != 3) return false;
        for (id component in value) if (!number(component) || [component doubleValue] < 0) return false;
        return true;
    }
    NSComparisonResult compareVersions(NSArray* left, NSArray* right)
    {
        for (NSUInteger i = 0; i != 3; ++i)
        {
            const NSComparisonResult result = [left[i] compare:right[i]];
            if (result != NSOrderedSame) return result;
        }
        return NSOrderedSame;
    }

    NSDictionary* result(NSDictionary* row, NSString* status, id actual, NSString* reason)
    {
        NSMutableDictionary* item = [row mutableCopy];
        item[@"status"] = status;
        item[@"actual"] = actual ?: NSNull.null;
        item[@"reason"] = reason;
        return item;
    }

    NSDictionary* evaluate(NSDictionary* row, NSDictionary* device, NSDictionary* instance)
    {
        if (!dictionary(row)) return @{@"status": @"unknown", @"reason": @"Malformed requirement row", @"actual": NSNull.null};
        NSString* kind = row[@"kind"];
        NSString* key = row[@"key"];
        if ([kind isEqual:@"any"] || [kind isEqual:@"all"])
        {
            const bool conjunction = [kind isEqual:@"all"];
            id rows = row[conjunction ? @"all_of" : @"any_of"];
            if (!array(rows) || ![rows count]) return result(row, @"unknown", nil, @"Missing requirement branches");
            NSMutableArray* children = [NSMutableArray array];
            bool supported = false, unsupported = false, unknown = false;
            for (id child in rows)
            {
                NSDictionary* evaluated = evaluate(child, device, instance);
                [children addObject:evaluated];
                supported |= [evaluated[@"status"] isEqual:@"supported"];
                unsupported |= [evaluated[@"status"] isEqual:@"unsupported"];
                unknown |= [evaluated[@"status"] isEqual:@"unknown"];
            }
            NSString* status = conjunction ? (unsupported ? @"unsupported" : unknown ? @"unknown" : @"supported")
                : (supported ? @"supported" : unknown ? @"unknown" : @"unsupported");
            NSMutableDictionary* item = [result(row, status, nil, @"Explicit conjunction/alternatives preserve profile capability groups") mutableCopy];
            item[@"alternatives"] = children;
            return item;
        }
        if ([kind isEqual:@"manual"])
            return result(row, @"unknown", nil, @"Requires a build, execution or presentation test; capability queries cannot establish this");
        id actual = nil;
        if ([kind isEqual:@"api"]) actual = device[@"identity"][@"api_version"];
        else if ([kind isEqual:@"extension"] || [kind isEqual:@"instance_extension"])
        {
            id extensions = [kind isEqual:@"extension"] ? device[@"extensions"] : instance[@"extensions"];
            if (!dictionary(extensions) || ![key isKindOfClass:NSString.class])
                return result(row, @"unknown", nil, @"Extension enumeration unavailable");
            id api = [kind isEqual:@"instance_extension"] ? instance[@"api_version"] : device[@"identity"][@"api_version"];
            if (version(row[@"core_since"]) && version(api))
                if (compareVersions(api, row[@"core_since"]) != NSOrderedAscending)
                    return result(row, @"supported", api, @"Explicit requirement permits this core promotion; individual feature bits remain separate checks");
            if (!extensions[key]) return result(row, @"unsupported", @NO, @"Extension absent from completed enumeration");
            actual = extensions[key];
            if (!row[@"value"]) return result(row, @"supported", actual, @"Extension advertised; execution correctness untested");
        }
        else if ([kind isEqual:@"format"])
            actual = device[@"formats"][row[@"format"] ?: @""][key ?: @""];
        else
        {
            NSString* group = [@{@"feature": @"features", @"limit": @"limits", @"property": @"properties", @"surface": @"surface"} objectForKey:kind ?: @""];
            if (!group) return result(row, @"unknown", nil, @"Unsupported requirement kind");
            if ([key isKindOfClass:NSString.class] && dictionary(device[group])) actual = device[group][key];
        }
        if (!actual || actual == NSNull.null)
            return result(row, @"unknown", nil, @"Field was not queried or a query failed; missing is not false");
        id expected = row[@"value"];
        NSString* op = row[@"op"] ?: @"eq";
        bool supported = false;
        if ([kind isEqual:@"api"] && version(actual) && version(expected))
        {
            const auto comparison = compareVersions(actual, expected);
            if ([op isEqual:@"ge"]) supported = comparison != NSOrderedAscending;
            else if ([op isEqual:@"le"]) supported = comparison != NSOrderedDescending;
            else if ([op isEqual:@"eq"]) supported = comparison == NSOrderedSame;
            else return result(row, @"unknown", actual, @"Unsupported version comparison");
        }
        else if ([op isEqual:@"eq"] && boolean(expected) && boolean(actual)) supported = [actual boolValue] == [expected boolValue];
        else if (number(actual) && number(expected))
        {
            const auto comparison = [actual compare:expected];
            if ([op isEqual:@"ge"]) supported = comparison != NSOrderedAscending;
            else if ([op isEqual:@"le"]) supported = comparison != NSOrderedDescending;
            else if ([op isEqual:@"eq"]) supported = comparison == NSOrderedSame;
            else if ([op isEqual:@"bits_all"]) supported = ([actual unsignedLongLongValue] & [expected unsignedLongLongValue]) == [expected unsignedLongLongValue];
            else return result(row, @"unknown", actual, @"Unsupported numeric comparison");
        }
        else return result(row, @"unknown", actual, @"Missing/mismatched comparison value or unsupported data type");
        return result(row, supported ? @"supported" : @"unsupported", actual,
            supported ? @"Requirement satisfied as reported; execution correctness untested" : @"Reported value does not meet the requirement");
    }

    NSDictionary* evaluateGroup(id rows, NSDictionary* device, NSDictionary* instance)
    {
        NSMutableArray* checks = [NSMutableArray array];
        NSMutableDictionary* counts = [@{@"supported": @0, @"unsupported": @0, @"unknown": @0} mutableCopy];
        bool failed = false, missing = false;
        if (!array(rows) || ![rows count])
            return @{@"status": @"unknown", @"checks": checks, @"counts": counts, @"reason": @"Empty/missing requirement group"};
        for (id row in rows)
        {
            NSDictionary* item = evaluate(row, device, instance);
            [checks addObject:item];
            NSString* status = item[@"status"];
            counts[status] = @([counts[status] unsignedIntegerValue] + 1);
            if (![item[@"severity"] isEqual:@"advisory"])
            {
                failed |= [status isEqual:@"unsupported"];
                missing |= [status isEqual:@"unknown"];
            }
        }
        return @{@"status": failed ? @"unsupported" : missing ? @"unknown" : @"supported", @"checks": checks, @"counts": counts};
    }

    void appendFailures(NSMutableString* text, NSDictionary* row, NSUInteger depth, NSUInteger& remaining)
    {
        if ([row[@"status"] isEqual:@"supported"] || !remaining) return;
        --remaining;
        [text appendFormat:@"%*s%@: %@ - %@\n", static_cast<int>(depth * 2), "",
            row[@"id"] ?: row[@"key"] ?: @"check", row[@"status"], row[@"reason"]];
        for (NSDictionary* child in row[@"alternatives"] ?: @[]) appendFailures(text, child, depth + 1, remaining);
    }
}

NSDictionary* evaluateCapabilities(NSDictionary* capabilities, NSDictionary* requirements)
{
    NSMutableArray* devices = [NSMutableArray array];
    for (NSDictionary* device in capabilities[@"devices"] ?: @[])
    {
        NSMutableDictionary* groups = [NSMutableDictionary dictionary];
        NSDictionary* profiles = requirements[@"profiles"];
        if (dictionary(profiles))
            for (NSString* name in profiles)
                groups[name] = evaluateGroup(profiles[name][@"requirements"], device, capabilities[@"instance"]);
        groups[@"runtime_checks"] = evaluateGroup(requirements[@"runtime_checks"], device, capabilities[@"instance"]);
        [devices addObject:@{@"identity": device[@"identity"] ?: @{}, @"groups": groups,
            @"query_status": device[@"query_status"] ?: @"unknown", @"query_diagnostics": device[@"unknown"] ?: @[]}];
    }
    return @{@"schema_version": @1, @"mesa_version": requirements[@"mesa_version"] ?: @"unknown",
        @"audit_id": capabilities[@"audit_id"] ?: NSNull.null, @"recorded_at": capabilities[@"recorded_at"] ?: NSNull.null,
        @"query_diagnostics": capabilities[@"unknown"] ?: @[],
        @"requirements_sources": requirements[@"sources"] ?: @[], @"devices": devices,
        @"scope": @"Reported capabilities only. No VkDevice, Mesa, Zink, shader, correctness, performance or thermal test was executed.",
        @"zink_viability": @"unknown_until_actual_zink_and_presentation_tests"};
}

NSString* auditSummary(NSDictionary* report)
{
    NSMutableString* text = [NSMutableString stringWithFormat:@"Mesa/Zink %@ capability audit\n\n", report[@"mesa_version"]];
    [text appendFormat:@"Audit: %@\nRecorded: %@\n\n", report[@"audit_id"] ?: @"unknown", report[@"recorded_at"] ?: @"unknown"];
    if (![report[@"devices"] count]) [text appendString:@"No Vulkan physical device reported. This audit is incomplete.\n\n"];
    for (NSString* diagnostic in report[@"query_diagnostics"]) [text appendFormat:@"QUERY: %@\n", diagnostic];
    for (NSDictionary* device in report[@"devices"])
    {
        [text appendFormat:@"%@\n", device[@"identity"][@"device_name"] ?: @"Unknown device"];
        for (NSString* diagnostic in device[@"query_diagnostics"]) [text appendFormat:@"QUERY: %@\n", diagnostic];
        NSDictionary* groups = device[@"groups"];
        for (NSString* name in [[groups allKeys] sortedArrayUsingSelector:@selector(compare:)])
        {
            NSDictionary* group = groups[name];
            [text appendFormat:@"%@: %@ (%@ supported / %@ unsupported / %@ unknown)\n", name, group[@"status"],
                group[@"counts"][@"supported"], group[@"counts"][@"unsupported"], group[@"counts"][@"unknown"]];
            NSUInteger remaining = 32;
            for (NSDictionary* check in group[@"checks"]) appendFailures(text, check, 1, remaining);
            if (!remaining) [text appendString:@"  Further details are in comparison-latest.json\n"];
        }
        [text appendString:@"\n"];
    }
    [text appendString:@"Supported means reported, not validated. Actual display FPS: unavailable.\nNo Mesa/Zink was built or run. Direct iOS Zink WSI remains a separate blocker.\n"];
    return text;
}
