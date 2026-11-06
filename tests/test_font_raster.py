# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from font_raster import retail_layers

def pixels(data):
    return [(int.from_bytes(data[y*4:y*4+4],'little')>>(x*2))&3 for y in range(16) for x in range(16)]

class FontRasterTests(unittest.TestCase):
    def test_indexed_layers_preserve_strokes_and_transparency(self):
        raw=bytearray(64);raw[5*4+1]=3<<2
        styled=retail_layers(raw);before=pixels(raw);after=pixels(styled)
        self.assertEqual({i for i,v in enumerate(before) if v==3},{i for i,v in enumerate(after) if v==3})
        self.assertEqual(set(after),{0,1,2,3});self.assertEqual(after[0],0)
        self.assertEqual(retail_layers(styled),styled)
    def test_blank_stays_blank(self):
        self.assertEqual(retail_layers(bytes(64)),bytes(64))
    def test_size_is_guarded(self):
        with self.assertRaises(ValueError):retail_layers(bytes(63))

if __name__=='__main__':unittest.main()
