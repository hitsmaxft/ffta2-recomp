#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download verified WenQuanYi Zen Hei and its license into a build/external folder."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

URL = 'https://downloads.sourceforge.net/project/wqy/wqy-zenhei/0.9.45%20%28Fighting-state%20RC1%29/wqy-zenhei-0.9.45.tar.gz'
SHA256 = 'e4b7e306475bf9427d1757578f0e4528930c84c44eaa3f167d4c42f110ee75d6'
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if (output == ROOT or ROOT in output.parents) and ROOT / 'build' not in output.parents:
        parser.error('Fonts belong in build/ or an external directory, never in public source')
    output.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=90) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('WenQuanYi archive hash differs')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(output, filter='data')
    font = output / 'wqy-zenhei/wqy-zenhei.ttc'
    if not font.is_file():
        raise ValueError('Font missing from verified archive')
    receipt = dict(url=URL, archive_sha256=SHA256,
                   font_sha256=hashlib.sha256(font.read_bytes()).hexdigest(),
                   license='GPL-2.0 with font embedding exception; see extracted COPYING')
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(font)


if __name__ == '__main__':
    main()
