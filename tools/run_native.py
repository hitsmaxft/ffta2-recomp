#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch the native backend using an unchanged original ROM and external data."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess

ROM_SHA256 = 'f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--localization', type=Path)
    p.add_argument('--binary', type=Path, default=ROOT / 'build/macos/backend/ffta2-recomp')
    p.add_argument('--serve', action='store_true', help='Headless diagnostic server instead of SDL window')
    p.add_argument('--port', type=int, default=19979)
    p.add_argument('--save', type=Path, help='Explicit external test save; defaults to no save writes')
    a = p.parse_args()
    rom = a.rom.resolve(strict=True)
    with rom.open('rb') as stream:
        identity = hashlib.file_digest(stream, 'sha256').hexdigest()
    if identity != ROM_SHA256:
        p.error('Expected unchanged European A6FP revision-0 ROM; patched ROMs are rejected')
    session = a.session.resolve()
    if session == ROOT or ROOT in session.parents:
        p.error('Session data must stay outside the repository')
    if not 1024 <= a.port <= 65535:
        p.error('Port must be 1024..65535')
    binary = a.binary.resolve(strict=True)
    command = [str(binary), '--serve' if a.serve else '--interactive', '--port', str(a.port),
               '--rom', str(rom), '--freebios', '--boot', 'direct', '--generated-firmware',
               '--firmware-state-path', str(session / 'firmware.bin'), '--network', 'off',
               '--diagnostics', 'on', '--diagnostics-dir', str(session / 'diagnostics'),
               '--coverage-manifest', str(session / 'coverage.json')]
    if a.localization:
        command += ['--localization', str(a.localization.resolve(strict=True))]
    if a.save:
        save = a.save.resolve()
        if save == rom or save == ROOT or ROOT in save.parents:
            p.error('Save must be an explicit external path, separate from the ROM')
        command += ['--save-path', str(save)]
    else:
        command += ['--no-save']
    session.mkdir(parents=True, exist_ok=True)
    print('Original ROM SHA256:', identity, flush=True)
    print('Runtime session:', session, flush=True)
    # Upstream's generated identity file is relative to its working directory.
    # Keep it with session data, never next to source or the input ROM.
    os.chdir(session)
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
