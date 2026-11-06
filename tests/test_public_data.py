# SPDX-License-Identifier: GPL-3.0-or-later
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PublicDataTests(unittest.TestCase):
    def test_public_snapshots_match_manifest_and_status_counts(self):
        directory=ROOT/'data/text'
        manifest=json.loads((directory/'manifest.json').read_text())
        for name, identity in manifest['files'].items():
            payload=(directory/name).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(),identity['sha256'])
            self.assertEqual(len(payload),identity['bytes'])
        with (directory/'machine-cn.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),manifest['slot0_rows'])
        self.assertEqual(len(set(r['id'] for r in rows)),len(rows))
        self.assertTrue(all(r['id'].split(':')[1]=='0' for r in rows))
        for status,field in [('translated','planned_accepted_rows'),('review','review_rows'),('untranslated','untranslated_rows')]:
            self.assertEqual(sum(r['status']==status for r in rows),manifest[field])
        self.assertFalse(manifest['full_translation'])
        self.assertFalse(manifest['runtime_cjk_encoding_verified'])

if __name__=='__main__':unittest.main()
