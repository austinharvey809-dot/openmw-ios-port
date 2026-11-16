# A static font library has no Windows DLL version resource. Preserve all
# genuine FreeType C sources, including builds/windows/ftsystem.c and ftdebug.c.
# This avoids requiring an unrelated GNU windres in the Zig CPU toolchain.
function(g6_static_font_resource)
  if(BUILD_SHARED_LIBS)
    message(FATAL_ERROR "G6 requires static FreeType")
  endif()
  get_target_property(_g6_font_sources freetype SOURCES)
  list(FILTER _g6_font_sources EXCLUDE REGEX "ftver[.]rc$")
  set_property(TARGET freetype PROPERTY SOURCES "${_g6_font_sources}")
endfunction()
cmake_language(DEFER CALL g6_static_font_resource)
