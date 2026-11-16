get_filename_component(G5_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(G5_GENERATED "${CMAKE_CURRENT_BINARY_DIR}/g5-generated")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${G5_ROOT}/engine-lock.json" "${G5_ROOT}/dependencies.json"
  "${G5_ROOT}/tools/prepare_engine.py" "${G5_ROOT}/tools/prepare_frontend.py"
  "${G5_ROOT}/tools/provenance.py" "${G5_ROOT}/tools/verify_lua.py")
if(NOT TARGET g4-upstream)
  message(FATAL_ERROR "G5 must attach to the accepted single G4 provider")
endif()
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/prepare_engine.py"
  --output "${G5_GENERATED}" COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/prepare_frontend.py"
  --output "${G5_GENERATED}" --defaults "${G4_GENERATED}/G4Defaults.hpp" COMMAND_ERROR_IS_FATAL ANY)
if(NOT G5_LUA_SOURCE)
  message(FATAL_ERROR "Supply a hash-verified G5_LUA_SOURCE prepared by tools/acquire.py")
endif()
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/verify_lua.py"
  "${G5_LUA_SOURCE}" COMMAND_ERROR_IS_FATAL ANY)
# Explicit inventory; do not accidentally compile the standalone lua/luac tools.
set(_lua lapi lauxlib lbaselib lcode lcorolib lctype ldblib ldebug ldo ldump lfunc
  lgc linit liolib llex lmathlib lmem loadlib lobject lopcodes loslib lparser
  lstate lstring lstrlib ltable ltablib ltm lundump lutf8lib lvm lzio)
set(_lua_sources)
foreach(_unit IN LISTS _lua)
  list(APPEND _lua_sources "${G5_LUA_SOURCE}/src/${_unit}.c")
endforeach()
add_library(g5-lua STATIC ${_lua_sources})
target_include_directories(g5-lua PUBLIC "${G5_LUA_SOURCE}/src")
set_target_properties(g5-lua PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED YES C_EXTENSIONS OFF)
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  # Stock Lua's ios Makefile uses this flag. Among other platform behavior it
  # selects the upstream loslib implementation for iOS's unavailable system().
  target_compile_definitions(g5-lua PUBLIC LUA_USE_IOS)
endif()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g5-lua-$<CONFIG>.txt" CONTENT "$<TARGET_FILE:g5-lua>\n")
add_library(g5-engine-store STATIC "${G5_GENERATED}/esmstore.cpp" "${G5_GENERATED}/readonly.cpp"
  "${G5_ROOT}/src/EngineIndex.cpp" "${G5_GENERATED}/References.cpp"
  "${G4_REPO}/components/esm/luascripts.cpp" "${G4_REPO}/components/lua/serialization.cpp"
  "${G4_REPO}/components/lua/configuration.cpp" "${G4_REPO}/components/misc/color.cpp")
target_include_directories(g5-engine-store PUBLIC "${G5_ROOT}/src" PRIVATE "${G4_REPO}/extern/sol3" "${G4_REPO}/apps/openmw/mwworld")
target_link_libraries(g5-engine-store PUBLIC g4-upstream g5-lua)
target_compile_definitions(g5-engine-store PRIVATE NO_LUAJIT)
target_compile_features(g5-engine-store PUBLIC cxx_std_20)
set_target_properties(g5-engine-store PROPERTIES CXX_EXTENSIONS OFF)
add_library(g5-world STATIC "${G5_GENERATED}/Resources.cpp" "${G5_GENERATED}/TerrainStorage.cpp"
  "${G5_GENERATED}/World.cpp" "${G5_GENERATED}/Environment.cpp" "${G5_GENERATED}/Session.cpp")
target_include_directories(g5-world BEFORE PUBLIC "${G5_GENERATED}")
target_link_libraries(g5-world PUBLIC g5-engine-store)
set_target_properties(g5-world PROPERTIES CXX_EXTENSIONS OFF)
