cmake_minimum_required(VERSION 3.24)

# Independent query application. Do not configure the OpenMW root project.
set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
project(IOSZinkCaps VERSION 0.1.0 LANGUAGES CXX OBJCXX)

string(TOLOWER "${CMAKE_OSX_SYSROOT}" _caps_sdk)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT _caps_sdk MATCHES "iphoneos")
    message(FATAL_ERROR "IOSZinkCaps requires macOS/Xcode with the iphoneos device SDK.")
endif()
if(NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
    message(FATAL_ERROR "Set CMAKE_OSX_ARCHITECTURES=arm64; simulator/macOS builds do not audit the iPhone.")
endif()

set(MOLTENVK_ROOT "" CACHE PATH "Previously extracted public MoltenVK iOS distribution")
set(CAPS_BUNDLE_ID "org.openmw.experiments.ios-zink-caps" CACHE STRING "Own bundle identifier for local signing")
set(CAPS_DEVELOPMENT_TEAM "" CACHE STRING "Apple development team for a locally signed build")
option(CAPS_UNSIGNED "Build an unsigned app; signing is required before installation" OFF)
if(NOT IS_DIRECTORY "${MOLTENVK_ROOT}")
    message(FATAL_ERROR "Supply MOLTENVK_ROOT pointing to existing MoltenVK; configuration downloads nothing.")
endif()

find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/../ios-render-smoke/tools/resolve_moltenvk.py"
        --root "${MOLTENVK_ROOT}" --output "${CMAKE_CURRENT_BINARY_DIR}/moltenvk-resolved.cmake"
    RESULT_VARIABLE _caps_resolve_result OUTPUT_VARIABLE _caps_resolve_output ERROR_VARIABLE _caps_resolve_error)
if(NOT _caps_resolve_result EQUAL 0)
    message(FATAL_ERROR "MoltenVK device dependency resolution failed: ${_caps_resolve_error}${_caps_resolve_output}")
endif()
include("${CMAKE_CURRENT_BINARY_DIR}/moltenvk-resolved.cmake")
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE CAPS_SOURCE_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT CAPS_SOURCE_REVISION)
    set(CAPS_SOURCE_REVISION "unknown")
endif()

set(_caps_requirements "${CMAKE_CURRENT_SOURCE_DIR}/data/mesa-25.1.9-requirements.json")
if(NOT EXISTS "${_caps_requirements}")
    message(FATAL_ERROR "Missing checked-in audited Mesa 25.1.9 requirements resource.")
endif()
set_source_files_properties("${_caps_requirements}" PROPERTIES MACOSX_PACKAGE_LOCATION Resources HEADER_FILE_ONLY TRUE)
add_executable(IOSZinkCaps MACOSX_BUNDLE src/main.mm src/Capabilities.mm src/Audit.mm "${_caps_requirements}")
target_compile_features(IOSZinkCaps PRIVATE cxx_std_17)
target_compile_options(IOSZinkCaps PRIVATE -fobjc-arc -Wall -Wextra)
target_compile_definitions(IOSZinkCaps PRIVATE VK_USE_PLATFORM_METAL_EXT=1 VK_ENABLE_BETA_EXTENSIONS=1)
target_include_directories(IOSZinkCaps SYSTEM PRIVATE "${SMOKE_VULKAN_INCLUDE_DIR}")
target_link_libraries(IOSZinkCaps PRIVATE "${SMOKE_MOLTENVK_LIBRARY}")
target_link_options(IOSZinkCaps PRIVATE -ObjC)
foreach(_framework UIKit Foundation CoreFoundation QuartzCore Metal CoreGraphics IOSurface GameController)
    find_library(CAPS_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSZinkCaps PRIVATE "${CAPS_${_framework}}")
endforeach()
set_target_properties(IOSZinkCaps PROPERTIES
    OBJCXX_STANDARD 17 OBJCXX_STANDARD_REQUIRED YES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "${CAPS_BUNDLE_ID}"
    MACOSX_BUNDLE_BUNDLE_NAME "iOS Zink Capabilities"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    MACOSX_BUNDLE_BUNDLE_VERSION "1"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1"
    XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_DEBUG_INFORMATION_FORMAT "dwarf-with-dsym"
    XCODE_GENERATE_SCHEME TRUE)
if(CAPS_UNSIGNED)
    set_target_properties(IOSZinkCaps PROPERTIES XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
elseif(CAPS_DEVELOPMENT_TEAM)
    set_target_properties(IOSZinkCaps PROPERTIES XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${CAPS_DEVELOPMENT_TEAM}")
endif()
