# Apply the complete preserved D math ABI before the single renderer provider configures.
file(READ "${G1B_REPO}/experiments/ios-openmw-esm/data/source-audit.json" _d)
string(JSON _count LENGTH "${_d}" osg_config_defines)
math(EXPR _last "${_count} - 1")
foreach(_i RANGE 0 ${_last})
    string(JSON _name MEMBER "${_d}" osg_config_defines ${_i})
    string(JSON _value GET "${_d}" osg_config_defines "${_name}")
    set(${_name} "${_value}" CACHE BOOL "Preserved OpenMW math ABI" FORCE)
endforeach()
# Genuine supported pthread fallback: no cross-compilation try_run/OSAtomic assumption.
set(OPENTHREADS_ATOMIC_USE_MUTEX ON CACHE BOOL "Device-safe upstream atomic implementation" FORCE)
set(BUILD_OSG_PLUGINS_BY_DEFAULT OFF CACHE BOOL "No plugins" FORCE)
