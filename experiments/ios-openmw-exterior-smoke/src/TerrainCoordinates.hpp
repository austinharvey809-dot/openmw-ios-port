#pragma once
#include <osg/Vec2f>
namespace G3 {
// Algebraic form of BlendmapTexMat in components/terrain/material.cpp (16 tiles).
inline osg::Vec2f blendCoordinates(float x,float y){
    constexpr float scale=16.f/17.f;
    return {(.5f+(x-.5f+1.f/64.f)*scale),(.5f+(y-.5f-1.f/64.f)*scale)};
}
}
