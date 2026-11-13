cmake_minimum_required(VERSION 3.24)
# Adapted committed v2 provider only. It defines exactly one osg/OpenThreads closure.
include(cmake/provider.cmake)
get_filename_component(G1C_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
set(G1C_REPO "${G1B_REPO}")
set(G1C_OSG_SOURCE "${OSG_SOURCE}")
set(G1C_GEOMETRY_TARGET g1b-geometry)
set(_generated "${CMAKE_CURRENT_BINARY_DIR}/osg/include")
set(G1C_GENERATED_INCLUDE "${_generated}")
foreach(_header OpenThreads/Config OpenThreads/Version osg/Config osg/GL osg/Version)
    if(NOT EXISTS "${_generated}/${_header}" OR IS_DIRECTORY "${_generated}/${_header}")
        message(FATAL_ERROR "Missing genuine generated header: ${_header}")
    endif()
endforeach()
set(OPENMW_IOS_ESM_VFS_HOST_TESTS OFF)
add_subdirectory("${G1B_REPO}/experiments/ios-openmw-esm-vfs"
    "${CMAKE_CURRENT_BINARY_DIR}/esm-vfs" EXCLUDE_FROM_ALL)
# This file contains only the preserved verified Bullet recipe, no G0C OSG provider.
include("${G1B_REPO}/experiments/ios-openmw-nif-device-smoke/cmake/bullet.cmake")
file(READ "${G1B_REPO}/experiments/ios-openmw-nif-smoke/data/nif-source-sha256.json" _manifest)
string(JSON _count LENGTH "${_manifest}" sources)
if(NOT _count EQUAL 14)
    message(FATAL_ERROR "Expected 12 genuine NIF units plus the two hash units")
endif()
math(EXPR _last "${_count} - 1")
set(_sources)
foreach(_i RANGE 0 ${_last})
    string(JSON _source GET "${_manifest}" sources ${_i})
    list(APPEND _sources "${G1B_REPO}/${_source}")
endforeach()
add_library(g1b-nif-parser STATIC ${_sources})
target_include_directories(g1b-nif-parser PRIVATE "${G0_BULLET_SOURCE}/src"
    "${G1B_REPO}/extern/smhasher/include" "${G1B_REPO}/extern/smhasher/include/smhasher")
target_link_libraries(g1b-nif-parser PUBLIC openmw-ios-esm-vfs BulletCollision LinearMath osg OpenThreads)
target_compile_definitions(g1b-nif-parser PUBLIC BT_USE_DOUBLE_PRECISION OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
target_compile_features(g1b-nif-parser PUBLIC cxx_std_20)
set(_prepared "${CMAKE_CURRENT_BINARY_DIR}/prepared")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G1C_ROOT}/tools/resources.py" prepare
    --osg-reference "${OPENMW_ESM_OSG_SOURCE}" --osg-renderer "${OSG_SOURCE}"
    --angle "${ANGLE_ROOT}" --bullet "${G0_BULLET_SOURCE}" --generated "${_generated}"
    --output "${_prepared}" COMMAND_ERROR_IS_FATAL ANY)
add_library(g1b-geometry STATIC "${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/src/GeometryAdapter.cpp"
    "${G1B_REPO}/experiments/ios-openmw-nif-device-smoke/src/NifProbe.cpp")
target_include_directories(g1b-geometry PUBLIC "${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/src"
    "${G1B_REPO}/experiments/ios-openmw-nif-device-smoke/src" PRIVATE "${_prepared}/include")
target_link_libraries(g1b-geometry PUBLIC g1b-nif-parser)
target_compile_features(g1b-geometry PUBLIC cxx_std_20)
include("${G1C_ROOT}/cmake/texture.cmake")
add_executable(IOSOpenMWTexturedNif MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
target_link_libraries(IOSOpenMWTexturedNif PRIVATE g1c-texture osgViewer osgGA osgText osgDB osgUtil osg OpenThreads
    "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
target_include_directories(IOSOpenMWTexturedNif PRIVATE "${_prepared}/include"
    "${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/device/src"
    "${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/device/baseline/src")
foreach(_framework UIKit Foundation CoreFoundation QuartzCore Metal GameController)
    find_library(G1B_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSOpenMWTexturedNif PRIVATE "${G1B_${_framework}}")
endforeach()
# Make the actual OSG build configuration canonical for all consumers, including D/E.
foreach(_target osgViewer osgGA osgText osgDB osgUtil osg OpenThreads
        openmw-ios-esm-reader openmw-ios-esm-vfs g1b-nif-parser g1b-geometry g1c-tga g1c-texture
        openmw-textured-nif-check IOSOpenMWTexturedNif)
    target_include_directories(${_target} BEFORE PUBLIC "$<BUILD_INTERFACE:${_generated}>")
    target_include_directories(${_target} SYSTEM BEFORE PUBLIC "${ANGLE_ROOT}/include")
endforeach()
foreach(_target g1b-nif-parser g1b-geometry openmw-textured-nif-check IOSOpenMWTexturedNif)
    target_compile_features(${_target} PRIVATE cxx_std_20)
    set_target_properties(${_target} PROPERTIES CXX_EXTENSIONS OFF)
endforeach()
foreach(_target IOSOpenMWTexturedNif openmw-textured-nif-check)
    target_link_libraries(${_target} PRIVATE "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
    target_link_options(${_target} PRIVATE "-Wl,-no_adhoc_codesign")
    set_target_properties(${_target} PROPERTIES BUILD_WITH_INSTALL_RPATH TRUE
        INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
endforeach()
target_compile_options(IOSOpenMWTexturedNif PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>" -Wall -Wextra)
set_target_properties(IOSOpenMWTexturedNif PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.ios-openmw-textured-nif"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g1c-products-$<CONFIG>.txt"
    CONTENT "$<TARGET_FILE:openmw-textured-nif-check>\n$<TARGET_FILE:IOSOpenMWTexturedNif>\n$<TARGET_BUNDLE_DIR:IOSOpenMWTexturedNif>\n")
file(GLOB_RECURSE _resources CONFIGURE_DEPENDS "${_prepared}/resources/*")
foreach(_resource IN LISTS _resources)
    file(RELATIVE_PATH _name "${_prepared}/resources" "${_resource}")
    if(NOT _name MATCHES "^Frameworks/")
        get_filename_component(_dir "${_name}" DIRECTORY)
        if(_dir STREQUAL "")
            set(_dir ".")
        endif()
        set_source_files_properties("${_resource}" PROPERTIES HEADER_FILE_ONLY TRUE MACOSX_PACKAGE_LOCATION "${_dir}")
        target_sources(IOSOpenMWTexturedNif PRIVATE "${_resource}")
    endif()
endforeach()
add_custom_command(TARGET IOSOpenMWTexturedNif POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${_prepared}/resources/Frameworks"
        "$<TARGET_BUNDLE_DIR:IOSOpenMWTexturedNif>/Frameworks")
