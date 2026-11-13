# One source-only decoder from the same pinned OSG provider. No dynamic plugin search.
add_library(g1c-tga STATIC "${G1C_OSG_SOURCE}/src/osgPlugins/tga/ReaderWriterTGA.cpp")
target_include_directories(g1c-tga BEFORE PUBLIC "$<BUILD_INTERFACE:${G1C_GENERATED_INCLUDE}>"
    "${G1C_OSG_SOURCE}/include")
target_compile_definitions(g1c-tga PRIVATE OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
target_link_libraries(g1c-tga PUBLIC osgDB osg OpenThreads)
if(APPLE)
    # Static TGA registration pulls osgDB's Apple FileUtils object into every
    # consumer, including the C++ link check without UIKit's framework list.
    foreach(_framework Foundation CoreFoundation)
        find_library(G1C_${_framework} NAMES ${_framework} REQUIRED)
        target_link_libraries(g1c-tga PUBLIC "${G1C_${_framework}}")
    endforeach()
endif()
add_library(g1c-texture STATIC "${G1C_ROOT}/src/TextureAdapter.cpp"
    "${G1C_REPO}/components/misc/resourcehelpers.cpp")
target_include_directories(g1c-texture PUBLIC "${G1C_ROOT}/src"
    "${G1C_REPO}/experiments/ios-openmw-bsa-vfs/src")
target_include_directories(g1c-texture BEFORE PUBLIC "$<BUILD_INTERFACE:${G1C_GENERATED_INCLUDE}>")
target_compile_definitions(g1c-texture PUBLIC OSG_LIBRARY_STATIC OPENTHREADS_STATIC)
target_compile_features(g1c-texture PUBLIC cxx_std_20)
target_link_libraries(g1c-texture PUBLIC ${G1C_GEOMETRY_TARGET} g1c-tga)
set_target_properties(g1c-texture PROPERTIES CXX_EXTENSIONS OFF)
add_executable(openmw-textured-nif-check "${G1C_ROOT}/tests/texture_check.cpp")
target_link_libraries(openmw-textured-nif-check PRIVATE g1c-texture)
set_target_properties(openmw-textured-nif-check PROPERTIES CXX_EXTENSIONS OFF)
