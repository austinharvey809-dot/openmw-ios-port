# ImageManager's upstream static registration list is retained in full. These
# are actual pinned OSG plugins, never placeholder registration symbols.
set(_plugins "${G4_OSG_SOURCE}/src/osgPlugins")
foreach(_plugin dds tga bmp png)
  string(TOUPPER "${_plugin}" _upper)
  add_library(g4-plugin-${_plugin} STATIC "${_plugins}/${_plugin}/ReaderWriter${_upper}.cpp")
  target_link_libraries(g4-plugin-${_plugin} PUBLIC osgDB osg)
endforeach()
set(G4_REGISTRATION_LIBRARIES g4-plugin-dds g4-plugin-tga g4-plugin-bmp g4-plugin-png
  g4-plugin-jpeg g4-plugin-osg g4-serializers-osg osgAnimation osgParticle osgShadow
  osgViewer osgGA osgText osgDB osgUtil osg OpenThreads)
target_link_libraries(g4-plugin-png PRIVATE g4-png ZLIB::ZLIBSTATIC)
add_library(g4-plugin-jpeg STATIC "${_plugins}/jpeg/ReaderWriterJPEG.cpp" "${_plugins}/jpeg/EXIF_Orientation.cpp")
target_include_directories(g4-plugin-jpeg PRIVATE "${G4_DEPENDENCIES_SOURCE}/jpeg/src" "${CMAKE_CURRENT_BINARY_DIR}/g4-deps/jpeg")
target_link_libraries(g4-plugin-jpeg PUBLIC osgDB osg PRIVATE jpeg-static)
add_dependencies(g4-plugin-jpeg g4-jpeg-build)
add_library(g4-plugin-osg STATIC "${_plugins}/osg/ReaderWriterOSG.cpp" "${_plugins}/osg/ReaderWriterOSG2.cpp")
target_link_libraries(g4-plugin-osg PUBLIC osgDB osg)
file(GLOB _serializers CONFIGURE_DEPENDS "${G4_OSG_SOURCE}/src/osgWrappers/serializers/osg/*.cpp")
add_library(g4-serializers-osg STATIC ${_serializers})

set(_g4_compat_args --source "${G4_OSG_SOURCE}" --output "${G4_GENERATED}/gles-compat.json")
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  list(APPEND _g4_compat_args --angle "${ANGLE_ROOT}")
endif()
execute_process(COMMAND "${Python3_EXECUTABLE}" "${G4_ROOT}/tools/osg_compat.py" ${_g4_compat_args}
  COMMAND_ERROR_IS_FATAL ANY OUTPUT_QUIET)
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  # The genuine GLenum serializer consumes the numeric default, not its token
  # spelling. Both Khronos spellings are 0x82E0; no API or source is substituted.
  set_property(SOURCE "${G4_OSG_SOURCE}/src/osgWrappers/serializers/osg/BufferIndexBinding.cpp"
    TARGET_DIRECTORY g4-serializers-osg APPEND PROPERTY COMPILE_DEFINITIONS "GL_BUFFER=GL_BUFFER_KHR")
endif()
target_link_libraries(g4-serializers-osg PUBLIC osgDB osg)
foreach(_target g4-plugin-dds g4-plugin-tga g4-plugin-bmp g4-plugin-png g4-plugin-jpeg g4-plugin-osg g4-serializers-osg)
  target_include_directories(${_target} BEFORE PUBLIC "${G4_OSG_GENERATED_INCLUDE}" "${G4_OSG_SOURCE}/include")
  target_compile_features(${_target} PUBLIC cxx_std_20)
  if(NOT G4_SHARED_DESKTOP_PROVIDER)
    target_compile_definitions(${_target} PUBLIC OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
  endif()
endforeach()
