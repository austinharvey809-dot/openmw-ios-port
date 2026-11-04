// SPDX-License-Identifier: GPL-3.0-or-later
#version 450

layout(location = 0) in vec3 position;
layout(location = 1) in vec2 uv;
layout(location = 0) out vec2 textureUV;
layout(push_constant) uniform Transform
{
    mat4 mvp;
} transform;

void main()
{
    gl_Position = transform.mvp * vec4(position, 1.0);
    textureUV = uv;
}
