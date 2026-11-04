// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#import <Foundation/Foundation.h>
@class CAMetalLayer;

// Query-only: no logical device, rendering, queue submission or readback.
// Throws std::exception on instance/enumeration failure; individual surface
// failures are retained as unknown results. All returned objects are JSON-safe.
NSDictionary* collectCapabilities(CAMetalLayer* layer);
