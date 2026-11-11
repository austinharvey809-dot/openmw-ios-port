cmake_minimum_required(VERSION 3.24)
project(OpenMWIOSNifSmoke LANGUAGES CXX)

if(NOT UNIX OR CMAKE_CROSSCOMPILING)
    message(FATAL_ERROR "G0A host check requires a native POSIX C++20 build; iPhoneOS linking is a later gate")
endif()

# Reuse D/E exactly once; A/B/C archives overlap their source closure.
set(OPENMW_IOS_ESM_VFS_HOST_TESTS ON CACHE BOOL "Build existing host E checks" FORCE)
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../ios-openmw-esm-vfs"
    "${CMAKE_CURRENT_BINARY_DIR}/esm-vfs" EXCLUDE_FROM_ALL)
get_filename_component(OPENMW_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

# The reader's math types include non-inline osg::Quat::makeRotate calls.
# Build pinned OSG core/OpenThreads, with D's audited math ABI, without viewer
# libraries, plugins, ANGLE or any iPhoneOS graphics configuration.
set(DYNAMIC_OPENSCENEGRAPH OFF CACHE BOOL "Static OSG core" FORCE)
set(DYNAMIC_OPENTHREADS OFF CACHE BOOL "Static OpenThreads" FORCE)
set(BUILD_OSG_APPLICATIONS OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_PLUGINS OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_PLUGINS_BY_DEFAULT OFF CACHE BOOL "" FORCE)
set(BUILD_OSG_DEPRECATED_SERIALIZERS OFF CACHE BOOL "" FORCE)
set(OSG_FIND_3RD_PARTY_DEPS OFF CACHE BOOL "" FORCE)
set(OSG_USE_FLOAT_MATRIX OFF CACHE BOOL "D math ABI" FORCE)
set(OSG_USE_FLOAT_PLANE OFF CACHE BOOL "D math ABI" FORCE)
set(OSG_USE_FLOAT_BOUNDINGSPHERE ON CACHE BOOL "D math ABI" FORCE)
set(OSG_USE_FLOAT_BOUNDINGBOX ON CACHE BOOL "D math ABI" FORCE)
set(OSG_USE_FLOAT_QUAT OFF CACHE BOOL "D math ABI" FORCE)
set(_osg_binary_dir "${CMAKE_CURRENT_BINARY_DIR}/osg")
add_subdirectory("${OPENMW_ESM_OSG_SOURCE}" "${_osg_binary_dir}" EXCLUDE_FROM_ALL)
if(NOT TARGET osg OR NOT TARGET OpenThreads)
    message(FATAL_ERROR "Pinned OSG core/OpenThreads targets are required for NIF math linkage")
endif()

# Upstream configure_file calls create these before add_subdirectory returns.
# OSG's directory-scoped includes do not propagate to this parent target.
set(_osg_generated_include "${_osg_binary_dir}/include")
foreach(_header IN ITEMS OpenThreads/Config OpenThreads/Version osg/Config osg/GL osg/Version)
    if(NOT EXISTS "${_osg_generated_include}/${_header}"
       OR IS_DIRECTORY "${_osg_generated_include}/${_header}")
        message(FATAL_ERROR "Pinned OSG generated header missing: ${_osg_generated_include}/${_header}")
    endif()
endforeach()

# Build the source that tools/prepare_bullet.py verified against OpenMW's own
# Bullet 3.25 SHA-512 pin. CMake never downloads or substitutes a package.
set(G0_BULLET_SOURCE "" CACHE PATH "Verified, extracted Bullet 3.25 source")
if(NOT G0_BULLET_SOURCE OR NOT EXISTS "${G0_BULLET_SOURCE}/CMakeLists.txt"
   OR NOT EXISTS "${G0_BULLET_SOURCE}/src/BulletCollision/CollisionShapes/btTriangleMesh.h")
    message(FATAL_ERROR "Provide the verified Bullet 3.25 source from prepare_bullet.py")
endif()
get_filename_component(_bullet_parent "${G0_BULLET_SOURCE}/.." ABSOLUTE)
set(_bullet_provenance "${_bullet_parent}/bullet-provenance.json")
if(NOT EXISTS "${_bullet_provenance}")
    message(FATAL_ERROR "Verified Bullet archive provenance is missing")
endif()
file(READ "${_bullet_provenance}" _bullet_json)
string(JSON _bullet_hash GET "${_bullet_json}" archive_sha512)
string(JSON _bullet_url GET "${_bullet_json}" source_url)
string(JSON _bullet_source GET "${_bullet_json}" source_directory)
get_filename_component(_bullet_real "${G0_BULLET_SOURCE}" REALPATH)
if(NOT _bullet_hash STREQUAL "7086e5fcf69635801bb311261173cb8d173b712ca1bd78be03df48fad884674e85512861190e45a1a62d5627aaad65cde08c175c44a3be9afa410d3dfd5358d4"
   OR NOT _bullet_url STREQUAL "https://github.com/bulletphysics/bullet3/archive/refs/tags/3.25.tar.gz"
   OR NOT _bullet_source STREQUAL _bullet_real)
    message(FATAL_ERROR "Bullet source/provenance does not match the approved pin")
endif()
set(USE_DOUBLE_PRECISION ON CACHE BOOL "Bullet ABI" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Static Bullet" FORCE)
set(BUILD_BULLET3 OFF CACHE BOOL "" FORCE)
set(BUILD_EXTRAS OFF CACHE BOOL "" FORCE)
set(BUILD_UNIT_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_PYBULLET OFF CACHE BOOL "" FORCE)
set(BUILD_BULLET2_DEMOS OFF CACHE BOOL "" FORCE)
set(BUILD_OPENGL3_DEMOS OFF CACHE BOOL "" FORCE)
set(BUILD_CPU_DEMOS OFF CACHE BOOL "" FORCE)
set(BUILD_EGL OFF CACHE BOOL "" FORCE)
set(BUILD_CLSOCKET OFF CACHE BOOL "" FORCE)
set(BUILD_ENET OFF CACHE BOOL "" FORCE)
set(BULLET2_MULTITHREADING OFF CACHE BOOL "" FORCE)
set(FETCHCONTENT_FULLY_DISCONNECTED ON CACHE BOOL "No dependency downloads during CMake" FORCE)
add_subdirectory("${G0_BULLET_SOURCE}" "${CMAKE_CURRENT_BINARY_DIR}/bullet" EXCLUDE_FROM_ALL)
if(NOT TARGET BulletCollision OR NOT TARGET LinearMath OR NOT USE_DOUBLE_PRECISION)
    message(FATAL_ERROR "Verified double-precision BulletCollision/LinearMath targets are required")
endif()
target_compile_definitions(BulletCollision PUBLIC BT_USE_DOUBLE_PRECISION)
target_compile_definitions(LinearMath PUBLIC BT_USE_DOUBLE_PRECISION)
set(_bullet_libraries BulletCollision LinearMath)

set(_nif_units base controller data effect extra niffile nifstream node particle physics property texture)
set(_sources)
foreach(_unit IN LISTS _nif_units)
    list(APPEND _sources "${OPENMW_ROOT}/components/nif/${_unit}.cpp")
endforeach()
list(APPEND _sources "${OPENMW_ROOT}/components/files/hash.cpp"
    "${OPENMW_ROOT}/extern/smhasher/MurmurHash3.cpp")
add_library(openmw-ios-nif-parser STATIC ${_sources})
target_include_directories(openmw-ios-nif-parser PRIVATE
    "${G0_BULLET_SOURCE}/src" "${OPENMW_ROOT}/extern/smhasher/include"
    "${OPENMW_ROOT}/extern/smhasher/include/smhasher")

# Prefer the actual OSG build configuration over D/E's math-only osg/Config.
# PUBLIC also supplies these headers to the genuine parser test executable.
target_include_directories(openmw-ios-nif-parser BEFORE PUBLIC
    "$<BUILD_INTERFACE:${_osg_generated_include}>")
target_compile_definitions(openmw-ios-nif-parser PUBLIC BT_USE_DOUBLE_PRECISION)
target_compile_features(openmw-ios-nif-parser PUBLIC cxx_std_20)
target_link_libraries(openmw-ios-nif-parser PUBLIC openmw-ios-esm-vfs ${_bullet_libraries}
    osg OpenThreads)
set_target_properties(openmw-ios-nif-parser PROPERTIES CXX_EXTENSIONS OFF)

add_executable(openmw-nif-parse-check tests/nif_parse_check.cpp)
target_link_libraries(openmw-nif-parse-check PRIVATE openmw-ios-nif-parser)
target_compile_features(openmw-nif-parse-check PRIVATE cxx_std_20)
set_target_properties(openmw-nif-parse-check PROPERTIES CXX_EXTENSIONS OFF)

find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
enable_testing()
add_test(NAME openmw-g0a-parser-candidates
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/run_host_cases.py"
    --reader "$<TARGET_FILE:openmw-nif-parse-check>")
