cmake_minimum_required(VERSION 3.24)
set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
project(IOSOSGSmoke VERSION 0.1.0 LANGUAGES C CXX OBJCXX)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"
   OR NOT CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0")
    message(FATAL_ERROR "Only unsigned iPhoneOS ARM64 with deployment target 18.0 is supported")
endif()
execute_process(COMMAND xcrun --sdk iphoneos --show-sdk-path OUTPUT_VARIABLE _device_sdk
    OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
string(TOLOWER "${CMAKE_OSX_SYSROOT}" _sdk)
if(NOT _sdk MATCHES "iphoneos")
    message(FATAL_ERROR "Select iphoneos; simulator/macOS builds are not device evidence")
endif()
# OSG's old iPhone setup needs an actual SDK path rather than a sysroot alias.
set(CMAKE_OSX_SYSROOT "${_device_sdk}" CACHE PATH "Selected iPhoneOS SDK" FORCE)
set(ANGLE_ROOT "" CACHE PATH "Verified existing ANGLE Gate 0 package")
set(OSG_SOURCE "" CACHE PATH "Pinned, overlaid source from tools/prepare_osg.py")
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/../ios-angle-smoke/tools/validate_dependency.py"
    --root "${ANGLE_ROOT}" --resolve "${CMAKE_CURRENT_BINARY_DIR}/angle-resolved.cmake" COMMAND_ERROR_IS_FATAL ANY)
include("${CMAKE_CURRENT_BINARY_DIR}/angle-resolved.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_osg_source.py"
    --source "${OSG_SOURCE}" COMMAND_ERROR_IS_FATAL ANY)

set(OSG_BUILD_PLATFORM_IPHONE ON CACHE BOOL "" FORCE)
set(IPHONE_VERSION_MIN "18.0" CACHE STRING "" FORCE)
set(CMAKE_XCODE_EFFECTIVE_PLATFORMS "-iphoneos" CACHE STRING "" FORCE)
set(OPENGL_PROFILE "GLES3" CACHE STRING "" FORCE)
set(OSG_GL_LIBRARY_STATIC OFF CACHE BOOL "ANGLE remains dynamic" FORCE)
set(OSG_ANGLE_GLES_LIBRARY "${ANGLE_GLES_LIBRARY}")
set(EGL_LIBRARY "${ANGLE_EGL_LIBRARY}" CACHE FILEPATH "" FORCE)
set(OPENGL_INCLUDE_DIR "${ANGLE_ROOT}/include" CACHE PATH "" FORCE)
set(CMAKE_REQUIRED_INCLUDES "${ANGLE_ROOT}/include")
set(OPENGL_HEADER1 "#include <GLES3/gl3.h>" CACHE STRING "" FORCE)
set(OPENGL_HEADER2 "#include <GLES3/gl3ext.h>" CACHE STRING "" FORCE)
set(OSG_WINDOWING_SYSTEM "None" CACHE STRING "" FORCE)
set(DYNAMIC_OPENSCENEGRAPH OFF CACHE BOOL "" FORCE)
set(DYNAMIC_OPENTHREADS OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_APPLICATIONS OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_PLUGINS OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_DEPRECATED_SERIALIZERS OFF CACHE BOOL "" FORCE)
set(OSG_COMPILE_FRAMEWORKS OFF CACHE BOOL "" FORCE)
set(OSG_TEXT_USE_FONTCONFIG OFF CACHE BOOL "" FORCE)
set(OSG_FIND_3RD_PARTY_DEPS OFF CACHE BOOL "" FORCE)
set(OSG_CXX_LANGUAGE_STANDARD "c++11" CACHE STRING "" FORCE)
# Match OpenMW's pinned fork ABI choices, without importing the engine.
foreach(_kind MATRIX PLANE QUAT)
    set(OSG_USE_FLOAT_${_kind} OFF CACHE BOOL "" FORCE)
endforeach()
foreach(_package ZLIB CURL Freetype Fontconfig JPEG PNG TIFF QuickTime QTKit SDL SDL2)
    set(CMAKE_DISABLE_FIND_PACKAGE_${_package} ON CACHE BOOL "No external plugin/image/font dependencies" FORCE)
endforeach()
add_compile_definitions(OSG_IOS_ANGLE=1)
# EXCLUDE_FROM_ALL + explicit app dependencies builds only the seven-library
# viewer closure. No broad install target (which would build other components).
add_subdirectory("${OSG_SOURCE}" "${CMAKE_CURRENT_BINARY_DIR}/osg" EXCLUDE_FROM_ALL)
if(NOT OSG_GLES3_AVAILABLE OR OSG_GL1_AVAILABLE OR OSG_GL2_AVAILABLE OR OSG_GL3_AVAILABLE
   OR NOT OSG_WINDOWING_SYSTEM STREQUAL "None")
    message(FATAL_ERROR "OSG profile/window configuration did not remain GLES3/None")
endif()
add_executable(IOSOSGSmoke MACOSX_BUNDLE src/main.mm src/OSGScene.hpp)
target_compile_features(IOSOSGSmoke PRIVATE cxx_std_17)
target_compile_definitions(IOSOSGSmoke PRIVATE OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
target_compile_options(IOSOSGSmoke PRIVATE -fobjc-arc -Wall -Wextra)
target_include_directories(IOSOSGSmoke PRIVATE "${OSG_SOURCE}/include" "${CMAKE_CURRENT_BINARY_DIR}/osg/include")
target_include_directories(IOSOSGSmoke SYSTEM PRIVATE "${ANGLE_ROOT}/include")
target_link_libraries(IOSOSGSmoke PRIVATE osgViewer osgGA osgText osgDB osgUtil osg OpenThreads
    "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
foreach(_framework UIKit Foundation CoreFoundation QuartzCore Metal GameController)
    find_library(SMOKE_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSOSGSmoke PRIVATE "${SMOKE_${_framework}}")
endforeach()
set_target_properties(IOSOSGSmoke PROPERTIES
    OBJCXX_STANDARD 17 OBJCXX_STANDARD_REQUIRED YES
    BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.ios-osg-smoke"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "org.openmw.experiments.ios-osg-smoke"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/osg-build.json"
    "{\"revision\":\"9b384d5439977784e5cd250ff8ff7966928ddd27\",\"profile\":\"GLES3\",\"overlay_version\":1,\"windowing\":\"None\",\"static\":true,\"deployment\":\"18.0\"}\n")
add_custom_command(TARGET IOSOSGSmoke POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${ANGLE_ROOT}/Frameworks" "$<TARGET_BUNDLE_DIR:IOSOSGSmoke>/Frameworks"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${ANGLE_ROOT}/Licenses" "$<TARGET_BUNDLE_DIR:IOSOSGSmoke>/Licenses"
    COMMAND "${CMAKE_COMMAND}" -E copy "${OSG_SOURCE}/LICENSE.txt" "$<TARGET_BUNDLE_DIR:IOSOSGSmoke>/Licenses/osg-LICENSE.txt"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${OSG_SOURCE}/include/OpenThreads" "$<TARGET_BUNDLE_DIR:IOSOSGSmoke>/Licenses/OpenThreads"
    COMMAND "${CMAKE_COMMAND}" -E copy "${ANGLE_ROOT}/angle-lock.json" "${ANGLE_ROOT}/angle-build.json"
        "${CMAKE_CURRENT_SOURCE_DIR}/data/osg-lock.json" "${CMAKE_CURRENT_BINARY_DIR}/osg-build.json"
        "$<TARGET_BUNDLE_DIR:IOSOSGSmoke>/")
