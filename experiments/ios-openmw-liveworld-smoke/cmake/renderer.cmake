execute_process(COMMAND "${Python3_EXECUTABLE}" "${G6_ROOT}/tools/prepare_renderer.py"
  --g5 "${G5_GENERATED}" --output "${G6_GENERATED}" COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
add_library(g6-world STATIC "${G6_GENERATED}/Resources.cpp" "${G6_GENERATED}/TerrainStorage.cpp"
  "${G6_GENERATED}/World.cpp" "${G6_GENERATED}/Environment.cpp" "${G6_GENERATED}/Session.cpp")
target_include_directories(g6-world BEFORE PUBLIC "${G6_GENERATED}")
target_link_libraries(g6-world PUBLIC g6-live-world)
set_target_properties(g6-world PROPERTIES CXX_EXTENSIONS OFF)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
add_executable(openmw-g6-world-check "${G6_GENERATED}/world_check.cpp")
target_link_libraries(openmw-g6-world-check PRIVATE g6-world)
set_target_properties(openmw-g6-world-check PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME g6-genuine-world COMMAND "${Python3_EXECUTABLE}" "${G6_ROOT}/tools/run_cases.py"
  --world-binary "$<TARGET_FILE:openmw-g6-world-check>" --shaders "${G4_GENERATED}/Shaders"
  --output "${CMAKE_CURRENT_BINARY_DIR}/g6-world-cases.json")
add_executable(openmw-g6-render-check "${G6_ROOT}/tests/render_check.cpp")
target_link_libraries(openmw-g6-render-check PRIVATE g6-world)
set_target_properties(openmw-g6-render-check PROPERTIES CXX_EXTENSIONS OFF)
if(WIN32 AND CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND G4_CPU_PROVIDER)
  foreach(_g6_binary openmw-g6-render-check openmw-g6-world-check)
    target_link_options(${_g6_binary} PRIVATE -g)
  endforeach()
endif()
add_test(NAME g6-live-render-lifecycle COMMAND "${Python3_EXECUTABLE}" "${G6_ROOT}/tools/run_cases.py"
  --render-binary "$<TARGET_FILE:openmw-g6-render-check>" --shaders "${G4_GENERATED}/Shaders"
  --output "${CMAKE_CURRENT_BINARY_DIR}/g6-render-cases.json")
endif()
# Interface/translation-unit gate only. Do not link this object into the app or
# claim Scene activation without its real World/RenderingManager/services.
add_library(g6-scene-compile OBJECT EXCLUDE_FROM_ALL "${G4_REPO}/apps/openmw/mwworld/scene.cpp")
target_link_libraries(g6-scene-compile PRIVATE g6-live-world)
target_include_directories(g6-scene-compile PRIVATE "${_g6_sdl}/include" "${G4_REPO}/extern/sol3")
set_target_properties(g6-scene-compile PROPERTIES CXX_EXTENSIONS OFF)
