include("${CMAKE_CURRENT_LIST_DIR}/store.cmake")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G5_ROOT}/tools/provenance.py"
  --output "${G5_GENERATED}" --g4-public "${G4_GENERATED}/public" --lua "${G5_LUA_SOURCE}"
  COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
add_executable(IOSOpenMWEngine MACOSX_BUNDLE "${G5_GENERATED}/main.mm" "${G5_GENERATED}/OSGScene.hpp")
get_target_property(_includes IOSOpenMWWorld INCLUDE_DIRECTORIES)
get_target_property(_links IOSOpenMWWorld LINK_LIBRARIES)
list(REMOVE_ITEM _links g4-upstream)
target_include_directories(IOSOpenMWEngine BEFORE PRIVATE "${G5_GENERATED}" "${G5_ROOT}/src")
target_include_directories(IOSOpenMWEngine PRIVATE ${_includes})
target_link_libraries(IOSOpenMWEngine PRIVATE g5-world ${_links})
target_compile_options(IOSOpenMWEngine PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
target_link_options(IOSOpenMWEngine PRIVATE "-Wl,-no_adhoc_codesign")
configure_file("${G4_ROOT}/device/Info.plist.in" "${G5_GENERATED}/Info.plist.in" COPYONLY)
set_target_properties(IOSOpenMWEngine PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS OFF
  OBJCXX_STANDARD 20 OBJCXX_STANDARD_REQUIRED YES OBJCXX_EXTENSIONS OFF
  BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "@executable_path/Frameworks" INSTALL_RPATH_USE_LINK_PATH FALSE
  MACOSX_BUNDLE_GUI_IDENTIFIER "org.openmw.experiments.real-model"
  MACOSX_BUNDLE_INFO_PLIST "${G5_GENERATED}/Info.plist.in" XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
foreach(_dir Frameworks Licenses Provenance)
  add_custom_command(TARGET IOSOpenMWEngine POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
    "${G4_BASE_PREPARED}/resources/${_dir}" "$<TARGET_BUNDLE_DIR:IOSOpenMWEngine>/${_dir}")
endforeach()
add_custom_command(TARGET IOSOpenMWEngine POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_directory
  "${G5_GENERATED}/public" "$<TARGET_BUNDLE_DIR:IOSOpenMWEngine>")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/g5-product-$<CONFIG>.txt"
  CONTENT "$<TARGET_FILE:IOSOpenMWEngine>\n$<TARGET_BUNDLE_DIR:IOSOpenMWEngine>\n${G4_BASE_PREPARED}\n")
