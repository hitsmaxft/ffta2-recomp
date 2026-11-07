# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from usa_layout_audit import measure, inspect


class FixtureMetrics:
    def glyph(self, index):
        if not 0 <= index < 4368:
            raise ValueError('bad glyph')
        return (12, 0, 13) if index >= 168 else (6, 0, 6)


class LayoutAuditTests(unittest.TestCase):
    def setUp(self):
        self.metrics = FixtureMetrics()

    def test_zero_low_byte_is_a_glyph_and_c1_starts_next_page(self):
        layout = measure(bytes.fromhex('a900c300c100a900c100'), self.metrics, True)
        self.assertEqual([len(p) for p in layout['pages']], [1, 1])
        self.assertEqual([p[0]['advance_px'] for p in layout['pages']], [12, 12])
        self.assertEqual(layout['problems'], [])

    def test_missing_newline_exceeds_width_even_when_allocation_fits(self):
        before = measure(b'\x02' * 20 + b'\xc0\0' + b'\x02' * 20, self.metrics, False)
        after = measure(b'\xa9\0' * 28, self.metrics, True)
        row = inspect('fixture', before, after, 2, {})
        self.assertTrue(any('337px exceeds 255px' in e for e in row['errors']))
        self.assertTrue(any('newline count differs' in w for w in row['warnings']))

    def test_dynamic_width_never_silently_passes_as_zero(self):
        raw = b'\x02\xca\0\xcb\x11\xc1\0'
        layout = measure(raw, self.metrics, True)
        row = inspect('fixture', layout, layout, 1, {})
        self.assertFalse(row['fully_bounded'])
        self.assertTrue(any('CA00,CB11' in w for w in row['warnings']))
        reserved = measure(raw, self.metrics, True, {'CA00': 72, 'CB11': 16})
        row = inspect('fixture', reserved, reserved, 1, {'max_width_px': 80})
        self.assertTrue(any('reserved width exceeds' in e for e in row['errors']))

    def test_explicit_box_limits_and_glyph_counts(self):
        raw = b'\x02' * 62 + b'\xc0\0\x02'
        layout = measure(raw, self.metrics, False)
        row = inspect('fixture', layout, layout, 1, {'max_lines_per_page': 1})
        self.assertTrue(any('lines exceeds box limit' in e for e in row['errors']))
        self.assertTrue(any('descriptor limit' in e for e in row['errors']))

    def test_truncation_and_post_nul_payload_are_errors(self):
        for raw in [b'\xa9', b'\xc1', b'\x02\0\x03']:
            self.assertTrue(measure(raw, self.metrics, True)['problems'])


if __name__ == '__main__':
    unittest.main()
