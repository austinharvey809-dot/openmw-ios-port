cmake_minimum_required(VERSION 3.24)
project(OpenMWNifGeometryFoundation LANGUAGES CXX)
if(NOT APPLE OR CMAKE_CROSSCOMPILING OR NOT CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    message(FATAL_ERROR "G1A requires a native macOS host; no iPhoneOS/GPU target is provided")
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/contracts.py"
    --osg-source "${OPENMW_ESM_OSG_SOURCE}" RESULT_VARIABLE _audit)
if(NOT _audit STREQUAL "0")
    message(FATAL_ERROR "G1A source, fixture, baseline or preservation audit failed")
endif()

# Exactly one unmodified G0B provider: genuine parser + E/D + OSG/OpenThreads + Bullet.
# G0C's GLES2 adapter and the ANGLE renderer are deliberately not added here.
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-nif-smoke"
    "${CMAKE_CURRENT_BINARY_DIR}/g0b" EXCLUDE_FROM_ALL)
get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-nif-smoke/data/fixture-manifest.json" _fixtures)
string(JSON _expected_sha GET "${_fixtures}" files triangle-candidate.nif sha256)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/generated/G1AExpectations.hpp"
    "#pragma once\nnamespace G1A { inline constexpr char ExpectedNifSHA256[] = \"${_expected_sha}\"; }\n")
add_library(g1a-geometry STATIC src/GeometryAdapter.cpp)
target_include_directories(g1a-geometry PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src"
    PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(g1a-geometry PUBLIC openmw-ios-nif-parser)
target_compile_features(g1a-geometry PUBLIC cxx_std_20)
target_compile_definitions(g1a-geometry PUBLIC OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
set_target_properties(g1a-geometry PROPERTIES CXX_EXTENSIONS OFF)
add_executable(openmw-nif-geometry-check tests/geometry_check.cpp)
target_link_libraries(openmw-nif-geometry-check PRIVATE g1a-geometry)
set_target_properties(openmw-nif-geometry-check PROPERTIES CXX_EXTENSIONS OFF)
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g1a-products-$<CONFIG>.txt"
    CONTENT "$<TARGET_FILE:openmw-nif-geometry-check>\n$<TARGET_FILE:openmw-nif-parse-check>\n")
enable_testing()
add_test(NAME g1a-owned-geometry-and-six-parser-cases
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/run_geometry.py"
    --geometry "$<TARGET_FILE:openmw-nif-geometry-check>"
    --parser "$<TARGET_FILE:openmw-nif-parse-check>"
    --osg-source "${OPENMW_ESM_OSG_SOURCE}"
    --evidence "${CMAKE_CURRENT_BINARY_DIR}/evidence")
