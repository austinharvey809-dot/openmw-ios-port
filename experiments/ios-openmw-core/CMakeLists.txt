cmake_minimum_required(VERSION 3.24)
option(OPENMW_IOS_CORE_HOST_TESTS "Explicit POSIX host build and runtime check; not iPhone evidence" OFF)
if(NOT OPENMW_IOS_CORE_HOST_TESTS)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
endif()
project(OpenMWIOSDataCore LANGUAGES CXX)

if(OPENMW_IOS_CORE_HOST_TESTS)
    if(NOT UNIX OR CMAKE_CROSSCOMPILING)
        message(FATAL_ERROR "Host runtime checks require a native POSIX host; use macOS/Linux")
    endif()
else()
    string(TOLOWER "${CMAKE_OSX_SYSROOT}" _sdk)
    if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS"
       OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"
       OR NOT CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0"
       OR NOT _sdk MATCHES "iphoneos")
        message(FATAL_ERROR "Select iPhoneOS ARM64, deployment 18.0; simulator/macOS is not device evidence")
    endif()
endif()

get_filename_component(OPENMW_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
# Compile actual repository translation units, without invoking the root project's
# global desktop dependency discovery or copying/patching the engine sources.
set(OPENMW_CORE_SOURCES
    components/files/conversion.cpp
    components/files/openfile.cpp
    components/files/constrainedfilestreambuf.cpp
    components/platform/fileposix.cpp
    components/vfs/manager.cpp
)
list(TRANSFORM OPENMW_CORE_SOURCES PREPEND "${OPENMW_ROOT}/")
add_library(openmw-ios-data-core STATIC ${OPENMW_CORE_SOURCES})
target_include_directories(openmw-ios-data-core PUBLIC "${OPENMW_ROOT}")
target_compile_features(openmw-ios-data-core PUBLIC cxx_std_20)
set_target_properties(openmw-ios-data-core PROPERTIES CXX_EXTENSIONS OFF)

if(OPENMW_IOS_CORE_HOST_TESTS)
    enable_testing()
    add_executable(openmw-data-core-check tests/core_check.cpp)
    target_link_libraries(openmw-data-core-check PRIVATE openmw-ios-data-core)
    add_test(NAME openmw-data-core-runtime
        COMMAND openmw-data-core-check "${CMAKE_CURRENT_BINARY_DIR}/core-runtime-fixture.bin")
endif()
