include("${CMAKE_CURRENT_LIST_DIR}/runtime.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/renderer.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G6_ROOT}/tools/provenance.py"
  --output "${G6_GENERATED}" --g5-public "${G5_GENERATED}/public"
  --dependencies "${G6_DEPENDENCIES_SOURCE}" --lua "${G5_LUA_SOURCE}"
  COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
add_executable(IOSOpenMWLiveWorld MACOSX_BUNDLE "${G6_GENERATED}/main.mm" "${G6_GENERATED}/OSGScene.hpp")
get_target_property(_g6_app_includes IOSOpenMWWorld INCLUDE_DIRECTORIES)
get_target_property(_g6_app_links IOSOpenMWWorld LINK_LIBRARIES)
list(REMOVE_ITEM _g6_app_links g4-upstream)
target_include_directories(IOSOpenMWLiveWorld BEFORE PRIVATE "${G6_GENERATED}" "${G6_ROOT}/src")
target_include_directories(IOSOpenMWLiveWorld PRIVATE ${_g6_app_includes})
target_link_libraries(IOSOpenMWLiveWorld PRIVATE g6-world ${_g6_app_links})
target_compile_options(IOSOpenMWLiveWorld PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWLiveWorld PRIVATE "-Wl,-no_adhoc_codesign")
configure_file("${G4_ROOT}/device/Info.plist.in" "${G6_GENERATED}/Info.plist.in" COPYONLY)
set_target_properties(IOSOpenMWLiveWorld PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS OFF
  OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF
  BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
  MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
  MACOSX_BUNDLE_INFO_PLIST "${G6_GENERATED}/Info.plist.in" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
foreach(_g6_dir Frameworks Licenses Provenance)
  add_custom_command(TARGET IOSOpenMWLiveWorld POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${G4_BASE_PREPARED}/resources/${_g6_dir}" "$<TARGET_BUNDLE_DIR:IOSOpenMWLiveWorld>/${_g6_dir}")
endforeach()
add_custom_command(TARGET IOSOpenMWLiveWorld POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
  "${G6_GENERATED}/public" "$<TARGET_BUNDLE_DIR:IOSOpenMWLiveWorld>")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g6-product-$<CONFIG>.txt"
  CONTENT "$<TARGET_FILE:IOSOpenMWLiveWorld>\n$<TARGET_BUNDLE_DIR:IOSOpenMWLiveWorld>\n${G4_BASE_PREPARED}\n")
