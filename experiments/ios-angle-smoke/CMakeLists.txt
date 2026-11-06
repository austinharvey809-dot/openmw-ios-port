cmake_minimum_required(VERSION 3.24)
set(CMAKE_OSX_DEPLOYMENT_TARGET "18.0" CACHE STRING "Minimum iOS version")
project(IOSANGLESmoke VERSION 0.1.0 LANGUAGES CXX OBJCXX)
string(TOLOWER "${CMAKE_OSX_SYSROOT}" _sdk)
if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS" OR NOT _sdk MATCHES "iphoneos"
   OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
    message(FATAL_ERROR "Requires full Xcode, iphoneos SDK and ARM64 device target")
endif()
if(NOT CMAKE_OSX_DEPLOYMENT_TARGET STREQUAL "18.0")
    message(FATAL_ERROR "Gate 0 and Gate 1 deployment target must agree: 18.0")
endif()
set(ANGLE_ROOT "" CACHE PATH "Validated Gate 0 package; configuration downloads nothing")
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/validate_dependency.py"
    --root "${ANGLE_ROOT}" --resolve "${CMAKE_CURRENT_BINARY_DIR}/angle-resolved.cmake"
    RESULT_VARIABLE _result)
if(NOT _result EQUAL 0)
    message(FATAL_ERROR "Gate 0 dependency resolution failed")
endif()
include("${CMAKE_CURRENT_BINARY_DIR}/angle-resolved.cmake")
add_executable(IOSANGLESmoke MACOSX_BUNDLE src/main.mm)
target_compile_features(IOSANGLESmoke PRIVATE cxx_std_17)
target_compile_options(IOSANGLESmoke PRIVATE -fobjc-arc -Wall -Wextra)
target_include_directories(IOSANGLESmoke SYSTEM PRIVATE "${ANGLE_ROOT}/include")
target_link_libraries(IOSANGLESmoke PRIVATE "${ANGLE_EGL_LIBRARY}" "${ANGLE_GLES_LIBRARY}")
foreach(_framework UIKit Foundation QuartzCore Metal GameController)
    find_library(SMOKE_${_framework} NAMES ${_framework} REQUIRED)
    target_link_libraries(IOSANGLESmoke PRIVATE "${SMOKE_${_framework}}")
endforeach()
set(_angle_bundle_id "org.openmw.experiments.ios-angle-smoke")
# CI packages the build-tree app, without cmake --install. Use its final runtime
# path now; CMake's default build rpath otherwise includes ANGLE_ROOT/Frameworks.
# Absolute framework link/search paths remain necessary at build time only.
set_target_properties(IOSANGLESmoke PROPERTIES
    OBJCXX_STANDARD 17 OBJCXX_STANDARD_REQUIRED YES
    BUILD_WITH_INSTALL_RPATH TRUE
    INSTALL_RPATH "@executable_path/Frameworks"
    INSTALL_RPATH_USE_LINK_PATH FALSE
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "${_angle_bundle_id}"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${_angle_bundle_id}"
    MACOSX_BUNDLE_BUNDLE_NAME "iOS ANGLE Smoke"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    MACOSX_BUNDLE_BUNDLE_VERSION "1"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1"
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"
    XCODE_ATTRIBUTE_DEBUG_INFORMATION_FORMAT "dwarf-with-dsym")
# Copy untouched upstream framework resources too (including any Metal assets).
# No automatic signing, binary rewriting, or downloads at app configure time.
add_custom_command(TARGET IOSANGLESmoke POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${ANGLE_ROOT}/Frameworks" "$<TARGET_BUNDLE_DIR:IOSANGLESmoke>/Frameworks"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${ANGLE_ROOT}/Licenses" "$<TARGET_BUNDLE_DIR:IOSANGLESmoke>/Licenses"
    COMMAND "${CMAKE_COMMAND}" -E copy "${ANGLE_ROOT}/angle-lock.json" "$<TARGET_BUNDLE_DIR:IOSANGLESmoke>/angle-lock.json"
    COMMAND "${CMAKE_COMMAND}" -E copy "${ANGLE_ROOT}/angle-build.json" "$<TARGET_BUNDLE_DIR:IOSANGLESmoke>/angle-build.json")
