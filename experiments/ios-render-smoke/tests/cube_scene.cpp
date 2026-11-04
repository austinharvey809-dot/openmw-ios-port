// SPDX-License-Identifier: GPL-3.0-or-later
#include "../src/SceneMath.hpp"

#include <cstdio>
#include <cstdlib>
#include <limits>

namespace
{
    void require(bool condition, const char* message)
    {
        if (!condition) { std::fprintf(stderr, "Cube scene test failed: %s\n", message); std::exit(1); }
    }
    bool near(float a, float b) { return std::abs(a - b) < 0.00002f; }
    std::array<float, 4> transform(const smoke::Matrix4& matrix, const std::array<float, 4>& point)
    {
        std::array<float, 4> result{};
        for (unsigned row = 0; row < 4; ++row)
            for (unsigned column = 0; column < 4; ++column)
                result[row] += matrix[column * 4 + row] * point[column];
        return result;
    }
}

int main()
{
    using namespace smoke;
    const auto projection = perspective(2);
    const auto nearPoint = transform(projection, {{0, 0, -0.1f, 1}});
    const auto farPoint = transform(projection, {{0, 0, -30, 1}});
    require(near(nearPoint[2] / nearPoint[3], 0) && near(farPoint[2] / farPoint[3], 1),
        "Vulkan perspective maps near/far to 0/1");
    require(near(projection[5], -2 * projection[0]), "Landscape aspect and Vulkan Y inversion");
    const auto squarePoint = transform(perspective(1), {{0.5f, 0.5f, -2, 1}});
    const auto widePoint = transform(perspective(2), {{0.5f, 0.5f, -2, 1}});
    require(near(squarePoint[0], widePoint[0] * 2) && near(squarePoint[1], widePoint[1]),
        "Orientation/aspect changes horizontal projection without distorting vertical projection");
    const auto origin = transform(cubeView(), {{0, 0, 0, 1}});
    require(near(origin[2], -5.0f) && near(origin[3], 1), "View translation is column-major");

    for (const double seconds : {0.0, 0.5, 10.0, 100000.0})
    {
        const auto model = cubeModel(seconds);
        const auto mvp = cubeMvp(2, seconds);
        for (const float value : mvp) require(std::isfinite(value), "Long-running transform remains finite");
        // Rotation columns remain orthonormal, preserving scale and lengths.
        for (unsigned a = 0; a < 3; ++a)
            for (unsigned b = 0; b < 3; ++b)
            {
                float dot = 0;
                for (unsigned component = 0; component < 3; ++component)
                    dot += model[a * 4 + component] * model[b * 4 + component];
                require(near(dot, a == b ? 1.0f : 0.0f), "Model rotation is orthonormal");
            }
        const float determinant = model[0] * (model[5] * model[10] - model[9] * model[6])
            - model[4] * (model[1] * model[10] - model[9] * model[2])
            + model[8] * (model[1] * model[6] - model[5] * model[2]);
        require(near(determinant, 1), "Rotation preserves handedness");
        const auto center = transform(mvp, {{0, 0, 0, 1}});
        require(near(center[0], 0) && near(center[1], 0) && center[3] > 0,
            "Projection/view/model order keeps cube centered in front of camera");
        for (const auto& vertex : cubeVertices)
        {
            const auto clip = transform(mvp, {{vertex.position[0], vertex.position[1], vertex.position[2], 1}});
            require(clip[3] > 0 && clip[2] > 0 && clip[2] < clip[3], "Cube lies inside depth frustum");
            require(std::abs(clip[0]) < clip[3] && std::abs(clip[1]) < clip[3], "Landscape cube fits view");
        }
    }
    const auto initial = cubeModel(0), rotated = cubeModel(1);
    bool changed = false;
    for (unsigned i = 0; i < initial.size(); ++i) changed |= !near(initial[i], rotated[i]);
    require(changed, "Elapsed time rotates cube");

    require(cubeVertices.size() == 24 && cubeIndices.size() == 36, "Six indexed textured faces");
    for (const auto& vertex : cubeVertices)
        require(vertex.uv[0] >= 0 && vertex.uv[0] <= 1 && vertex.uv[1] >= 0 && vertex.uv[1] <= 1,
            "Every UV lies within original checkerboard");
    for (unsigned triangle = 0; triangle < 12; ++triangle)
    {
        const unsigned offset = triangle * 3;
        for (unsigned corner = 0; corner < 3; ++corner)
            require(cubeIndices[offset + corner] < cubeVertices.size(), "Index stays in vertex buffer");
        const auto& a = cubeVertices[cubeIndices[offset]].position;
        const auto& b = cubeVertices[cubeIndices[offset + 1]].position;
        const auto& c = cubeVertices[cubeIndices[offset + 2]].position;
        const std::array<float, 3> u{{b[0] - a[0], b[1] - a[1], b[2] - a[2]}};
        const std::array<float, 3> v{{c[0] - a[0], c[1] - a[1], c[2] - a[2]}};
        const std::array<float, 3> normal{{u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]}};
        require(normal[0] * a[0] + normal[1] * a[1] + normal[2] * a[2] > 0,
            "All triangles are nondegenerate with consistent outward winding");
    }
    for (const float invalid : {0.0f, -1.0f, std::numeric_limits<float>::infinity()})
    {
        bool rejected = false;
        try { (void)perspective(invalid); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "Invalid aspect is rejected");
    }
    std::puts("Cube geometry and matrix tests passed");
}
