cmake_minimum_required(VERSION 3.24)
option(OPENMW_IOS_BSA_HOST_TESTS "Build and run the synthetic BSA fixture on a native POSIX host" OFF)
if(NOT OPENMW_IOS_BSA_HOST_TESTS)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
endif()
project(OpenMWIOSBSAReader LANGUAGES CXX)

# Reuse Milestone A unchanged, with matching host/device selection. CMP0077 NEW
# makes its option respect this normal variable; no cache/engine patch is needed.
set(OPENMW_IOS_CORE_HOST_TESTS "${OPENMW_IOS_BSA_HOST_TESTS}")
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-core"
    "${CMAKE_CURRENT_BINARY_DIR}/data-core" EXCLUDE_FROM_ALL)
get_filename_component(OPENMW_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
add_library(openmw-ios-bsa-reader STATIC "${OPENMW_ROOT}/components/bsa/bsafile.cpp")
target_link_libraries(openmw-ios-bsa-reader PUBLIC openmw-ios-data-core)
target_compile_features(openmw-ios-bsa-reader PUBLIC cxx_std_20)
set_target_properties(openmw-ios-bsa-reader PROPERTIES CXX_EXTENSIONS OFF)

if(OPENMW_IOS_BSA_HOST_TESTS)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    enable_testing()
    add_executable(openmw-bsa-check tests/bsa_check.cpp)
    target_link_libraries(openmw-bsa-check PRIVATE openmw-ios-bsa-reader)
    add_test(NAME openmw-bsa-runtime
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/fixtures.py"
        --reader "$<TARGET_FILE:openmw-bsa-check>" --directory "${CMAKE_CURRENT_BINARY_DIR}/synthetic-bsa")
endif()
