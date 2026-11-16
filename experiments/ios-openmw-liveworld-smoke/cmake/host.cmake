include("${CMAKE_CURRENT_LIST_DIR}/runtime.cmake")
add_executable(openmw-g6-live-check "${G6_ROOT}/tests/live_check.cpp")
target_link_libraries(openmw-g6-live-check PRIVATE g6-live-world)
set_target_properties(openmw-g6-live-check PROPERTIES CXX_EXTENSIONS OFF)
if(WIN32 AND CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND G4_CPU_PROVIDER)
  # Retain local public symbols for DbgHelp. -g at link does not change the
  # optimized instruction bytes; the regression fault was verified this way.
  target_link_options(openmw-g6-live-check PRIVATE -g)
endif()
add_test(NAME g6-live-world COMMAND "${Python3_EXECUTABLE}" "${G6_ROOT}/tools/run_cases.py"
  --binary "$<TARGET_FILE:openmw-g6-live-check>" --output "${CMAKE_CURRENT_BINARY_DIR}/g6-live-cases.json")
include("${CMAKE_CURRENT_LIST_DIR}/renderer.cmake")
