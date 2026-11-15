cmake_minimum_required(VERSION 3.24)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")
get_filename_component(G3_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
add_subdirectory("${G3_ROOT}/../ios-openmw-interior-smoke/device" "${CMAKE_CURRENT_BINARY_DIR}/provider" EXCLUDE_FROM_ALL)
project(OpenMWExteriorDevice LANGUAGES C CXX OBJCXX)
include("${G3_ROOT}/common.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G3_ROOT}/tools/provenance.py" --output "${G3_GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
add_executable(IOSOpenMWExterior MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
get_target_property(_includes IOSOpenMWInterior INCLUDE_DIRECTORIES)
get_target_property(_links IOSOpenMWInterior LINK_LIBRARIES)
list(REMOVE_ITEM _links g2-cell)
target_include_directories(IOSOpenMWExterior PRIVATE ${_includes} "${G3_GENERATED}")
# Digest calls the accepted G1A::sha256 implementation compiled by this target.
# Keep its declaration/include interface and link ownership explicit.
target_link_libraries(IOSOpenMWExterior PRIVATE g3-world g1b-geometry ${_links})
# The SDK probe consumes this same explicit dependency inventory before ANGLE builds.
file(READ "${G3_ROOT}/../ios-openmw-interior-smoke/device/frameworks.json" _g2_frameworks)
string(JSON _g2_framework_count LENGTH "${_g2_frameworks}")
math(EXPR _g2_framework_last "${_g2_framework_count} - 1")
foreach(_index RANGE 0 ${_g2_framework_last})
  string(JSON _framework GET "${_g2_frameworks}" ${_index})
  find_library(G2_${_framework} NAMES "${_framework}" REQUIRED)
  target_link_libraries(IOSOpenMWExterior PRIVATE "${G2_${_framework}}")
endforeach()
target_include_directories(g3-world BEFORE PUBLIC "${_g3_osg_include}" "${ANGLE_ROOT}/include")
set_source_files_properties("${G3_GENERATED}/g3-build.json" PROPERTIES MACOSX_PACKAGE_LOCATION ".")
target_sources(IOSOpenMWExterior PRIVATE "${G3_GENERATED}/g3-build.json")
target_compile_options(IOSOpenMWExterior PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWExterior PRIVATE "-Wl,-no_adhoc_codesign")
set_target_properties(IOSOpenMWExterior PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF CXX_EXTENSIONS OFF
  BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
  MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
  MACOSX_BUNDLE_INFO_PLIST "${G3_ROOT}/device/Info.plist.in" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
foreach(_dir Frameworks Licenses Provenance)
  add_custom_command(TARGET IOSOpenMWExterior POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${CMAKE_CURRENT_BINARY_DIR}/provider/provider/g1c/prepared/resources/${_dir}" "$<TARGET_BUNDLE_DIR:IOSOpenMWExterior>/${_dir}")
endforeach()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g3-product-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:IOSOpenMWExterior>\n$<TARGET_BUNDLE_DIR:IOSOpenMWExterior>\n")
