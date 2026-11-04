// SPDX-License-Identifier: GPL-3.0-or-later
#include "../src/RenderMode.hpp"
#include <cstdio>
#include <cstdlib>

void require(bool condition)
{
    if (!condition) { std::fputs("RenderMode test failed\n", stderr); std::exit(1); }
}
int main()
{
    smoke::RenderMode mode;
    using smoke::GeometryMode;
    mode.configure(true, true, GeometryMode::Cube, false);
    require(mode.cube() && !mode.clear());
    mode.toggleClear();
    require(mode.clear() && mode.selected() == GeometryMode::Cube);
    mode.toggleGeometry();
    require(mode.clear() && mode.selected() == GeometryMode::Triangle);
    mode.toggleClear();
    require(!mode.clear() && !mode.cube());
    mode.toggleGeometry();
    require(mode.cube());
    // A triangle-only run has no cube/depth prerequisites and Square is inert.
    mode.configure(true, false, GeometryMode::Cube, false);
    mode.toggleGeometry();
    require(!mode.cubeAvailable() && mode.selected() == GeometryMode::Triangle && !mode.clear());
    mode.toggleClear(); mode.toggleClear();
    require(!mode.clear());
    // A shader-free clear bundle cannot enable either geometry mode.
    mode.configure(false, true, GeometryMode::Cube, false);
    mode.toggleClear(); mode.toggleGeometry();
    require(mode.clear() && !mode.geometryAvailable() && !mode.cubeAvailable());
    // Launch --clear-only remembers its geometry mode until Triangle/Y resumes it.
    mode.configure(true, true, GeometryMode::Cube, true);
    require(mode.clear());
    mode.toggleClear();
    require(mode.cube());
    std::puts("RenderMode tests passed");
}
