#pragma once

// Original fixture: row zero is the v=0 edge. The red 4x4 corner marks (u,v)=(0,0).
// Caller supplies Width*Height*Channels bytes of OSG-owned image storage.
namespace Checkerboard {
constexpr unsigned Width = 32, Height = 32, Channels = 4, Cell = 4;
inline void fill(unsigned char* pixels) {
    for (unsigned y = 0; y < Height; ++y) {
        for (unsigned x = 0; x < Width; ++x) {
            const unsigned offset = (y * Width + x) * Channels;
            const unsigned char shade = ((x / Cell + y / Cell) % 2) ? 240 : 32;
            const bool marker = x < Cell && y < Cell;
            pixels[offset + 0] = marker ? 255 : shade;
            pixels[offset + 1] = marker ? 32 : shade;
            pixels[offset + 2] = marker ? 32 : shade;
            pixels[offset + 3] = 255;
        }
    }
}
}
