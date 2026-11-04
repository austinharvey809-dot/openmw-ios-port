// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

namespace smoke
{
    enum class GeometryMode { Triangle, Cube };

    class RenderMode
    {
    public:
        void configure(bool geometryAvailable, bool cubeAvailable, GeometryMode selected, bool clear)
        {
            mGeometryAvailable = geometryAvailable;
            mCubeAvailable = geometryAvailable && cubeAvailable;
            mSelected = mCubeAvailable ? selected : GeometryMode::Triangle;
            mClear = !geometryAvailable || clear;
        }
        // DualShock 4 Triangle / GameController Y / SDL controller Y.
        void toggleClear() { if (mGeometryAvailable) mClear = !mClear; }
        // DualShock 4 Square / GameController X / SDL controller X.
        // Selecting geometry while clear remains active must not turn clear off.
        void toggleGeometry()
        {
            if (mCubeAvailable)
                mSelected = mSelected == GeometryMode::Triangle ? GeometryMode::Cube : GeometryMode::Triangle;
        }
        bool clear() const { return mClear; }
        bool cube() const { return !mClear && mSelected == GeometryMode::Cube; }
        bool geometryAvailable() const { return mGeometryAvailable; }
        bool cubeAvailable() const { return mCubeAvailable; }
        GeometryMode selected() const { return mSelected; }
        const char* label() const
        {
            if (mClear) return mSelected == GeometryMode::Cube ? "CLEAR (cube selected)" : "CLEAR (triangle selected)";
            return mSelected == GeometryMode::Cube ? "TEXTURED CUBE" : "TRIANGLE";
        }
    private:
        bool mGeometryAvailable = false, mCubeAvailable = false, mClear = true;
        GeometryMode mSelected = GeometryMode::Triangle;
    };
}
