get_filename_component(G4_REPO "${G4_ROOT}/../.." ABSOLUTE)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
set(G4_GENERATED "${CMAKE_CURRENT_BINARY_DIR}/g4-generated")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/paths.py" COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/prepare_shaders.py"
  --output "${G4_GENERATED}/Shaders" COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/prepare_defaults.py"
  --output "${G4_GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
include("${G4_ROOT}/cmake/dependencies.cmake")
include("${G4_ROOT}/cmake/image_plugins.cmake")
file(READ "${G4_ROOT}/engine-sources.json" _g4_sources)
string(JSON _count LENGTH "${_g4_sources}" sources)
math(EXPR _last "${_count} - 1")
set(_units)
foreach(_index RANGE 0 ${_last})
  string(JSON _source GET "${_g4_sources}" sources ${_index})
  list(APPEND _units "${G4_REPO}/${_source}")
endforeach()
if(WIN32)
  list(APPEND _units "${G4_REPO}/components/platform/filewin32.cpp")
else()
  list(APPEND _units "${G4_REPO}/components/platform/fileposix.cpp")
endif()
add_library(g4-upstream STATIC ${_units}
  "${G4_ROOT}/src/WorldIndex.cpp" "${G4_ROOT}/src/Resources.cpp" "${G4_ROOT}/src/TerrainStorage.cpp"
  "${G4_ROOT}/src/World.cpp" "${G4_ROOT}/src/Environment.cpp" "${G4_ROOT}/src/Session.cpp"
  "${G4_REPO}/experiments/ios-openmw-exterior-smoke/src/Physics.cpp")
target_include_directories(g4-upstream BEFORE PUBLIC "${G4_OSG_GENERATED_INCLUDE}")
target_include_directories(g4-upstream PUBLIC "${G4_ROOT}/src" "${G4_REPO}" "${G4_OSG_SOURCE}/include"
  "${G0_BULLET_SOURCE}/src" "${G4_DEPENDENCIES_SOURCE}/mygui/MyGUIEngine/include"
  PRIVATE "${G4_GENERATED}" "${G4_REPO}/extern/smhasher/include" "${G4_REPO}/extern/smhasher/include/smhasher")
target_compile_definitions(g4-upstream PUBLIC BT_USE_DOUBLE_PRECISION)
target_link_libraries(g4-upstream PUBLIC osgViewer osgGA osgDB osgUtil osg osgAnimation osgParticle osgShadow OpenThreads
  BulletDynamics BulletCollision LinearMath yaml-cpp::yaml-cpp g4-boost-options
  g4-plugin-dds g4-plugin-tga g4-plugin-bmp g4-plugin-png g4-plugin-jpeg g4-plugin-osg g4-serializers-osg)
if(NOT G4_SHARED_DESKTOP_PROVIDER)
  target_compile_definitions(g4-upstream PUBLIC OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
endif()
if(WIN32)
  target_link_libraries(g4-upstream PUBLIC opengl32)
endif()
target_compile_features(g4-upstream PUBLIC cxx_std_20)
set_target_properties(g4-upstream PROPERTIES CXX_EXTENSIONS OFF)
foreach(_bullet BulletDynamics BulletCollision LinearMath)
  if(NOT TARGET ${_bullet})
    message(FATAL_ERROR "G4 missing verified ${_bullet} provider")
  endif()
endforeach()
file(WRITE "${G4_GENERATED}/osg-include.txt" "${G4_OSG_GENERATED_INCLUDE}\n")
