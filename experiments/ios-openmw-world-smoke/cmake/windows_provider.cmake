# Optional Windows CPU validation against an already verified G3 desktop build.
# This does not supply or alter the iPhoneOS provider or produce a device app.
if(NOT WIN32 OR NOT G4_CPU_PROVIDER)
  message(FATAL_ERROR "Supply an existing Windows CPU provider build")
endif()
set(G4_SHARED_DESKTOP_PROVIDER ON)
set(G4_OSG_GENERATED_INCLUDE "${G4_CPU_PROVIDER}/osg/include")
foreach(_name osg osgDB osgUtil osgGA osgViewer osgText osgParticle osgAnimation osgShadow OpenThreads)
  if(NOT EXISTS "${G4_CPU_PROVIDER}/osg/lib/lib${_name}.dll.a")
    message(FATAL_ERROR "Missing supplemental desktop provider ${_name}")
  endif()
  add_library(${_name} SHARED IMPORTED)
  set_target_properties(${_name} PROPERTIES
    IMPORTED_IMPLIB "${G4_CPU_PROVIDER}/osg/lib/lib${_name}.dll.a"
    IMPORTED_LOCATION "${G4_CPU_PROVIDER}/osg/bin/lib${_name}.dll")
endforeach()
foreach(_name BulletDynamics BulletCollision LinearMath)
  add_library(${_name} STATIC IMPORTED)
  set_target_properties(${_name} PROPERTIES IMPORTED_LOCATION "${G4_CPU_PROVIDER}/lib/lib${_name}.a")
endforeach()
