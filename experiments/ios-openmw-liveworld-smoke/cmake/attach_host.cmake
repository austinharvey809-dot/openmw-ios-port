# Dependencies requiring add_subdirectory/enable_language are prepared while
# project() is executing normally, not from a deferred callback.
include("${CMAKE_CURRENT_LIST_DIR}/dependencies.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/../../ios-openmw-engine-smoke/cmake/attach_host.cmake")
get_filename_component(G6_ATTACH_ROOT "${CMAKE_CURRENT_LIST_DIR}" ABSOLUTE)
cmake_language(DEFER CALL include "${G6_ATTACH_ROOT}/host.cmake")
