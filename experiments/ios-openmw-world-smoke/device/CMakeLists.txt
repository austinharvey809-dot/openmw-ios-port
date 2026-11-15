cmake_minimum_required(VERSION 3.24)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")
get_filename_component(G4_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
add_subdirectory("${G4_ROOT}/../ios-openmw-exterior-smoke/device" "${CMAKE_CURRENT_BINARY_DIR}/provider" EXCLUDE_FROM_ALL)
project(OpenMWWorldDevice LANGUAGES C CXX OBJCXX)
set(G4_OSG_SOURCE "${OSG_SOURCE}")
get_target_property(_osg_binary osg BINARY_DIR)
get_filename_component(G4_OSG_GENERATED_INCLUDE "${_osg_binary}/../../include" ABSOLUTE)
include("${G4_ROOT}/cmake/engine.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/provenance.py"
  --output "${G4_GENERATED}" --dependencies "${G4_DEPENDENCIES_SOURCE}" COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
add_executable(IOSOpenMWWorld MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
get_target_property(_includes IOSOpenMWExterior INCLUDE_DIRECTORIES)
get_target_property(_links IOSOpenMWExterior LINK_LIBRARIES)
list(REMOVE_ITEM _links g3-world g2-cell g1d-model g1c-texture g1b-geometry)
target_include_directories(IOSOpenMWWorld PRIVATE ${_includes} "${G4_GENERATED}")
target_include_directories(IOSOpenMWWorld BEFORE PRIVATE "${G4_OSG_GENERATED_INCLUDE}" "${ANGLE_ROOT}/include")
target_include_directories(g4-upstream BEFORE PUBLIC "${G4_OSG_GENERATED_INCLUDE}" "${ANGLE_ROOT}/include")
target_link_libraries(IOSOpenMWWorld PRIVATE g4-upstream ${_links})
target_compile_options(IOSOpenMWWorld PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWWorld PRIVATE "-Wl,-no_adhoc_codesign")
set_target_properties(IOSOpenMWWorld PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS OFF
  OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF
  BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
  MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
  MACOSX_BUNDLE_INFO_PLIST "${G4_ROOT}/device/Info.plist.in" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
# Derive shared prepared resources from the actual CMake target, not a counted
# nesting depth or a GitHub runner absolute path.
get_target_property(_textured_binary IOSOpenMWTexturedNif BINARY_DIR)
set(G4_BASE_PREPARED "${_textured_binary}/prepared")
foreach(_dir Frameworks Licenses Provenance)
  add_custom_command(TARGET IOSOpenMWWorld POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${G4_BASE_PREPARED}/resources/${_dir}" "$<TARGET_BUNDLE_DIR:IOSOpenMWWorld>/${_dir}")
endforeach()
add_custom_command(TARGET IOSOpenMWWorld POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
  "${G4_GENERATED}/public" "$<TARGET_BUNDLE_DIR:IOSOpenMWWorld>")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g4-product-$<CONFIG>.txt"
  CONTENT "$<TARGET_FILE:IOSOpenMWWorld>\n$<TARGET_BUNDLE_DIR:IOSOpenMWWorld>\n${G4_BASE_PREPARED}\n")
