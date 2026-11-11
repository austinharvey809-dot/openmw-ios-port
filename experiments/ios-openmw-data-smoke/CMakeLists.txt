cmake_minimum_required(VERSION 3.24)
set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
project(IOSOpenMWDataSmoke VERSION 0.1.0 LANGUAGES CXX OBJCXX)
string(TOLOWER "${CMAKE_OSX_SYSROOT}" _sdk)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT _sdk MATCHES "iphoneos"
   OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64" OR NOT CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0")
    message(FATAL_ERROR "Requires real iPhoneOS ARM64, minimum iOS 18.0; simulator/macOS is not device evidence")
endif()
find_package(Threads REQUIRED)
# E configures D and its genuine OSG math Config in this build tree. Never add
# A/B/C archives separately: their sources overlap D. No renderer or downloads.
set(OPENMW_IOS_ESM_VFS_HOST_TESTS OFF)
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm-vfs"
    "${CMAKE_CURRENT_BINARY_DIR}/esm-vfs" EXCLUDE_FROM_ALL)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
set(_generated "${CMAKE_CURRENT_BINARY_DIR}/prepared")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_inputs.py"
    --output "${_generated}" --osg-source "${OPENMW_ESM_OSG_SOURCE}"
    --config "${CMAKE_CURRENT_BINARY_DIR}/esm-vfs/esm-reader/osg-math/include/osg/Config"
    RESULT_VARIABLE _prepare_result OUTPUT_VARIABLE _prepare_log ERROR_VARIABLE _prepare_error)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/prepare-inputs.log" "${_prepare_log}${_prepare_error}")
if(NOT _prepare_result STREQUAL "0")
    message(FATAL_ERROR "Data-smoke fixture/provenance preparation failed: ${_prepare_log}${_prepare_error}")
endif()

# First milestone: the exact reviewed E main, linked as a genuine iPhoneOS
# MH_EXECUTE. This target is link evidence only, not an installable app or test
# that can run as a subprocess on a stock iPhone.
add_executable(openmw-data-link-check "${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm-vfs/tests/esm_vfs_check.cpp")
target_link_libraries(openmw-data-link-check PRIVATE openmw-ios-esm-vfs)
target_compile_features(openmw-data-link-check PRIVATE cxx_std_20)
set_target_properties(openmw-data-link-check PROPERTIES CXX_EXTENSIONS OFF
    BUILD_RPATH "" INSTALL_RPATH "" SKIP_BUILD_RPATH TRUE
    XCODE_ATTRIBUTE_LD_RUNPATH_SEARCH_PATHS ""
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")

add_executable(IOSOpenMWDataSmoke MACOSX_BUNDLE
    src/main.mm src/DataCheck.mm src/DataCheck.hpp src/DataProbe.cpp src/DataProbe.hpp)
add_dependencies(IOSOpenMWDataSmoke openmw-data-link-check)
target_link_libraries(IOSOpenMWDataSmoke PRIVATE openmw-ios-esm-vfs)
target_include_directories(IOSOpenMWDataSmoke PRIVATE "${_generated}/include")
target_compile_features(IOSOpenMWDataSmoke PRIVATE cxx_std_20)
target_compile_options(IOSOpenMWDataSmoke PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>" -Wall -Wextra)
foreach(_framework UIKit Foundation)
    find_library(DATA_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSOpenMWDataSmoke PRIVATE "${DATA_${_framework}}")
endforeach()
set_target_properties(IOSOpenMWDataSmoke PROPERTIES
    CXX_EXTENSIONS OFF OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES
    BUILD_RPATH "" INSTALL_RPATH "" SKIP_BUILD_RPATH TRUE INSTALL_RPATH_USE_LINK_PATH FALSE
    XCODE_ATTRIBUTE_LD_RUNPATH_SEARCH_PATHS ""
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.ios-openmw-data-smoke"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "org.openmw.experiments.ios-openmw-data-smoke"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"
    XCODE_ATTRIBUTE_DEBUG_INFORMATION_FORMAT "dwarf-with-dsym")
# Let Xcode copy each prepared file into its actual product for every configuration.
# MACOSX_PACKAGE_LOCATION is relative to the iOS .app root, without a Resources prefix.
foreach(_resource IN ITEMS
    Fixtures/valid.esm Fixtures/base.bsa Fixtures/fixtures.json
    data-build.json Licenses/OpenMW-LICENSE.txt Licenses/OSG-LICENSE.txt
    Provenance/osg/Config)
    set(_resource_path "${_generated}/resources/${_resource}")
    get_filename_component(_bundle_directory "${_resource}" DIRECTORY)
    if(_bundle_directory STREQUAL "")
        set(_bundle_directory ".")
    endif()
    set_source_files_properties("${_resource_path}" PROPERTIES
        HEADER_FILE_ONLY TRUE MACOSX_PACKAGE_LOCATION "${_bundle_directory}")
    target_sources(IOSOpenMWDataSmoke PRIVATE "${_resource_path}")
endforeach()
