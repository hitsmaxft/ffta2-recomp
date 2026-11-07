# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from font_raster import retail_layers
from title_texture import label_pixels


def glyph(points):
    return retail_layers(b''.join(struct.pack('<I', sum(3 << (x * 2)
                             for x, yy in points if yy == y)) for y in range(16)))


class TitleTextureTests(unittest.TestCase):
    def test_selected_face_rim_and_lower_shadow_have_distinct_roles(self):
        pixels = label_pixels('a', {'a': glyph({(5, 5)})}, 'selected')
        self.assertEqual(pixels[5, 5], 0xf9)  # Original light face index 25.
        for point in ((4, 5), (6, 5), (5, 4), (5, 6)):
            self.assertEqual(pixels[point], 0xf6)  # Orange rim, never black.
        black = {pos for pos, value in pixels.items() if value & 31 == 1}
        self.assertEqual(black, {(4, 7), (5, 7), (6, 7)})
        self.assertTrue(all(pixels[pos] >> 5 == 3 for pos in black))

    def test_adjacent_rim_cannot_overwrite_foreground(self):
        pixels = label_pixels('ab', {'a': glyph({(12, 5)}),
                                       'b': glyph({(1, 5)})}, 'selected')
        self.assertEqual(pixels[12, 5], 0xf9)
        self.assertEqual(pixels[13, 5], 0xf9)

    def test_each_style_keeps_its_own_palette_indices(self):
        for style, face, rim in [('normal', 11, 7), ('selected', 25, 22),
                                 ('disabled', 28, 1), ('heading', 31, 7)]:
            pixels = label_pixels('a', {'a': glyph({(5, 5)})}, style)
            self.assertEqual(pixels[5, 5] & 31, face)
            self.assertEqual(pixels[4, 5] & 31, rim)


if __name__ == '__main__':
    unittest.main()
