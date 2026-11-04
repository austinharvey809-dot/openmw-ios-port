// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#import <Foundation/Foundation.h>

// Query comparisons only: a supported row is a reported capability, not a tested implementation.
NSDictionary* evaluateCapabilities(NSDictionary* capabilities, NSDictionary* requirements);
NSString* auditSummary(NSDictionary* report);
