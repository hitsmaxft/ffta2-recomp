# SPDX-License-Identifier: GPL-3.0-or-later
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from model_text_package import export,assemble,audit,digest
from text_catalog import FIELDS,controls

class ModelPackageTests(unittest.TestCase):
    def test_existing_chinese_source_has_explicit_two_byte_planning(self):
        catalog=self.root/'human.csv'
        with catalog.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader()
            writer.writerow(dict(id='event:0:1:0',source_sha256='fixture',source_text='甲乙\\end\\',status='review'))
        package=self.root/'human-package'
        result=export(catalog,package,source_cjk_bytes=2)
        item=json.loads((package/'model-input.jsonl').read_text().splitlines()[0])
        self.assertEqual(item['source'],'甲乙')
        self.assertEqual(item['limits']['max_encoded_bytes'],4)
        self.assertEqual(item['limits']['cjk_bytes'],2)
        self.assertFalse(result['controls_exposed_to_model'])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.catalog=self.root/'catalog.csv'
        self.source='Hello, "hero"\\varA:00\\\nCome back!\\end\\'
        with self.catalog.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n');writer.writeheader()
            writer.writerow(dict(id='event:0:1:0',rom_offset='0x100',byte_length='29',source_sha256='fixture',source_text=self.source,translation='',status='untranslated',notes=''))
        self.package=self.root/'package';export(self.catalog,self.package)
        self.manifest=self.package/'reconstruction.json';self.response=self.root/'response.jsonl'
    def answers(self,translation='你好'):
        fragments=json.loads(self.manifest.read_text())['fragments']
        return [dict(id=key,translation=translation) for key in fragments]
    def write(self,rows):
        self.response.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    def test_model_input_has_no_controls_and_roundtrip_restores_them(self):
        for line in (self.package/'model-input.jsonl').read_text().splitlines():
            item=json.loads(line);self.assertNotIn('\\',item['source']);self.assertNotIn('\n',item['source'])
        self.write(self.answers());out=self.root/'out.csv'
        result=assemble(self.catalog,self.manifest,self.response,out)
        with out.open(encoding='utf-8-sig',newline='') as stream:
            row=next(csv.DictReader(stream))
        self.assertEqual(controls(row['translation']),controls(self.source))
        self.assertEqual(row['status'],'review');self.assertFalse(result['patch_eligible'])
    def test_translation_cannot_inject_script_or_newline(self):
        for text in ['中文\\end\\','中文\n换行','隐藏\u200b字符','\x00']:
            self.write(self.answers(text))
            with self.assertRaisesRegex(ValueError,'injection'):
                assemble(self.catalog,self.manifest,self.response,self.root/'out.csv')
    def test_ids_cannot_be_omitted_duplicated_or_added(self):
        valid=self.answers()
        for rows in [valid[:-1],valid+[valid[0]],valid+[dict(id='invented',translation='中')]]:
            self.write(rows)
            with self.assertRaises(ValueError):assemble(self.catalog,self.manifest,self.response,self.root/'out.csv')
    def test_tampered_reconstruction_detected_before_import(self):
        manifest=json.loads(self.manifest.read_text());manifest['recipes'][0]['parts'][1]['protected']='\\varA:01\\'
        with self.assertRaisesRegex(ValueError,'integrity'):audit(manifest,self.catalog)
        body={k:v for k,v in manifest.items() if k!='integrity_sha256'};manifest['integrity_sha256']=digest(body)
        with self.assertRaisesRegex(ValueError,'byte identity'):audit(manifest,self.catalog)
    def test_source_catalog_identity_required(self):
        manifest=json.loads(self.manifest.read_text());self.catalog.write_bytes(self.catalog.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'catalog identity'):audit(manifest,self.catalog)

if __name__=='__main__':unittest.main()
