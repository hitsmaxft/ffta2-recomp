#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare ROM-pinned, byte-validated native main-code banks outside checkout."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA256 = 'f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
ROM_SHA1 = '09a4a90eb05d187e7cd896497866d58da36353b0'
MODULES = {
    'arm9': (0x20, 'c6d7818ec4528be8c31d2cc74de55d31cf070141'),
    'arm7': (0x30, '1aea109daeacd0165e068813f10df804a4e20f0a'),
}


def external_output(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Generated guest code and binary assets must stay outside checkout')
    return path


def integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def coverage_entries(doc):
    """Accept native runner tier3_coverage or identity-bearing coverage manifests."""
    if doc.get('rom_sha1', ROM_SHA1) != ROM_SHA1:
        raise ValueError('Coverage ROM identity does not match the supported ROM')
    if 'entries' in doc:
        for row in doc['entries']:
            cpu = integer(row['cpu'])
            if cpu not in (7, 9) or integer(row['thumb']) not in (0, 1):
                raise ValueError('Invalid coverage CPU or instruction mode')
            yield f'arm{cpu}', integer(row['pc']), 'thumb' if integer(row['thumb']) else 'arm'
    else:
        if not any(f'entry_points_{cpu}' in doc for cpu in MODULES):
            raise ValueError('Coverage document contains no supported entry arrays')
        for cpu in MODULES:
            for row in doc.get(f'entry_points_{cpu}', []):
                if row['mode'] not in ('arm', 'thumb'):
                    raise ValueError('Invalid coverage instruction mode')
                yield cpu, integer(row['addr']), row['mode']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--recompiler', type=Path, default=ROOT / 'build/recompiler/nds_recompile')
    parser.add_argument('--coverage', type=Path, action='append', default=[])
    parser.add_argument('--runtime-captures', type=Path,
                        help='Read-only debug read_region snapshots: mainram/itcm/wramshared/wram7.bin')
    parser.add_argument('--shards', type=int, choices=(8, 16), default=8)
    args = parser.parse_args()
    output = external_output(args.output)
    rom = args.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Unsupported ROM; expected original European A6FP revision 0')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty; preserve earlier bank generations in separate directories')
    recompiler = args.recompiler.resolve(strict=True)
    coverage = []
    coverage_inputs = []
    for path in args.coverage:
        raw = path.read_bytes()
        coverage.extend(coverage_entries(json.loads(raw)))
        coverage_inputs.append({'sha256': hashlib.sha256(raw).hexdigest(), 'name': path.name})
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'schema': 1, 'kind': 'ffta2-native-bank-preparation',
               'rom_sha256': ROM_SHA256, 'rom_sha1': ROM_SHA1,
               'recompiler_sha256': hashlib.sha256(recompiler.read_bytes()).hexdigest(),
               'coverage_inputs': coverage_inputs, 'modules': [],
               'overlay_policy': 'Not generated: staticInitStart is an array, not a function entry',
               'execution_verified': False}
    if args.runtime_captures:
        receipt['capture_sha256'] = {name: hashlib.sha256(
            (args.runtime_captures / f'{name}.bin').read_bytes()).hexdigest()
            for name in ('mainram', 'itcm', 'wramshared', 'wram7')}
    for cpu, (header, expected_sha1) in MODULES.items():
        offset, entry, base, size = struct.unpack_from('<4I', rom, header)
        binary = rom[offset:offset + size]
        sha1 = hashlib.sha1(binary).hexdigest()
        if sha1 != expected_sha1:
            raise ValueError(f'{cpu} image identity mismatch; compressed images are not accepted')
        seeds, skipped = set(), []
        # Pinned SDK startup: LDR r1,[PC,#0x30] at 0x02000914 loads
        # literal 0x02000BDC at 0x0200094C; BX r1 at 0x0200092C enters
        # application main. The finder currently misses this known transfer.
        if cpu == 'arm9':
            if (struct.unpack_from('<I', binary, 0x914)[0] != 0xE59F1030 or
                    struct.unpack_from('<I', binary, 0x92C)[0] != 0xE12FFF11 or
                    struct.unpack_from('<I', binary, 0x94C)[0] != 0x02000BDC):
                raise ValueError('Pinned ARM9 SDK application-main transfer changed')
            seeds.add((0x02000BDC, 'arm'))
        # Relocated SDK code is executable at its runtime address, never at a
        # fabricated ROM offset. These pinned mappings are verified against a
        # stopped runner's read-only region snapshots when supplied.
        copies = ([(0x01FF8000, 0x0211E8E0, 0x2D20, 'itcm')]
                  if cpu == 'arm9' else
                  [(0x037F8000, 0x023801E8, 0xF28C, 'arm7_wram_code'),
                   (0x027E0000, 0x0238F56C, 0x17855, 'mainram')])
        validated_copies = []
        if args.runtime_captures:
            captured = {name: (args.runtime_captures / f'{name}.bin').read_bytes()
                        for name in ('mainram', 'itcm', 'wramshared', 'wram7')}
            expected_sizes = {'mainram': 0x400000, 'itcm': 0x8000,
                              'wramshared': 0x8000, 'wram7': 0x10000}
            if any(len(captured[name]) != length for name, length in expected_sizes.items()):
                raise ValueError('Unexpected runtime captured region size')
            for runtime, source, length, name in copies:
                original = binary[source - base:source - base + length]
                if name == 'itcm':
                    live = captured['itcm'][runtime & 0x7FFF:][:length]
                elif name == 'mainram':
                    live = captured['mainram'][runtime & 0x3FFFFF:][:length]
                else:
                    live = (captured['wramshared'] + captured['wram7'])[:length]
                if live != original:
                    raise ValueError(f'Live copy mismatch {cpu} {name} at 0x{runtime:08X}')
                validated_copies.append({'runtime_start': runtime, 'source_start': source,
                                         'rom_offset': offset + source - base, 'size': length,
                                         'sha256': hashlib.sha256(original).hexdigest()})
        for seed_cpu, pc, mode in coverage:
            if seed_cpu != cpu:
                continue
            alignment = 2 if mode == 'thumb' else 4
            if pc % alignment:
                raise ValueError(f'Misaligned coverage entry {cpu}:0x{pc:08X}/{mode}')
            mapped = (args.runtime_captures and any(runtime <= pc <= runtime + length - alignment
                      for runtime, source, length, name in copies))
            if not (base <= pc <= base + size - alignment or mapped):
                skipped.append({'address': pc, 'mode': mode, 'reason': 'outside original main image'})
                continue
            seeds.add((pc, mode))
        bank = f'ffta2_{cpu}_main'
        binary_path = output / f'{cpu}.bin'
        config_path = output / f'{cpu}.toml'
        binary_path.write_bytes(binary)
        config = (f'[program]\nname = "FFTA2 Europe {cpu.upper()}"\nid = "{bank}"\n'
                  f'load_address = 0x{base:08X}\nsize = {size}\nentry_pc = 0x{entry:08X}\n\n'
                  f'[identity]\nsha1 = "{sha1}"\n')
        if args.runtime_captures:
            for runtime, source, length, name in copies:
                config += (f'\n[[code_copy]]\nruntime_start = 0x{runtime:08X}\n'
                           f'source_start = 0x{source:08X}\nsize = {length}\nname = "{name}"\n')
        for pc, mode in sorted(seeds):
            config += f'\n[[entry_point]]\naddr = 0x{pc:08X}\nmode = "{mode}"\n'
        config_path.write_text(config, encoding='utf-8')
        command = [str(recompiler), '--config', str(config_path), '--bin', str(binary_path),
                   '--out', str(output), '--bank', bank, '--validate-live-bytes',
                   '--shards', str(args.shards)]
        log_path = output / f'{cpu}-generation.log'
        with log_path.open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        text = log_path.read_text()
        counts = re.search(r'\[finder\] functions=(\d+) \(arm=(\d+) thumb=(\d+)\)', text)
        if result.returncode or not counts:
            raise RuntimeError(f'{cpu} generation failed (exit {result.returncode}); inspect {log_path}')
        receipt['modules'].append({'cpu': cpu, 'bank': bank, 'rom_offset': offset,
                                   'load_address': base, 'entry': entry, 'size': size,
                                   'sha1': sha1, 'sha256': hashlib.sha256(binary).hexdigest(),
                                   'functions': int(counts[1]), 'arm_functions': int(counts[2]),
                                   'thumb_functions': int(counts[3]),
                                   'explicit_entry_seeds': len(seeds), 'validated_runtime_copies': validated_copies,
                                   'sdk_main_entry': 0x02000BDC if cpu == 'arm9' else None,
                                   'skipped_coverage': skipped, 'live_byte_validation': True})
        print(f'{cpu}: {counts[1]} functions, source image {size} bytes', flush=True)
    receipt['files'] = [{'name': p.name, 'size': p.stat().st_size,
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in sorted(output.iterdir()) if p.is_file()]
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Generated {sum(x["size"] for x in receipt["files"]):,} bytes in {output}')


if __name__ == '__main__':
    main()
