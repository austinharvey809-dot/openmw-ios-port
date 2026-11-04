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
option(SMOKE_CLEAR_ONLY "Build the original clear-only fallback without shaders" OFF)
option(SMOKE_TRIANGLE_ONLY "Build an independent triangle fallback without cube shaders or resources" OFF)
set(SMOKE_START_MODE "cube" CACHE STRING "Initial geometry mode: cube or triangle")
set_property(CACHE SMOKE_START_MODE PROPERTY STRINGS cube triangle)
if(NOT SMOKE_START_MODE MATCHES "^(cube|triangle)$")
    message(FATAL_ERROR "SMOKE_START_MODE must be cube or triangle.")
endif()
set(SMOKE_RENDER_MODE "${SMOKE_START_MODE}")
set(SMOKE_CUBE_AVAILABLE true)
if(SMOKE_TRIANGLE_ONLY)
    set(SMOKE_RENDER_MODE "triangle")
    set(SMOKE_CUBE_AVAILABLE false)
endif()
if(SMOKE_CLEAR_ONLY)
    set(SMOKE_RENDER_MODE "clear")
    set(SMOKE_CUBE_AVAILABLE false)
endif()
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
if(NOT SMOKE_CLEAR_ONLY)
    # This is a host executable, never an iphoneos program or runtime dependency.
    find_program(SMOKE_GLSLANG_VALIDATOR NAMES glslangValidator glslang
        NO_CMAKE_FIND_ROOT_PATH REQUIRED)
    execute_process(COMMAND "${SMOKE_GLSLANG_VALIDATOR}" --version
        RESULT_VARIABLE _shader_result OUTPUT_VARIABLE _shader_version ERROR_VARIABLE _shader_error)
    if(NOT _shader_result EQUAL 0)
        message(FATAL_ERROR "Cannot execute host glslang: ${_shader_error}")
    endif()
    message(STATUS "Host shader compiler: ${SMOKE_GLSLANG_VALIDATOR}\n${_shader_version}")
    set(_smoke_shaders)
    set(_smoke_geometry_modes triangle)
    if(NOT SMOKE_TRIANGLE_ONLY)
        list(APPEND _smoke_geometry_modes cube)
    endif()
    foreach(_mode IN LISTS _smoke_geometry_modes)
        foreach(_stage vert frag)
            set(_source "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${_mode}.${_stage}")
            set(_output "${CMAKE_CURRENT_BINARY_DIR}/shaders/${_mode}.${_stage}.spv")
            add_custom_command(OUTPUT "${_output}"
                COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/shaders"
                COMMAND "${SMOKE_GLSLANG_VALIDATOR}" -V --target-env vulkan1.0
                    -S "${_stage}" -e main -o "${_output}" "${_source}"
                DEPENDS "${_source}" "${SMOKE_GLSLANG_VALIDATOR}"
                COMMENT "Compile ${_mode}.${_stage} to SPIR-V 1.0" VERBATIM)
            set_source_files_properties("${_output}" PROPERTIES
                GENERATED TRUE HEADER_FILE_ONLY TRUE MACOSX_PACKAGE_LOCATION Resources)
            list(APPEND _smoke_shaders "${_output}")
        endforeach()
    endforeach()
    set(_smoke_assets)
    if(NOT SMOKE_TRIANGLE_ONLY)
        set(_checkerboard "${CMAKE_CURRENT_BINARY_DIR}/assets/checkerboard.rgba")
        add_custom_command(OUTPUT "${_checkerboard}"
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_checkerboard.py"
                --output "${_checkerboard}"
            DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/generate_checkerboard.py"
            COMMENT "Generate original 32x32 RGBA8 checkerboard" VERBATIM)
        set_source_files_properties("${_checkerboard}" PROPERTIES
            GENERATED TRUE HEADER_FILE_ONLY TRUE MACOSX_PACKAGE_LOCATION Resources)
        list(APPEND _smoke_assets "${_checkerboard}")
    endif()
    add_custom_target(IOSRenderSmokeShaders DEPENDS ${_smoke_shaders} ${_smoke_assets})
    add_dependencies(IOSRenderSmoke IOSRenderSmokeShaders)
    target_sources(IOSRenderSmoke PRIVATE ${_smoke_shaders} ${_smoke_assets})
endif()
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
foreach(_framework UIKit Foundation QuartzCore Metal CoreGraphics IOSurface GameController)
    find_library(SMOKE_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSRenderSmoke PRIVATE "${SMOKE_${_framework}}")
endforeach()
if(SMOKE_UNSIGNED)
    set_target_properties(IOSRenderSmoke PROPERTIES XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
elseif(SMOKE_DEVELOPMENT_TEAM)
    set_target_properties(IOSRenderSmoke PROPERTIES XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${SMOKE_DEVELOPMENT_TEAM}")
endif()
