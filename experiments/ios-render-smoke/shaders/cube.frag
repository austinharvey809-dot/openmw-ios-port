// SPDX-License-Identifier: GPL-3.0-or-later
#version 450

layout(location = 0) in vec2 textureUV;
layout(location = 0) out vec4 outColor;
layout(set = 0, binding = 0) uniform sampler2D checkerboard;

void main()
{
    outColor = texture(checkerboard, textureUV);
}
