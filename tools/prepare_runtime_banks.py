#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate resident overlay banks only after complete ROM/live-byte equality.

Input snapshots are read_region outputs from a paused native runner, not code
obtained by scanning random memory. No staticInit table address is an entry.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

from prepare_recomp import ROOT, ROM_SHA256, coverage_entries, external_output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--captures', type=Path, required=True)
    p.add_argument('--coverage', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--recompiler', type=Path, default=ROOT / 'build/recompiler/nds_recompile')
    a = p.parse_args()
    output = external_output(a.output)
    output.mkdir(parents=True, exist_ok=True)
    rom = a.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Unsupported original ROM')
    entries = {entry for path in a.coverage for entry in coverage_entries(json.loads(path.read_bytes()))}
    mainram = (a.captures / 'mainram.bin').read_bytes()
    itcm = (a.captures / 'itcm.bin').read_bytes()
    if len(mainram) != 0x400000 or len(itcm) != 0x8000:
        raise ValueError('Unexpected captured region size')
    table, size = struct.unpack_from('<II', rom, 0x50)
    fat = struct.unpack_from('<I', rom, 0x48)[0]
    report = {'schema': 1, 'rom_sha256': ROM_SHA256, 'banks': [], 'skipped': []}
    for index in range(size // 32):
        overlay, base, length, bss, init_start, init_end, file_id, flags = struct.unpack_from('<8I', rom, table + index * 32)
        start, end = struct.unpack_from('<II', rom, fat + file_id * 8)
        binary = rom[start:end]
        if flags or len(binary) != length:
            report['skipped'].append({'overlay': overlay, 'reason': 'compressed or nonexact image'})
            continue
        live = (itcm[base & 0x7FFF:][:length] if 0x01FF8000 <= base < 0x02000000
                else mainram[base - 0x02000000:][:length] if 0x02000000 <= base < 0x02400000 else b'')
        seeds = sorted((pc, mode) for cpu, pc, mode in entries
                       if cpu == 'arm9' and base <= pc < base + length)
        if live != binary or not seeds:
            report['skipped'].append({'overlay': overlay, 'reason': 'not fully resident or no observed entry', 'observed_entries': len(seeds)})
            continue
        bank = f'ffta2_arm9_overlay_{overlay:04d}'
        paths = {ext: output / f'{bank}.{ext}' for ext in ('bin', 'toml', 'log')}
        if any(path.exists() for path in paths.values()):
            raise ValueError(f'Refusing to overwrite bank {bank}')
        paths['bin'].write_bytes(binary)
        config = (f'[program]\nname = "FFTA2 overlay {overlay}"\nid = "{bank}"\n'
                  f'load_address = 0x{base:08X}\nsize = {length}\nentry_pc = 0x{seeds[0][0]:08X}\n'
                  f'\n[identity]\nsha1 = "{hashlib.sha1(binary).hexdigest()}"\n')
        for pc, mode in seeds:
            config += f'\n[[entry_point]]\naddr = 0x{pc:08X}\nmode = "{mode}"\n'
        paths['toml'].write_text(config)
        with paths['log'].open('w') as log:
            subprocess.run([str(a.recompiler), '--config', str(paths['toml']), '--bin', str(paths['bin']),
                            '--out', str(output), '--bank', bank, '--validate-live-bytes', '--shards', '8'],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        match = re.search(r'\[finder\] functions=(\d+)', paths['log'].read_text())
        report['banks'].append({'bank': bank, 'overlay': overlay, 'load_address': base, 'size': length,
                               'rom_offset': start, 'sha256': hashlib.sha256(binary).hexdigest(),
                               'live_byte_validation': True, 'full_snapshot_match': True,
                               'observed_entries': len(seeds), 'functions': int(match[1]),
                               'static_init_used_as_entry': False})
        print(f'{bank}: {match[1]} functions; {len(seeds)} observed entries', flush=True)
    report['capture_sha256'] = {name: hashlib.sha256((a.captures / (name + '.bin')).read_bytes()).hexdigest()
                                for name in ('mainram', 'itcm')}
    (output / 'runtime-banks.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
