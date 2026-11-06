import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('prepare_recomp', Path(__file__).resolve().parents[1] / 'tools/prepare_recomp.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreparationTests(unittest.TestCase):
    def test_reject_checkout_and_symlink_resolution(self):
        with self.assertRaises(ValueError):
            module.external_output(module.ROOT / 'generated')

    def test_coverage_modes_and_identity(self):
        doc = {'entries': [{'cpu': 9, 'pc': '0x02000800', 'thumb': 0}]}
        self.assertEqual(list(module.coverage_entries(doc)), [('arm9', 0x02000800, 'arm')])
        doc['rom_sha1'] = '0' * 40
        with self.assertRaises(ValueError):
            list(module.coverage_entries(doc))

    def test_reject_ambiguous_modes(self):
        with self.assertRaises(ValueError):
            list(module.coverage_entries({'entries': [{'cpu': 9, 'pc': 0x2000800, 'thumb': 2}]}))


if __name__ == '__main__':
    unittest.main()
