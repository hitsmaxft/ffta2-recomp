# SPDX-License-Identifier: GPL-3.0-or-later
"""Region-specific archive lookup; byte tokens shared by both output backends."""
from build_cn_patch import Archive, u16, u32
from text_resources import PATHS, block_slot

def slots(raw, language=0):
    arc = Archive(raw)
    for family, (ip, pp, single) in PATHS.items():
        idx, _ = arc.read(ip.format(lang=language))
        pak, entry = arc.read(pp.format(lang=language))
        if len(idx) < 10 or u32(idx) != 0 or any(idx[4+((len(idx)-4)//6)*6:]):
            raise ValueError('Malformed index: '+family)
        for block in range((len(idx)-4)//6-1):
            v = u32(idx, 4+6*block)
            start = ((v & 0x7ffffff) >> 3)*4
            end = ((u32(idx, 10+6*block) & 0x7ffffff) >> 3)*4
            if v & 7 or start == end:
                continue
            count = 1 if single else u16(pak, start)
            for sid in range(count):
                key = f'{family}:{language}:{block}:{sid}'
                yield block_slot(idx, pak, entry['offset'], key, block, sid, single)



def tokens(data):
    result = []
    pos = 0
    while pos < len(data):
        code = data[pos]
        width = 2 if code >= 0xa9 else 1
        if pos+width > len(data):
            raise ValueError('Truncated USA text token')
        token = data[pos:pos+width]
        if code:
            result.append(token)
        pos += width
    return result


def repair_terminal_padding(data):
    """Move only NUL gaps before final C1/C2 controls to the allocation's end."""
    pos = 0
    saw_gap = False
    result = bytearray()
    while pos < len(data):
        code = data[pos]
        if not code:
            saw_gap = True
            pos += 1
            continue
        width = 2 if code >= 0xa9 else 1
        if pos+width > len(data):
            raise ValueError('Truncated USA text token')
        if saw_gap and code not in (0xc1, 0xc2):
            raise ValueError('Nonterminal data after NUL requires manual review')
        result.extend(data[pos:pos+width])
        pos += width
    result.extend(bytes(len(data)-len(result)))
    if tokens(data) != tokens(result):
        raise AssertionError('Terminal padding repair altered tokens')
    return bytes(result)
