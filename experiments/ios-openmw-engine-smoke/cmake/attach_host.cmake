# Injected only by the isolated G5 configuration. Accepted G4 is intact.
cmake_language(EVAL CODE "cmake_language(DEFER CALL include [[${CMAKE_CURRENT_LIST_DIR}/host.cmake]])")
