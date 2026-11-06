# SPDX-License-Identifier: GPL-3.0-or-later
"""Indexed glyph layers; colors remain entirely controlled by retail palettes."""
import struct

def retail_layers(packed):
    if len(packed)!=64:
        raise ValueError('Expected a 16x16 2bpp glyph')
    strokes={(x,y) for y in range(16) for x in range(16)
             if (int.from_bytes(packed[y*4:y*4+4],'little')>>(2*x))&3==3}
    outline={(x+dx,y+dy) for x,y in strokes for dy in (-1,0,1) for dx in (-1,0,1)
             if 0<=x+dx<16 and 0<=y+dy<16}
    shadow={(x+1,y+1) for x,y in strokes if x+1<16 and y+1<16}
    # The layer roles, rather than a hard-coded color, match the retail 2bpp path.
    return b''.join(struct.pack('<I',sum((3 if (x,y) in strokes else
                                        2 if (x,y) in shadow else
                                        1 if (x,y) in outline else 0)<<(2*x)
                                       for x in range(16))) for y in range(16))
