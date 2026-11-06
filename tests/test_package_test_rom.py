# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from package_test_rom import difference_segments
from bps import build,apply

class TestPackagingTests(unittest.TestCase):
    def test_relocated_asset_is_source_copy_not_literal(self):
        source=b'header-ORIGINAL-ASSET---tail-----'
        target=bytearray(source)
        target[21:31]=source[7:17]
        target=bytes(target)
        copies=[(21,7,10)]
        self.assertEqual(target[21:31],source[7:17])
        segments=difference_segments(source,target,copies)
        self.assertTrue(any(s==('source',7,10) for s in segments))
        patch,recreated=build(source,segments)
        self.assertEqual(recreated,target);self.assertEqual(apply(source,patch),target)
    def test_changed_asset_refuses_source_copy(self):
        with self.assertRaisesRegex(ValueError,'differs'):
            difference_segments(b'abcdefgh',b'abcXYZgh',[(3,0,3)])
    def test_size_change_rejected(self):
        with self.assertRaises(ValueError):difference_segments(b'a',b'ab')

if __name__=='__main__':unittest.main()
