import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_native_localization import checked_text


class LocalizationBuilderTests(unittest.TestCase):
    def setUp(self):
        raw = b'original-script\xca\x00\xc1\x00'
        self.original = {'source_sha256': hashlib.sha256(raw).hexdigest(),
                         'source_text': 'Hello\\varA:00\\\\end\\'}
        self.row = dict(self.original, id='event:0:1:0', translation='你好\\varA:00\\\\end\\')
        self.resources = SimpleNamespace(locate=lambda key: SimpleNamespace(data=raw))

    def test_variable_parameter_and_order_are_immutable(self):
        checked_text(self.row, self.original, self.resources)
        self.row['translation'] = '你好\\varA:01\\\\end\\'
        with self.assertRaisesRegex(ValueError, 'Script controls'):
            checked_text(self.row, self.original, self.resources)

    def test_actual_original_bytes_are_checked(self):
        self.resources.locate = lambda key: SimpleNamespace(data=b'changed')
        with self.assertRaisesRegex(ValueError, 'Actual ROM'):
            checked_text(self.row, self.original, self.resources)

    def test_malformed_control_rejected(self):
        self.row['translation'] += '\\broken'
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            checked_text(self.row, self.original, self.resources)


if __name__ == '__main__':
    unittest.main()
