#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch the native backend using an unchanged original ROM and external data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROM_SHA256 = 'f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
ROOT = Path(__file__).resolve().parents[1]


def default_binary():
    if os.name != 'nt':
        return ROOT / 'build/macos/backend/ffta2-recomp'
    directory = ROOT / 'build/windows-x64/backend'
    release = directory / 'Release/ffta2-recomp.exe'
    return release if release.is_file() else directory / 'ffta2-recomp.exe'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--localization', type=Path)
    p.add_argument('--binary', type=Path, default=default_binary())
    p.add_argument('--serve', action='store_true', help='Headless diagnostic server instead of SDL window')
    p.add_argument('--port', type=int, default=19979)
    p.add_argument('--savestate-dir', type=Path, help='External instant-save root; defaults to session/states')
    p.add_argument('--save', type=Path, help='Explicit external test save; defaults to no save writes')
    p.add_argument('--title-assets', type=Path, help='External exact-match title texture package')
    p.add_argument('--bitmap-fallback', action=argparse.BooleanOptionalAction, default=True,
                   help='Use palette-aware bitmap Chinese for menu widgets without verified HD layout')
    p.add_argument('--font', choices=('pixel','system'), default='system')
    p.add_argument('--window-scale', type=int, choices=range(1,9), default=3)
    p.add_argument('--lcd', type=float, default=0, help='LCD pixel grid strength, 0..1')
    p.add_argument('--lcd-text', action='store_true', help='Apply LCD grid to native text too')
    a = p.parse_args()
    if not 0 <= a.lcd <= 1: p.error('--lcd must be 0..1')
    if a.title_assets:
        os.environ['FFTA2_TITLE_ASSETS'] = str(a.title_assets.resolve(strict=True))
    os.environ['FFTA2_FONT'] = a.font
    os.environ['FFTA2_BITMAP_FALLBACK'] = '1' if a.bitmap_fallback else '0'
    os.environ['FFTA2_WINDOW_SCALE'] = str(a.window_scale)
    os.environ['FFTA2_LCD'] = str(a.lcd)
    os.environ['FFTA2_LCD_TEXT'] = '1' if a.lcd_text else '0'
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
    states = (a.savestate_dir or session / 'states').resolve()
    if states == ROOT or ROOT in states.parents or states == rom:
        p.error('Instant saves must stay outside the repository and ROM')
    binary = a.binary.resolve(strict=True)
    command = [str(binary), '--serve' if a.serve else '--interactive', '--port', str(a.port),
               '--rom', str(rom), '--freebios', '--boot', 'direct', '--generated-firmware',
               '--firmware-state-path', str(session / 'firmware.bin'), '--network', 'off',
               '--savestate-dir', str(states), '--diagnostics', 'on', '--diagnostics-dir', str(session / 'diagnostics'),
               '--coverage-manifest', str(session / 'coverage.json')]
    settings_path = session / 'localization.json'
    localization = a.localization
    if localization is None and settings_path.exists():
        settings = json.loads(settings_path.read_text())
        localization = Path(settings['directory'])
    if localization is None:
        candidate = rom.parent / 'native-localization'
        if (candidate / 'manifest.json').is_file():
            localization = candidate
    if localization:
        localization = localization.resolve(strict=True)
        command += ['--localization', str(localization)]
        session.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({'directory': str(localization)}, indent=2) + '\n')
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
