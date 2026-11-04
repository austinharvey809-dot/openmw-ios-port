"""Deterministic original texture tests; no imaging or native dependencies."""

from pathlib import Path
import tempfile
import unittest

from generate_checkerboard import BLUE, HEIGHT, LIGHT, WIDTH, checkerboard_rgba, main


class CheckerboardTests(unittest.TestCase):
    def test_size_colors_and_cell_boundaries(self):
        data = checkerboard_rgba()
        self.assertEqual((WIDTH, HEIGHT, len(data)), (32, 32, 4096))

        def pixel(x, y):
            offset = (y * WIDTH + x) * 4
            return tuple(data[offset:offset + 4])

        for x, y in ((0, 0), (3, 3), (4, 4), (31, 31)):
            self.assertEqual(pixel(x, y), LIGHT)
        for x, y in ((4, 0), (0, 4), (31, 0), (0, 31)):
            self.assertEqual(pixel(x, y), BLUE)
        pixels = [tuple(data[index:index + 4]) for index in range(0, len(data), 4)]
        self.assertEqual(set(pixels), {LIGHT, BLUE})
        self.assertEqual(pixels.count(LIGHT), 512)
        self.assertEqual(pixels.count(BLUE), 512)
        self.assertTrue(all(pixel[3] == 255 for pixel in pixels))

    def test_generation_is_deterministic_and_cli_creates_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assets" / "checkerboard.rgba"
            self.assertEqual(main(["--output", str(output)]), 0)
            first = output.read_bytes()
            self.assertEqual(main(["--output", str(output)]), 0)
            self.assertEqual(first, output.read_bytes())
            self.assertEqual(first, checkerboard_rgba())


if __name__ == "__main__":
    unittest.main()
