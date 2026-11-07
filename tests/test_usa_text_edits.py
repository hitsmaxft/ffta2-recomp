# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from usa_text_edits import add_newline, encode, rebuild_multi
from text_resources import block_slot
from usa_text import tokens


class TextRevisionTests(unittest.TestCase):
    def test_newline_insertion_preserves_glyphs_and_controls(self):
        raw = bytes.fromhex('a900cb11a901c200c100')
        result = add_newline(raw, 1)
        self.assertEqual(result, bytes.fromhex('a900c000cb11a901c200c100'))
        self.assertEqual([t for t in tokens(result) if t != b'\xc0\0'], tokens(raw))
        with self.assertRaises(ValueError):
            add_newline(raw, 3)

    def test_unreviewed_unicode_and_unknown_controls_rejected(self):
        self.assertEqual(encode('X中\\sprite:11\\', {'中': 168}), bytes.fromhex('19a900cb11'))
        for text in ['文', '\\unsafe:11\\']:
            with self.assertRaises(ValueError):
                encode(text, {'中': 168})

    def test_repack_expands_block_and_keeps_neighbor_allocations(self):
        block = struct.pack('<HIIH', 1, 2, 12, 1) + b'A\0\0\0'
        pak = block * 2
        idx = struct.pack('<I', 0) + b''.join(struct.pack('<IH', (off // 4) << 3, 0x1234)
                                             for off in (0, 16, 32))
        new_idx, new_pak = rebuild_multi(idx, pak, {'message:0:0:0': (b'longer\xc0\0text\0', 2)})
        a = block_slot(new_idx, new_pak, 0, 'message:0:0:0', 0, 0, False)
        b = block_slot(new_idx, new_pak, 0, 'message:0:1:0', 1, 0, False)
        self.assertEqual(a.data, b'longer\xc0\0text\0')
        self.assertEqual(a.original_lines, 2)
        self.assertEqual(b.data, b'A\0')
        self.assertEqual(new_idx[8:10], idx[8:10])
        self.assertGreater(b.offset, 16)
        self.assertEqual(new_pak[-16:], block)

    def test_missing_sid_and_invalid_allocations_rejected(self):
        idx = struct.pack('<IIHIH', 0, 0, 0, 32, 0)
        block = struct.pack('<HIIH', 1, 2, 12, 1) + b'A\0\0\0'
        with self.assertRaises(ValueError):
            rebuild_multi(idx, block, {'message:0:0:5': (b'X', 1)})


if __name__ == '__main__':
    unittest.main()
