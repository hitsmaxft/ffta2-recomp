#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory potential CJK decoder hooks; never modifies a ROM.

Static linear disassembly includes data and speculative function boundaries. The
output is an audit aid, not proof of reachability or a safe patch location.
"""
import argparse
import bisect
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

SEEDS = {
    0x0204a95c: 'is_control', 0x0204a98c: 'control_opcode',
    0x020845f0: 'expand_glyph', 0x020846d0: 'convert_glyph',
    0x02084bc8: 'load_message_table', 0x0204aa68: 'count_glyphs',
}
EXPECTED_ROM_SHA256 = 'f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
ROW = re.compile(r'^([0-9A-Fa-f]{8}):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$')
TARGET = re.compile(r'#?0x([0-9a-f]+)', re.I)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asm', type=Path, required=True)
    p.add_argument('--extraction', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    for root in (a.asm.resolve().parent, a.extraction.resolve().parent,
                 Path(__file__).resolve().parents[1]):
        if output == root or root in output.parents:
            p.error('Analysis output must be outside input and source directories')
    inventory = json.loads((a.extraction / 'rom_inventory.json').read_text())
    if inventory.get('sha256') != EXPECTED_ROM_SHA256:
        p.error('Unsupported extraction ROM identity')
    candidates = json.loads((a.asm / 'function-candidates.json').read_text())
    modules = json.loads((a.asm / 'modules.json').read_text())
    for module in modules:
        data = (a.asm / (module['module'] + '.bin')).read_bytes()
        if hashlib.sha256(data).hexdigest() != module['sha256']:
            p.error('Module binary SHA-256 mismatch: ' + module['module'])
    bymodule = collections.defaultdict(list)
    for c in candidates:
        bymodule[c['module']].append(c['address'])
    for addresses in bymodule.values():
        addresses.sort()
    edges, loads, thumb_calls, thumb_load_counts, listing_hashes = [], [], [], {}, {}
    for module in modules:
        name = module['module']
        if name == 'arm7':
            continue
        path = a.asm / (name + '.arm.s')
        if not path.exists():
            continue
        listing_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        addresses = bymodule[name]
        for line in path.open():
            m = ROW.match(line)
            if not m:
                continue
            addr = int(m[1], 16)
            op, args = m[3], m[4]
            i = bisect.bisect_right(addresses, addr) - 1
            owner = addresses[i] if i >= 0 else None
            if op in ('bl', 'blx'):
                t = TARGET.fullmatch(args.strip())
                if t:
                    edges.append({'module': name, 'site': addr, 'candidate_owner': owner,
                                  'target': int(t[1], 16), 'instruction': line.strip()})
            if op.startswith(('ldrb', 'ldrsb')):
                loads.append({'module': name, 'site': addr, 'candidate_owner': owner,
                              'instruction': line.strip()})
        thumb_path = a.asm / (name + '.thumb.s')
        thumb_count = 0
        if thumb_path.exists():
            listing_hashes[thumb_path.name] = hashlib.sha256(thumb_path.read_bytes()).hexdigest()
            for line in thumb_path.open():
                m = ROW.match(line)
                if not m:
                    continue
                if m[3].startswith(('ldrb', 'ldrsb')):
                    thumb_count += 1
                if m[3] in ('bl', 'blx'):
                    t = TARGET.fullmatch(m[4].strip())
                    if t:
                        thumb_calls.append({'module': name, 'site': int(m[1], 16),
                                            'target': int(t[1], 16), 'instruction': line.strip()})
        thumb_load_counts[name] = thumb_count
    # Inverse direct-call closure is a conservative *candidate* inventory; ARM
    # disassembly is linear and module code/data and boundaries are unverified.
    tracked = set(SEEDS)
    for _ in range(3):
        tracked.update(e['candidate_owner'] for e in edges
                       if e['module'] == 'arm9' and e['target'] in tracked
                       and e['candidate_owner'] is not None)
    relevant_edges = [e for e in edges if e['module'] == 'arm9' and
                      (e['target'] in tracked or e['candidate_owner'] in tracked)]
    relevant_loads = [e for e in loads if e['module'] == 'arm9' and e['candidate_owner'] in tracked]
    counts = collections.Counter()
    malformed = 0
    rows = 0
    for path in sorted((a.extraction / 'analysis').glob('*_*.tsv')):
        with path.open(newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            if not reader.fieldnames or 'raw_hex' not in reader.fieldnames:
                continue
            for row in reader:
                data = bytes.fromhex(row['raw_hex']); rows += 1; pos = 0
                while pos < len(data):
                    b = data[pos]; pos += 1
                    if b >= 0xc0:
                        counts[b] += 1
                        if pos == len(data):
                            malformed += 1
                        else:
                            pos += 1
    out = {
        'schema_version': 1,
        'limitations': ['ARM and Thumb linear sweeps include non-code and exclude indirect calls',
                        'nearest candidate owner is not a proven function boundary',
                        'three inverse call levels are not a complete call graph',
                        'absence in extracted strings does not prove a control opcode unused in code or generated text'],
        'rom_sha256': inventory['sha256'],
        'input_hashes': {m['module']: m['sha256'] for m in modules},
        'listing_hashes': listing_hashes,
        'seed_functions': {hex(k): v for k, v in SEEDS.items()},
        'all_arm_direct_calls': edges,
        'all_arm_byte_loads': loads,
        'all_thumb_direct_calls': thumb_calls,
        'thumb_byte_load_counts': thumb_load_counts,
        'candidate_inverse_closure': sorted(tracked),
        'candidate_closure_calls': relevant_edges,
        'candidate_closure_byte_loads': relevant_loads,
        'control_token_counts': {f'{i:02X}': counts[i] for i in range(0xc0, 0x100)},
        'strings_scanned': rows, 'truncated_control_sequences': malformed,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({'output': str(a.output), 'sha256': hashlib.sha256(a.output.read_bytes()).hexdigest(),
                      'direct_calls': len(edges), 'byte_loads': len(loads),
                      'seed_direct_calls': {v: sum(e['target'] == k for e in edges) for k, v in SEEDS.items()},
                      'strings_scanned': rows, 'truncated_controls': malformed,
                      'unused_extracted_control_bytes': [f'{i:02X}' for i in range(0xc0, 0x100) if not counts[i]]}, indent=2))

if __name__ == '__main__':
    main()
