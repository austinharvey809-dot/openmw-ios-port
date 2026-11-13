cmake_minimum_required(VERSION 3.24)
project(OpenMWTexturedNif LANGUAGES CXX)
get_filename_component(G1C_ROOT "${CMAKE_CURRENT_SOURCE_DIR}" ABSOLUTE)
get_filename_component(G1C_REPO "${G1C_ROOT}/../../.." ABSOLUTE)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G1C_ROOT}/tools/resources.py" audit
    --osg-reference "${OPENMW_ESM_OSG_SOURCE}" COMMAND_ERROR_IS_FATAL ANY)
# Reuse the completed host parser/geometry/provider without a second OSG instance.
add_subdirectory("${G1C_ROOT}/.." "${CMAKE_CURRENT_BINARY_DIR}/g1a" EXCLUDE_FROM_ALL)
set(G1C_OSG_SOURCE "${OPENMW_ESM_OSG_SOURCE}")
set(G1C_GEOMETRY_TARGET g1a-geometry)
set(G1C_GENERATED_INCLUDE "${CMAKE_CURRENT_BINARY_DIR}/g1a/g0b/osg/include")
include(cmake/texture.cmake)
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g1c-host-products-$<CONFIG>.txt"
    CONTENT "$<TARGET_FILE:openmw-textured-nif-check>\n$<TARGET_FILE:openmw-nif-geometry-check>\n$<TARGET_FILE:openmw-nif-parse-check>\n")
enable_testing()
add_test(NAME g1c-texture-ownership-and-negatives
    COMMAND "${Python3_EXECUTABLE}" "${G1C_ROOT}/tools/run_texture.py"
        --product "$<TARGET_FILE:openmw-textured-nif-check>"
        --evidence "${CMAKE_CURRENT_BINARY_DIR}/evidence")
