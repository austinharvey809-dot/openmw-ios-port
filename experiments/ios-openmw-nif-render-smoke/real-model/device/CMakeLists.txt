cmake_minimum_required(VERSION 3.24)
get_filename_component(G1D_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
# The completed provider is evaluated once; no upstream/completed source edits.
add_subdirectory("${G1D_ROOT}/../textured/device" "${CMAKE_CURRENT_BINARY_DIR}/g1c" EXCLUDE_FROM_ALL)
project(OpenMWRealModelDevice LANGUAGES C CXX OBJCXX)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G1D_ROOT}/tools/provenance.py" --output "${CMAKE_CURRENT_BINARY_DIR}/generated" COMMAND_ERROR_IS_FATAL ANY)
set(G1D_BASE g1c-texture)
include("${G1D_ROOT}/common.cmake")
add_executable(IOSOpenMWRealModel MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
get_target_property(_includes IOSOpenMWTexturedNif INCLUDE_DIRECTORIES)
get_target_property(_links IOSOpenMWTexturedNif LINK_LIBRARIES)
target_include_directories(IOSOpenMWRealModel PRIVATE ${_includes})
target_include_directories(IOSOpenMWRealModel PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
set_source_files_properties("${CMAKE_CURRENT_BINARY_DIR}/generated/g1d-build.json" PROPERTIES MACOSX_PACKAGE_LOCATION ".")
target_sources(IOSOpenMWRealModel PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/g1d-build.json")
target_link_libraries(IOSOpenMWRealModel PRIVATE g1d-model ${_links})
target_include_directories(g1d-model BEFORE PUBLIC "${_generated}" "${ANGLE_ROOT}/include")
target_include_directories(g1d-dds BEFORE PUBLIC "${_generated}" "${ANGLE_ROOT}/include")
target_compile_options(IOSOpenMWRealModel PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWRealModel PRIVATE "-Wl,-no_adhoc_codesign")
set_target_properties(IOSOpenMWRealModel PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF CXX_EXTENSIONS OFF
    BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
    MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
    MACOSX_BUNDLE_INFO_PLIST "${G1D_ROOT}/device/Info.plist.in"
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
add_custom_command(TARGET IOSOpenMWRealModel POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_CURRENT_BINARY_DIR}/g1c/prepared/resources/Frameworks" "$<TARGET_BUNDLE_DIR:IOSOpenMWRealModel>/Frameworks"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${CMAKE_CURRENT_BINARY_DIR}/g1c/prepared/resources/Licenses" "$<TARGET_BUNDLE_DIR:IOSOpenMWRealModel>/Licenses"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${CMAKE_CURRENT_BINARY_DIR}/g1c/prepared/resources/Provenance" "$<TARGET_BUNDLE_DIR:IOSOpenMWRealModel>/Provenance")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g1d-product-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:IOSOpenMWRealModel>\n$<TARGET_BUNDLE_DIR:IOSOpenMWRealModel>\n")
