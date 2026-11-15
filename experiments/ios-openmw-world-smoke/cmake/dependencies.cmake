# G4-only verified dependencies. No downloads or installation during CMake.
set(G4_DEPENDENCIES_SOURCE "" CACHE PATH "Verified prepare_dependencies.py output")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/prepare_dependencies.py"
  --output "${G4_DEPENDENCIES_SOURCE}" --offline COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_CONTRIB OFF CACHE BOOL "" FORCE)
set(YAML_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
add_subdirectory("${G4_DEPENDENCIES_SOURCE}/yaml" "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/yaml" EXCLUDE_FROM_ALL)
set(ZLIB_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(ZLIB_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ZLIB_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${G4_DEPENDENCIES_SOURCE}/zlib" "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/zlib" EXCLUDE_FROM_ALL)
# Use libpng's genuine portable C implementation and shipped configuration.
# No ARM assembly/NEON configuration guesses are needed for the first build.
set(_png "${G4_DEPENDENCIES_SOURCE}/png")
set(_png_units png pngerror pngget pngmem pngpread pngread pngrio pngrtran pngrutil
  pngset pngtrans pngwio pngwrite pngwtran pngwutil)
set(_png_sources)
foreach(_unit IN LISTS _png_units)
  list(APPEND _png_sources "${_png}/${_unit}.c")
endforeach()
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/png")
configure_file("${_png}/scripts/pnglibconf.h.prebuilt" "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/png/pnglibconf.h" COPYONLY)
add_library(g4-png STATIC ${_png_sources})
target_include_directories(g4-png PUBLIC "${_png}" "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/png")
target_compile_definitions(g4-png PRIVATE PNG_ARM_NEON_OPT=0 PNG_INTEL_SSE_OPT=0 PNG_POWERPC_VSX_OPT=0 PNG_MIPS_MSA_OPT=0)
target_link_libraries(g4-png PUBLIC ZLIB::ZLIBSTATIC)
include(ExternalProject)
# libjpeg-turbo explicitly rejects add_subdirectory. Its genuine top-level
# configuration generates jconfig/jconfigint and builds the portable C archive.
set(_jpeg_binary "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/jpeg")
file(MAKE_DIRECTORY "${_jpeg_binary}")
set(_jpeg_archive "${_jpeg_binary}/${CMAKE_STATIC_LIBRARY_PREFIX}jpeg${CMAKE_STATIC_LIBRARY_SUFFIX}")
set(_jpeg_platform)
foreach(_variable CMAKE_SYSTEM_NAME CMAKE_SYSTEM_PROCESSOR CMAKE_OSX_SYSROOT CMAKE_OSX_ARCHITECTURES CMAKE_OSX_DEPLOYMENT_TARGET)
  if(DEFINED ${_variable} AND NOT "${${_variable}}" STREQUAL "")
    list(APPEND _jpeg_platform "-D${_variable}=${${_variable}}")
  endif()
endforeach()
ExternalProject_Add(g4-jpeg-build
  SOURCE_DIR "${G4_DEPENDENCIES_SOURCE}/jpeg" BINARY_DIR "${_jpeg_binary}"
  DOWNLOAD_COMMAND "" UPDATE_COMMAND "" INSTALL_COMMAND ""
  CMAKE_ARGS "-DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}" "-DCMAKE_MAKE_PROGRAM=${CMAKE_MAKE_PROGRAM}"
    "-DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}" "-DCMAKE_AR=${CMAKE_AR}" "-DCMAKE_RANLIB=${CMAKE_RANLIB}"
    "-DCMAKE_PROJECT_INCLUDE=${G4_ROOT}/cmake/archive_tools.cmake"
    "-DG4_CPU_AR=${G4_CPU_AR}" "-DG4_CPU_RANLIB=${G4_CPU_RANLIB}"
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    "-DCMAKE_INSTALL_PREFIX=${_jpeg_binary}/unused-install"
    -DENABLE_STATIC=ON -DENABLE_SHARED=OFF -DWITH_SIMD=OFF -DWITH_TURBOJPEG=OFF -DWITH_TOOLS=OFF -DWITH_TESTS=OFF ${_jpeg_platform}
  BUILD_COMMAND "${CMAKE_COMMAND}" --build <BINARY_DIR> --target jpeg-static --parallel 3
  BUILD_BYPRODUCTS "${_jpeg_archive}" EXCLUDE_FROM_ALL TRUE)
add_library(jpeg-static STATIC IMPORTED GLOBAL)
set_target_properties(jpeg-static PROPERTIES IMPORTED_LOCATION "${_jpeg_archive}")
add_dependencies(jpeg-static g4-jpeg-build)
file(GLOB _boost_options CONFIGURE_DEPENDS "${G4_DEPENDENCIES_SOURCE}/boost/libs/program_options/src/*.cpp")
add_library(g4-boost-options STATIC ${_boost_options})
target_include_directories(g4-boost-options PUBLIC "${G4_DEPENDENCIES_SOURCE}/boost")
target_compile_definitions(g4-boost-options PUBLIC BOOST_ALL_NO_LIB BOOST_PROGRAM_OPTIONS_STATIC_LINK)
target_compile_features(g4-boost-options PUBLIC cxx_std_20)
