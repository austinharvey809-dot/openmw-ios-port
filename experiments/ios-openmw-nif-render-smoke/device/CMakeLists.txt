cmake_minimum_required(VERSION 3.24)
# Adapted committed v2 provider only. It defines exactly one osg/OpenThreads closure.
include(cmake/provider.cmake)
set(_generated "${CMAKE_CURRENT_BINARY_DIR}/osg/include")
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
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/provenance.py" prepare
    --osg-reference "${OPENMW_ESM_OSG_SOURCE}" --osg-renderer "${OSG_SOURCE}"
    --angle "${ANGLE_ROOT}" --bullet "${G0_BULLET_SOURCE}" --generated "${_generated}"
    --output "${_prepared}" COMMAND_ERROR_IS_FATAL ANY)
add_library(g1b-geometry STATIC "${CMAKE_CURRENT_SOURCE_DIR}/../src/GeometryAdapter.cpp"
    "${G1B_REPO}/experiments/ios-openmw-nif-device-smoke/src/NifProbe.cpp")
target_include_directories(g1b-geometry PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../src"
    "${G1B_REPO}/experiments/ios-openmw-nif-device-smoke/src" PRIVATE "${_prepared}/include")
target_link_libraries(g1b-geometry PUBLIC g1b-nif-parser)
target_compile_features(g1b-geometry PUBLIC cxx_std_20)
add_executable(openmw-g1b-device-link-check "${CMAKE_CURRENT_SOURCE_DIR}/../tests/geometry_check.cpp")
target_link_libraries(openmw-g1b-device-link-check PRIVATE g1b-geometry)
add_executable(IOSOpenMWNifTriangle MACOSX_BUNDLE src/main.mm src/OSGScene.hpp src/AngleRenderer.hpp)
target_link_libraries(IOSOpenMWNifTriangle PRIVATE g1b-geometry osgViewer osgGA osgText osgDB osgUtil osg OpenThreads
    "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
target_include_directories(IOSOpenMWNifTriangle PRIVATE "${_prepared}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/baseline/src")
foreach(_framework UIKit Foundation CoreFoundation QuartzCore Metal GameController)
    find_library(G1B_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSOpenMWNifTriangle PRIVATE "${G1B_${_framework}}")
endforeach()
# Make the actual OSG build configuration canonical for all consumers, including D/E.
foreach(_target osgViewer osgGA osgText osgDB osgUtil osg OpenThreads
        openmw-ios-esm-reader openmw-ios-esm-vfs g1b-nif-parser g1b-geometry
        openmw-g1b-device-link-check IOSOpenMWNifTriangle)
    target_include_directories(${_target} BEFORE PUBLIC "$<BUILD_INTERFACE:${_generated}>")
    target_include_directories(${_target} SYSTEM BEFORE PUBLIC "${ANGLE_ROOT}/include")
endforeach()
foreach(_target g1b-nif-parser g1b-geometry openmw-g1b-device-link-check IOSOpenMWNifTriangle)
    target_compile_features(${_target} PRIVATE cxx_std_20)
    set_target_properties(${_target} PROPERTIES CXX_EXTENSIONS OFF)
endforeach()
foreach(_target IOSOpenMWNifTriangle openmw-g1b-device-link-check)
    target_link_libraries(${_target} PRIVATE "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
    target_link_options(${_target} PRIVATE "-Wl,-no_adhoc_codesign")
    set_target_properties(${_target} PROPERTIES BUILD_WITH_INSTALL_RPATH TRUE
        INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
endforeach()
target_compile_options(IOSOpenMWNifTriangle PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>" -Wall -Wextra)
set_target_properties(IOSOpenMWNifTriangle PROPERTIES OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.ios-openmw-nif-triangle"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g1b-products-$<CONFIG>.txt"
    CONTENT "$<TARGET_FILE:openmw-g1b-device-link-check>\n$<TARGET_FILE:IOSOpenMWNifTriangle>\n$<TARGET_BUNDLE_DIR:IOSOpenMWNifTriangle>\n")
file(GLOB_RECURSE _resources CONFIGURE_DEPENDS "${_prepared}/resources/*")
foreach(_resource IN LISTS _resources)
    file(RELATIVE_PATH _name "${_prepared}/resources" "${_resource}")
    if(NOT _name MATCHES "^Frameworks/")
        get_filename_component(_dir "${_name}" DIRECTORY)
        if(_dir STREQUAL "")
            set(_dir ".")
        endif()
        set_source_files_properties("${_resource}" PROPERTIES HEADER_FILE_ONLY TRUE MACOSX_PACKAGE_LOCATION "${_dir}")
        target_sources(IOSOpenMWNifTriangle PRIVATE "${_resource}")
    endif()
endforeach()
add_custom_command(TARGET IOSOpenMWNifTriangle POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${_prepared}/resources/Frameworks"
        "$<TARGET_BUNDLE_DIR:IOSOpenMWNifTriangle>/Frameworks")
