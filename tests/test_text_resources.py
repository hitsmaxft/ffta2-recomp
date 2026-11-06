# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from text_resources import block_slot

def index(end):
    return bytes(4)+struct.pack('<IH',0,0)+struct.pack('<IH',(end//4)<<3,0)

class TextResourceTests(unittest.TestCase):
    def test_table_slot_and_absolute_metadata_addresses(self):
        pak=struct.pack('<HIIH',1,4,12,1)+b'ABCD'
        slot=block_slot(index(len(pak)),pak,0x1000,'event:0:0:0',0,0,False)
        self.assertEqual((slot.offset,slot.capacity,slot.length_field,slot.lines_field),(0x100c,4,0x1002,0x100a))
        self.assertEqual(slot.data,b'ABCD')
    def test_string_cannot_overrun_next_block(self):
        pak=struct.pack('<HIIH',1,5,12,1)+b'ABCD'
        with self.assertRaisesRegex(ValueError,'beyond block'):
            block_slot(index(len(pak)),pak,0,'event:0:0:0',0,0,False)
    def test_header_cannot_be_overwritten_as_text(self):
        pak=struct.pack('<HIIH',1,4,4,1)+b'ABCD'
        with self.assertRaisesRegex(ValueError,'overlaps table'):
            block_slot(index(len(pak)),pak,0,'event:0:0:0',0,0,False)
    def test_single_header(self):
        pak=bytes(4)+struct.pack('<I',2)+bytes(4)+struct.pack('<H',1)+b'XY'
        slot=block_slot(index(len(pak)),pak,0x20,'questtext:0:0:0',0,0,True)
        self.assertEqual(slot.data,b'XY')
        self.assertEqual(slot.offset,0x2e)
    def test_absent_block_rejected(self):
        idx=bytearray(index(16));struct.pack_into('<I',idx,4,1)
        with self.assertRaisesRegex(ValueError,'Absent'):
            block_slot(idx,bytes(16),0,'event:0:0:0',0,0,False)

if __name__=='__main__':unittest.main()
