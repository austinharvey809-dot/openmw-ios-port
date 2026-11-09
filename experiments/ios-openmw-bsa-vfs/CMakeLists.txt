cmake_minimum_required(VERSION 3.24)
option(OPENMW_IOS_BSA_VFS_HOST_TESTS "Build and execute the synthetic BSA/VFS fixture on a native POSIX host" OFF)
if(NOT OPENMW_IOS_BSA_VFS_HOST_TESTS)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
endif()
project(OpenMWIOSBSAVFS LANGUAGES CXX)

# CMP0077 NEW preserves these normal-variable selections in the unchanged
# Milestone B and A subprojects. No cache forcing or dependency downloads.
set(OPENMW_IOS_BSA_HOST_TESTS "${OPENMW_IOS_BSA_VFS_HOST_TESTS}")
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-bsa"
    "${CMAKE_CURRENT_BINARY_DIR}/bsa-reader" EXCLUDE_FROM_ALL)
get_filename_component(OPENMW_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
find_package(Threads REQUIRED)
add_library(openmw-ios-bsa-vfs STATIC
    src/register_bsa.cpp
    "${OPENMW_ROOT}/components/toutf8/toutf8.cpp"
    "${OPENMW_ROOT}/components/debug/debuglog.cpp"
)
target_include_directories(openmw-ios-bsa-vfs PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(openmw-ios-bsa-vfs PUBLIC openmw-ios-bsa-reader Threads::Threads)
target_compile_features(openmw-ios-bsa-vfs PUBLIC cxx_std_20)
set_target_properties(openmw-ios-bsa-vfs PROPERTIES CXX_EXTENSIONS OFF)

if(OPENMW_IOS_BSA_VFS_HOST_TESTS)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    enable_testing()
    add_executable(openmw-bsa-vfs-check tests/vfs_check.cpp)
    target_link_libraries(openmw-bsa-vfs-check PRIVATE openmw-ios-bsa-vfs)
    add_test(NAME openmw-bsa-vfs-runtime
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/fixtures.py"
        --reader "$<TARGET_FILE:openmw-bsa-vfs-check>" --directory "${CMAKE_CURRENT_BINARY_DIR}/synthetic-bsa-vfs")
endif()
