cmake_minimum_required(VERSION 3.24)

# Standalone project. Never add_subdirectory() this from OpenMW's build.
set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
project(IOSRenderSmoke VERSION 0.1.0 LANGUAGES CXX OBJCXX)

string(TOLOWER "${CMAKE_OSX_SYSROOT}" _smoke_sdk)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT _smoke_sdk MATCHES "iphoneos")
    message(FATAL_ERROR "This experiment requires macOS/Xcode and the iphoneos SDK (device, not simulator). See README.md.")
endif()
if(NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
    message(FATAL_ERROR "Set CMAKE_OSX_ARCHITECTURES=arm64 for the physical-device test.")
endif()

set(MOLTENVK_ROOT "" CACHE PATH "Existing extracted MoltenVK distribution or static MoltenVK.xcframework")
set(SMOKE_BUNDLE_ID "org.openmw.experiments.ios-render-smoke" CACHE STRING "Own bundle identifier for device signing")
set(SMOKE_DEVELOPMENT_TEAM "" CACHE STRING "Apple development team, needed for a signed device build")
option(SMOKE_UNSIGNED "Compile an unsigned device app; cannot install until signed" OFF)
if(NOT IS_DIRECTORY "${MOLTENVK_ROOT}")
    message(FATAL_ERROR "Supply -DMOLTENVK_ROOT=/absolute/path/to/existing/distribution. Configuration downloads nothing.")
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/resolve_moltenvk.py"
        --root "${MOLTENVK_ROOT}" --output "${CMAKE_CURRENT_BINARY_DIR}/moltenvk-resolved.cmake"
    RESULT_VARIABLE _resolve_result OUTPUT_VARIABLE _resolve_output ERROR_VARIABLE _resolve_error)
if(NOT _resolve_result EQUAL 0)
    message(FATAL_ERROR "Cannot resolve MoltenVK device dependency: ${_resolve_error}${_resolve_output}")
endif()
include("${CMAKE_CURRENT_BINARY_DIR}/moltenvk-resolved.cmake")
message(STATUS "MoltenVK device archive: ${SMOKE_MOLTENVK_LIBRARY}")
message(STATUS "Matching Vulkan headers: ${SMOKE_VULKAN_INCLUDE_DIR}")

add_executable(IOSRenderSmoke MACOSX_BUNDLE src/main.mm)
target_compile_features(IOSRenderSmoke PRIVATE cxx_std_17)
set_target_properties(IOSRenderSmoke PROPERTIES
    OBJCXX_STANDARD 17 OBJCXX_STANDARD_REQUIRED YES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "${SMOKE_BUNDLE_ID}"
    MACOSX_BUNDLE_BUNDLE_NAME "iOS Render Smoke"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    MACOSX_BUNDLE_BUNDLE_VERSION "1"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1"
    XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_DEBUG_INFORMATION_FORMAT "dwarf-with-dsym"
    XCODE_GENERATE_SCHEME TRUE)
target_compile_options(IOSRenderSmoke PRIVATE -fobjc-arc -Wall -Wextra)
target_compile_definitions(IOSRenderSmoke PRIVATE VK_USE_PLATFORM_METAL_EXT=1 VK_ENABLE_BETA_EXTENSIONS=1)
target_include_directories(IOSRenderSmoke SYSTEM PRIVATE "${SMOKE_VULKAN_INCLUDE_DIR}")
target_link_libraries(IOSRenderSmoke PRIVATE "${SMOKE_MOLTENVK_LIBRARY}")
target_link_options(IOSRenderSmoke PRIVATE -ObjC)
foreach(_framework UIKit Foundation QuartzCore Metal CoreGraphics IOSurface)
    find_library(SMOKE_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSRenderSmoke PRIVATE "${SMOKE_${_framework}}")
endforeach()
if(SMOKE_UNSIGNED)
    set_target_properties(IOSRenderSmoke PROPERTIES XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
elseif(SMOKE_DEVELOPMENT_TEAM)
    set_target_properties(IOSRenderSmoke PROPERTIES XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${SMOKE_DEVELOPMENT_TEAM}")
endif()
