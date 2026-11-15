# Optional portable compiler archive tools, after compiler detection. This file
# runs through CMAKE_PROJECT_INCLUDE; no dependency source is edited.
if(G4_CPU_AR)
  set(CMAKE_AR "${G4_CPU_AR}")
  set(CMAKE_RANLIB "${G4_CPU_RANLIB}")
endif()
