# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from usa_text import tokens, repair_terminal_padding
from usa_cn_release import arm_immediate, patch_word
from export_usa_cn import decode


class UsaTextTest(unittest.TestCase):
    def test_low_byte_zero_is_part_of_glyph_not_terminator(self):
        raw = bytes.fromhex('a900c2000000c100')
        self.assertEqual(tokens(raw), [bytes.fromhex(s) for s in ['a900','c200','c100']])
        fixed = repair_terminal_padding(raw)
        self.assertEqual(fixed, bytes.fromhex('a900c200c1000000'))
        self.assertEqual(tokens(fixed), tokens(raw))

    def test_padding_repair_preserves_controls_and_capacity(self):
        for raw in [bytes.fromhex('02030000c200c100'), bytes.fromhex('0203c20000000000c100')]:
            fixed = repair_terminal_padding(raw)
            self.assertEqual(len(raw), len(fixed))
            self.assertEqual(tokens(raw), tokens(fixed))
            text, controls, _, issues = decode(fixed, True, {})
            self.assertEqual(controls, ['C200','C100'])
            self.assertNotIn('data_after_terminator', issues)

    def test_unsafe_suffix_and_truncated_tokens_are_rejected(self):
        for raw in [bytes.fromhex('02000003'), bytes.fromhex('02a9'), bytes.fromhex('02c1')]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                repair_terminal_padding(raw)

    def test_private_import_retains_glyph_number(self):
        text, controls, glyphs, issues = decode(bytes.fromhex('a900c200c100'), True, {168:'X'})
        self.assertEqual(glyphs, [168])
        self.assertTrue(text.startswith('X'))
        self.assertEqual(controls, ['C200','C100'])
        self.assertEqual(issues, [])

    def test_heap_sizes_are_encodable_arm_operands(self):
        for size in [0x2400, 0x7800, 0x41000, 0x47000]:
            value = arm_immediate(size)
            byte, rotation = value & 255, (value >> 8)*2
            expanded = ((byte >> rotation) | (byte << (32-rotation))) & 0xffffffff if rotation else byte
            self.assertEqual(expanded, size)

    def test_word_guards_reject_wrong_revision_without_mutation(self):
        data = bytearray(struct.pack('<I', 0xe7d04005))
        before = bytes(data)
        with self.assertRaises(ValueError):
            patch_word(data, 0, 0, 1, 'test', [], 0x2000000)
        self.assertEqual(bytes(data), before)
        changes = []
        patch_word(data, 0, 0xe7d04005, 0xe7d04085, 'test', changes, 0x2000000)
        self.assertEqual((struct.unpack('<I', data)[0] >> 7) & 31, 1)
        self.assertEqual(len(changes), 1)


if __name__ == '__main__':
    unittest.main()
