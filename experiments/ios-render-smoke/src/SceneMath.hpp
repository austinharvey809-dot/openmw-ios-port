// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <type_traits>

namespace smoke
{
    struct CubeVertex
    {
        std::array<float, 3> position;
        std::array<float, 2> uv;
    };
    static_assert(std::is_standard_layout<CubeVertex>::value && sizeof(CubeVertex) == 5 * sizeof(float),
        "Cube vertex input must be five contiguous floats");

    // Original geometry: each face has its own UVs, wound counterclockwise from outside.
    inline constexpr std::array<CubeVertex, 24> cubeVertices{{
        {{{-1, -1,  1}}, {{0, 1}}}, {{{ 1, -1,  1}}, {{1, 1}}},
        {{{ 1,  1,  1}}, {{1, 0}}}, {{{-1,  1,  1}}, {{0, 0}}}, // front
        {{{ 1, -1, -1}}, {{0, 1}}}, {{{-1, -1, -1}}, {{1, 1}}},
        {{{-1,  1, -1}}, {{1, 0}}}, {{{ 1,  1, -1}}, {{0, 0}}}, // back
        {{{ 1, -1,  1}}, {{0, 1}}}, {{{ 1, -1, -1}}, {{1, 1}}},
        {{{ 1,  1, -1}}, {{1, 0}}}, {{{ 1,  1,  1}}, {{0, 0}}}, // right
        {{{-1, -1, -1}}, {{0, 1}}}, {{{-1, -1,  1}}, {{1, 1}}},
        {{{-1,  1,  1}}, {{1, 0}}}, {{{-1,  1, -1}}, {{0, 0}}}, // left
        {{{-1,  1,  1}}, {{0, 1}}}, {{{ 1,  1,  1}}, {{1, 1}}},
        {{{ 1,  1, -1}}, {{1, 0}}}, {{{-1,  1, -1}}, {{0, 0}}}, // top
        {{{-1, -1, -1}}, {{0, 1}}}, {{{ 1, -1, -1}}, {{1, 1}}},
        {{{ 1, -1,  1}}, {{1, 0}}}, {{{-1, -1,  1}}, {{0, 0}}}, // bottom
    }};
    inline constexpr std::array<uint16_t, 36> cubeIndices{{
         0,  1,  2,  2,  3,  0,   4,  5,  6,  6,  7,  4,
         8,  9, 10, 10, 11,  8,  12, 13, 14, 14, 15, 12,
        16, 17, 18, 18, 19, 16,  20, 21, 22, 22, 23, 20,
    }};

    // Column-major matrices multiply column vectors, matching GLSL's mat4 layout.
    using Matrix4 = std::array<float, 16>;
    inline constexpr float scenePi = 3.14159265358979323846f;

    inline Matrix4 identityMatrix()
    {
        return {{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}};
    }

    inline Matrix4 multiply(const Matrix4& left, const Matrix4& right)
    {
        Matrix4 product{};
        for (unsigned column = 0; column < 4; ++column)
            for (unsigned row = 0; row < 4; ++row)
                for (unsigned inner = 0; inner < 4; ++inner)
                    product[column * 4 + row] += left[inner * 4 + row] * right[column * 4 + inner];
        return product;
    }

    inline Matrix4 rotationX(float radians)
    {
        const float c = std::cos(radians), s = std::sin(radians);
        return {{1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1}};
    }

    inline Matrix4 rotationY(float radians)
    {
        const float c = std::cos(radians), s = std::sin(radians);
        return {{c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1}};
    }

    inline Matrix4 perspective(float aspect, float fovYRadians = scenePi / 4,
        float nearPlane = 0.1f, float farPlane = 30.0f)
    {
        if (!std::isfinite(aspect) || aspect <= 0 || !std::isfinite(fovYRadians)
            || fovYRadians <= 0 || fovYRadians >= scenePi || !std::isfinite(nearPlane)
            || !std::isfinite(farPlane) || nearPlane <= 0 || farPlane <= nearPlane)
            throw std::invalid_argument("Invalid cube perspective parameters");
        const float focal = 1.0f / std::tan(fovYRadians / 2);
        Matrix4 projection{};
        projection[0] = focal / aspect;
        projection[5] = -focal; // Positive-height Vulkan viewport: invert projected Y.
        projection[10] = farPlane / (nearPlane - farPlane);
        projection[11] = -1;
        projection[14] = farPlane * nearPlane / (nearPlane - farPlane);
        return projection; // Right-handed view, Vulkan depth range [0, 1].
    }

    inline Matrix4 cubeModel(double seconds)
    {
        // Reduce angles before conversion to float to retain smooth motion during long runs.
        const float x = static_cast<float>(std::fmod(0.35 + seconds * 0.37, 2.0 * scenePi));
        const float y = static_cast<float>(std::fmod(0.55 + seconds * 0.61, 2.0 * scenePi));
        return multiply(rotationY(y), rotationX(x));
    }

    inline Matrix4 cubeView()
    {
        Matrix4 view = identityMatrix();
        view[14] = -5.0f; // Entire rotating cube stays inside the 45-degree vertical field of view.
        return view;
    }

    inline Matrix4 cubeMvp(float aspect, double seconds)
    {
        return multiply(perspective(aspect), multiply(cubeView(), cubeModel(seconds)));
    }
}
