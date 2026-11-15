cmake_minimum_required(VERSION 3.24)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")
get_filename_component(G2_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
add_subdirectory("${G2_ROOT}/../ios-openmw-nif-render-smoke/real-model/device" "${CMAKE_CURRENT_BINARY_DIR}/provider" EXCLUDE_FROM_ALL)
project(OpenMWInteriorDevice LANGUAGES C CXX OBJCXX)
include("${G2_ROOT}/common.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G2_ROOT}/tools/provenance.py" --output "${G2_GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
add_executable(IOSOpenMWInterior MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
get_target_property(_includes IOSOpenMWRealModel INCLUDE_DIRECTORIES)
get_target_property(_links IOSOpenMWRealModel LINK_LIBRARIES)
list(REMOVE_ITEM _links g1d-model)
target_include_directories(IOSOpenMWInterior PRIVATE ${_includes} "${G2_GENERATED}")
# Digest calls the accepted G1A::sha256 implementation compiled by this target.
# Keep its declaration/include interface and link ownership explicit.
target_link_libraries(IOSOpenMWInterior PRIVATE g2-cell g1b-geometry ${_links})
target_include_directories(g2-cell BEFORE PUBLIC "${_g2_osg_include}" "${ANGLE_ROOT}/include")
set_source_files_properties("${G2_GENERATED}/g2-build.json" PROPERTIES MACOSX_PACKAGE_LOCATION ".")
target_sources(IOSOpenMWInterior PRIVATE "${G2_GENERATED}/g2-build.json")
target_compile_options(IOSOpenMWInterior PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWInterior PRIVATE "-Wl,-no_adhoc_codesign")
set_target_properties(IOSOpenMWInterior PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF CXX_EXTENSIONS OFF
  BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
  MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
  MACOSX_BUNDLE_INFO_PLIST "${G2_ROOT}/device/Info.plist.in" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
foreach(_dir Frameworks Licenses Provenance)
  add_custom_command(TARGET IOSOpenMWInterior POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_CURRENT_BINARY_DIR}/provider/g1c/prepared/resources/${_dir}" "$<TARGET_BUNDLE_DIR:IOSOpenMWInterior>/${_dir}")
endforeach()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g2-product-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:IOSOpenMWInterior>\n$<TARGET_BUNDLE_DIR:IOSOpenMWInterior>\n")
