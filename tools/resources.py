# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import struct,json,re
R=Path(os.environ['FFTA2_ANALYSIS_DIR']); inv=json.loads((R/'rom_inventory.json').read_text()); I=(R/'extracted/master/pc.idx').read_bytes(); B=(R/'extracted/master/pc.bin').read_bytes(); BASE=inv['files']['master/pc.bin']['rom_offset']
u16=lambda b,o=0:struct.unpack_from('<H',b,o)[0]
u32=lambda b,o=0:struct.unpack_from('<I',b,o)[0]
N=u32(I);EX=8+9*N
entries=[]
for i in range(N):
 a,b=struct.unpack_from('<II',I,8+9*i); off=(a&0x3ffffff)*2;sz=((a>>26)+(b&65535)*64)*4;parts=[]
 if a or b:
  if a&1:
   pos=off//4; num=I[pos];pos+=1
   for j in range(num):
    of=u32(I,pos)*4;pos+=4
    size=sz
    if j: size=u32(I,pos)*4;pos+=8
    c,cp=I[pos:pos+2];pos+=3
    parts.append(dict(offset=of,size=size,char=chr(c),char_position=cp))
  else:parts=[dict(offset=off,size=sz)]
 for e in parts: assert e['offset']+e['size']<=len(B),(i,e)
 entries.append(parts)
def h(s):
 v=0
 for c in s.encode():v=(v*37+c)&0xffffffff
 return v&1023
def get(name):
 parts=entries[h(name)]
 for e in parts:
  if 'char' not in e or (e['char_position']<len(name) and name[e['char_position']]==e['char']):
   return dict(e,hash_id=h(name),rom_offset=BASE+e['offset'])
 return None
if __name__=='__main__':
 names=['menu/font/'+s+'.bin' for s in ['UseMoji_table','UseMoji_image','FontWidthTable','fontpalette']]
 for s in inv['resource_strings']:
  if '%d' in s['text']:
   names.extend(s['text']%i for i in range(4))
 result={}; dest=R/'resources';dest.mkdir(exist_ok=True)
 for name in dict.fromkeys(names):
  e=get(name)
  if not e:continue
  data=B[e['offset']:e['offset']+e['size']];e['head_hex']=data[:32].hex();result[name]=e
  p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 (R/'resource_offsets.json').write_text(json.dumps(result,indent=2));(R/'archive_entries.json').write_text(json.dumps(entries,indent=2))
 print('archive buckets',N,'subfiles',sum(map(len,entries)))
 for name,e in result.items():print(name,'rom=%08X size=%X hash=%d'%(e['rom_offset'],e['size'],e['hash_id']),e.get('char',''),e.get('char_position',''),e['head_hex'][:32])
