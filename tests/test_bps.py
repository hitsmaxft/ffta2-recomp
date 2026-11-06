# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib,sys,unittest,struct,zlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from bps import apply,build
class BpsTests(unittest.TestCase):
 def test_sourcecopy_and_literal(self):
  source=b'abcdefgh';patch,target=build(source,[('source',0,2),('source',6,2),('literal',b'XY'),('source',2,2)])
  self.assertEqual(target,b'abghXYcd');self.assertEqual(apply(source,patch),target)
  # First source action encodes SourceRead; later relocation must be SourceCopy.
  self.assertIn(b'BPS1',patch)
 def test_corruption_is_rejected(self):
  p,_=build(b'abc',[('literal',b'new')])
  with self.assertRaisesRegex(ValueError,'Source checksum'):apply(b'xyz',p)
  bad=p[:-1]+bytes([p[-1]^1])
  with self.assertRaisesRegex(ValueError,'Patch checksum'):apply(b'abc',bad)
 def test_target_overflow_is_rejected(self):
  # Hand-assembled BPS with target size 1 and a two-byte literal action.
  p=b'BPS1'+bytes([0x81,0x81,0x80,0x85])+b'xx'+struct.pack('<II',zlib.crc32(b'a'),0)
  p+=struct.pack('<I',zlib.crc32(p))
  with self.assertRaisesRegex(ValueError,'overflow'):apply(b'a',p)
if __name__=='__main__':unittest.main()
