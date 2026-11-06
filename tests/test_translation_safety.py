# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from validate_translation import RetailCodec, inspect_row

class SafetyTests(unittest.TestCase):
    def setUp(self):
        charset=json.loads((Path(__file__).resolve().parents[1]/'config/western-charset.json').read_text())
        self.codec=RetailCodec(charset, [6]*168, extended_bytes=3)
    def row(self, source, translation, capacity):
        original=dict(id='event:0:1:0',source_text=source,byte_length=str(capacity),source_sha256='fixture')
        return inspect_row(dict(original,translation=translation),original,self.codec)
    def test_multibyte_capacity_is_not_unicode_character_count(self):
        r=self.row('AB\\end\\','中文\\end\\',4)
        self.assertEqual(r['encoded_bytes'],8)
        self.assertTrue(any('allocation' in e for e in r['errors']))
    def test_parameter_change_is_rejected(self):
        r=self.row('ABC\\varA:00\\\\end\\','中\\varA:01\\\\end\\',7)
        self.assertIn('Control sequence or parameters differ',r['errors'])
    def test_pixel_overflow_even_when_bytes_fit(self):
        r=self.row('AA\nAA\\end\\','中文\\end\\',8)
        self.assertTrue(any('wider' in e for e in r['errors']))
    def test_original_line_count_not_expanded(self):
        r=self.row('ABCDEFGH\\end\\','中\n文\\end\\',10)
        self.assertTrue(any('additional lines' in e for e in r['errors']))
    def test_preserved_dynamic_substitution_remains_runtime_gate(self):
        r=self.row('ABCD\\varA:00\\\\end\\','中\\varA:00\\\\end\\',8)
        self.assertEqual(r['errors'],[])
        self.assertTrue(r['warnings'])
    def test_unknown_control_fails_closed(self):
        r=self.row('AB\\end\\','中\\unsafe:00\\\\end\\',4)
        self.assertTrue(any('Unrecognized' in e for e in r['errors']))

if __name__=='__main__': unittest.main()
