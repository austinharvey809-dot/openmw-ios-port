include("${CMAKE_CURRENT_LIST_DIR}/store.cmake")
add_executable(openmw-engine-check "${G5_GENERATED}/world_check.cpp")
target_include_directories(openmw-engine-check BEFORE PRIVATE "${G5_GENERATED}")
target_link_libraries(openmw-engine-check PRIVATE g5-world)
add_executable(openmw-g5-store-check "${G5_ROOT}/tests/store_check.cpp")
target_link_libraries(openmw-g5-store-check PRIVATE g5-world)
set_target_properties(openmw-engine-check openmw-g5-store-check PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME g5-engine-store COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/run_engine_cases.py"
  --binary "$<TARGET_FILE:openmw-g5-store-check>" --output "${CMAKE_CURRENT_BINARY_DIR}/g5-store-cases.json")
add_test(NAME g5-engine-world COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/run_engine_cases.py"
  --world-binary "$<TARGET_FILE:openmw-engine-check>" --shaders "${G4_GENERATED}/Shaders"
  --output "${CMAKE_CURRENT_BINARY_DIR}/g5-world-cases.json")
