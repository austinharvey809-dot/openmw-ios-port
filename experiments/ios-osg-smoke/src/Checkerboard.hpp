#pragma once

// Original fixture: row zero is the v=0 edge. The red 4x4 corner marks (u,v)=(0,0).
// Caller supplies Width*Height*Channels bytes of OSG-owned image storage.
namespace Checkerboard {
constexpr unsigned Width = 32, Height = 32, Channels = 4, Cell = 4;
// Expected chain dimensions only; these do not query GPU allocation.
inline unsigned mipLevelCount(unsigned extent) {
    unsigned count = 0;
    for (; extent; extent >>= 1) ++count;
    return count;
}
inline unsigned mipDimension(unsigned extent, unsigned level) {
    if (!extent) return 0;
    while (level-- && extent > 1) extent >>= 1;
    return extent;
}
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
