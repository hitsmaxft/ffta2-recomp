# SPDX-License-Identifier: GPL-3.0-or-later
"""BPS1 encoder and checked decoder. SourceCopy keeps retail assets out of patches."""
import struct,zlib

def number(v):
    out=bytearray()
    while True:
        x=v&127;v>>=7
        if not v:return bytes(out+bytes([x|128]))
        out.append(x);v-=1

def signed(v):return number((abs(v)<<1)|(v<0))

def build(source,segments,metadata=b''):
    """segments are ('source', source_offset, length) or ('literal', bytes)."""
    target=bytearray();out=bytearray(b'BPS1'+number(len(source))+number(sum(s[2] if s[0]=='source' else len(s[1]) for s in segments))+number(len(metadata))+metadata);relative=0
    for seg in segments:
        if seg[0]=='source':
            _,offset,length=seg
            if not length:continue
            assert 0<=offset<=offset+length<=len(source)
            if offset==len(target):out+=number(((length-1)<<2)|0)
            else:
                out+=number(((length-1)<<2)|2)+signed(offset-relative);relative=offset+length
            target+=source[offset:offset+length]
        else:
            data=seg[1]
            if not data:continue
            out+=number(((len(data)-1)<<2)|1)+data;target+=data
    out+=struct.pack('<II',zlib.crc32(source),zlib.crc32(target));out+=struct.pack('<I',zlib.crc32(out))
    return bytes(out),bytes(target)

def apply(source,patch):
    if patch[:4]!=b'BPS1' or len(patch)<16:raise ValueError('Not a BPS1 patch')
    if zlib.crc32(patch[:-4])!=struct.unpack_from('<I',patch,len(patch)-4)[0]:raise ValueError('Patch checksum mismatch')
    source_crc,target_crc=struct.unpack_from('<II',patch,len(patch)-12)
    if zlib.crc32(source)!=source_crc:raise ValueError('Source checksum mismatch')
    pos=4
    def read():
        nonlocal pos
        value=0;shift=1
        while True:
            if pos>=len(patch)-12:raise ValueError('Truncated BPS')
            x=patch[pos];pos+=1;value+=(x&127)*shift
            if x&128:return value
            shift<<=7;value+=shift
    source_size,target_size,meta_size=read(),read(),read();pos+=meta_size
    if len(source)!=source_size or target_size>512*1024*1024:raise ValueError('Invalid BPS sizes')
    target=bytearray();sr=tr=0
    while len(target)<target_size:
        action=read();kind=action&3;n=(action>>2)+1
        if len(target)+n>target_size:raise ValueError('BPS output overflow')
        if kind==0:
            o=len(target)
            if o+n>len(source):raise ValueError('SourceRead overflow')
            target+=source[o:o+n]
        elif kind==1:
            if pos+n>len(patch)-12:raise ValueError('TargetRead overflow')
            target+=patch[pos:pos+n];pos+=n
        else:
            delta=read();delta=-(delta>>1) if delta&1 else delta>>1
            if kind==2:
                sr+=delta
                if sr<0 or sr+n>len(source):raise ValueError('SourceCopy overflow')
                target+=source[sr:sr+n];sr+=n
            else:
                tr+=delta
                for _ in range(n):
                    if tr<0 or tr>=len(target):raise ValueError('TargetCopy overflow')
                    target.append(target[tr]);tr+=1
    if pos!=len(patch)-12 or zlib.crc32(target)!=target_crc:raise ValueError('Target checksum mismatch')
    return bytes(target)
