get_filename_component(G6_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(G6_GENERATED "${CMAKE_CURRENT_BINARY_DIR}/g6-generated")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${G6_ROOT}/engine-lock.json" "${G6_ROOT}/dependencies.json"
  "${G6_ROOT}/tools/prepare.py" "${G6_ROOT}/tools/dependencies.py"
  "${G6_ROOT}/tools/prepare_mygui.py" "${G6_ROOT}/tools/prepare_renderer.py")
set(G6_DEPENDENCIES_SOURCE "" CACHE PATH "Verified G6 dependency source directory")
if(NOT TARGET g5-lua OR NOT TARGET g4-upstream)
  message(FATAL_ERROR "G6 requires the unchanged G5 Lua and G4 OSG/Bullet provider")
endif()
if(NOT TARGET g6-mygui)
  include("${CMAKE_CURRENT_LIST_DIR}/dependencies.cmake")
endif()
# These values are needed by both normal and deferred core configuration.
set(_g6_sdl "${G6_DEPENDENCIES_SOURCE}/SDL2-2.32.10")
file(READ "${G6_ROOT}/engine-lock.json" _g6_lock)
string(JSON _g6_sources_count LENGTH "${_g6_lock}" sources)
math(EXPR _g6_sources_last "${_g6_sources_count}-1")
foreach(_g6_i RANGE 0 ${_g6_sources_last})
  string(JSON _g6_original MEMBER "${_g6_lock}" sources ${_g6_i})
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${G4_REPO}/${_g6_original}")
endforeach()
string(JSON _g6_count LENGTH "${_g6_lock}" units)
math(EXPR _g6_last "${_g6_count}-1")
set(_g6_units)
foreach(_g6_i RANGE 0 ${_g6_last})
  string(JSON _g6_name GET "${_g6_lock}" units ${_g6_i})
  list(APPEND _g6_units "${G4_REPO}/${_g6_name}")
endforeach()
add_library(g6-live-world STATIC ${_g6_units}
  "${G6_GENERATED}/EngineIndex.cpp" "${G6_GENERATED}/cellstore.cpp"
  "${G6_GENERATED}/player_data.cpp" "${G6_GENERATED}/spellstore.cpp"
  "${G6_GENERATED}/effect_list.cpp" "${G6_GENERATED}/tooltip_format.cpp"
  "${G6_GENERATED}/inventory_pickup.cpp" "${G6_GENERATED}/preview_helpers.cpp"
  "${G6_GENERATED}/esmstore.cpp" "${G6_ROOT}/src/LiveWorld.cpp"
  "${G4_REPO}/components/esm/luascripts.cpp" "${G4_REPO}/components/lua/serialization.cpp"
  "${G4_REPO}/components/lua/configuration.cpp" "${G4_REPO}/components/misc/color.cpp")
target_include_directories(g6-live-world BEFORE PUBLIC "${G6_GENERATED}" "${G6_ROOT}/src" "${G6_GENERATED}/mygui")
target_include_directories(g6-live-world PRIVATE "${_g6_sdl}/include" "${G4_REPO}/extern/sol3"
  "${G4_REPO}/extern/Base64" "${G4_REPO}/apps/openmw/mwworld" "${G4_DEPENDENCIES_SOURCE}/zlib")
target_link_libraries(g6-live-world PUBLIC g4-upstream g5-lua g6-mygui g6-icu-i18n g6-detour)
target_compile_definitions(g6-live-world PRIVATE NO_LUAJIT)
target_compile_features(g6-live-world PUBLIC cxx_std_20)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
  target_compile_definitions(g6-live-world PRIVATE G6_DEFAULT_SETTINGS="${G4_REPO}/files/settings-default.cfg")
endif()
foreach(_g6_target g6-live-world g6-mygui g6-icu-common g6-icu-i18n g6-detour)
  set_target_properties(${_g6_target} PROPERTIES CXX_EXTENSIONS OFF)
endforeach()
# Imported Windows providers can contain native backslashes. Normalize the
# actual configured path before embedding it in portable JSON evidence.
file(TO_CMAKE_PATH "${G4_OSG_GENERATED_INCLUDE}" _g6_osg_include_json)
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g6-config-$<CONFIG>.json" CONTENT
  "{\"generated\":\"${G6_GENERATED}\",\"osg_include\":\"${_g6_osg_include_json}\",\"g6_dependencies\":\"${G6_DEPENDENCIES_SOURCE}\",\"g4_dependencies\":\"${G4_DEPENDENCIES_SOURCE}\",\"sdl\":\"${_g6_sdl}\",\"archives\":{\"core\":\"$<TARGET_FILE:g6-live-world>\",\"mygui\":\"$<TARGET_FILE:g6-mygui>\",\"freetype\":\"$<TARGET_FILE:freetype>\",\"icu_common\":\"$<TARGET_FILE:g6-icu-common>\",\"icu_i18n\":\"$<TARGET_FILE:g6-icu-i18n>\",\"icu_data\":\"$<TARGET_FILE:g6-icu-data>\",\"detour\":\"$<TARGET_FILE:g6-detour>\",\"lua\":\"$<TARGET_FILE:g5-lua>\"}}\n")
