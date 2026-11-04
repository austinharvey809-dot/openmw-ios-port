"""Generate this experiment's original 32x32 RGBA8 checkerboard; no image libraries."""

import argparse
from pathlib import Path

WIDTH = HEIGHT = 32
CELL_SIZE = 4
LIGHT = (232, 232, 216, 255)
BLUE = (32, 88, 144, 255)


def checkerboard_rgba() -> bytes:
    """Row-major opaque RGBA8, top row first, with 4x4-texel alternating checks."""
    return bytes(channel
                 for y in range(HEIGHT)
                 for x in range(WIDTH)
                 for channel in (LIGHT if ((x // CELL_SIZE) + (y // CELL_SIZE)) % 2 == 0 else BLUE))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(checkerboard_rgba())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
