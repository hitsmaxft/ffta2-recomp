# SPDX-License-Identifier: GPL-3.0-or-later
import csv,hashlib,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from text_catalog import FIELDS,import_csv
class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  self.row=dict(id='event:0:103:6',rom_offset='0x023B9096',byte_length='12',source_sha256=hashlib.sha256(b'fixture').hexdigest(),source_text='Name, "quoted"\nSecond line.\\varA:00\\\\end\\',translation='',status='untranslated',notes='')
  self.catalog=self.root/'catalog.csv';self.write(self.catalog,[self.row])
 def write(self,path,rows):
  with path.open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n');w.writeheader();w.writerows(rows)
 def translated(self,**changes):
  return dict(self.row,**dict(dict(source_text='',translation='姓名,"引号"\n第二行。\\varA:00\\\\end\\',status='translated'),**changes))
 def test_rfc4180_newlines_quotes_unicode(self):
  p=self.root/'cn.csv';self.write(p,[self.translated()]);out=import_csv(p,self.catalog)
  self.assertEqual(out['strings'][self.row['id']],'姓名,"引号"\n第二行。\\varA:00\\\\end\\')
 def test_duplicate_ids_rejected(self):
  p=self.root/'cn.csv';self.write(p,[self.translated(),self.translated()])
  with self.assertRaisesRegex(ValueError,'Duplicate text ID'):import_csv(p,self.catalog)
 def test_original_byte_identity_rejected(self):
  p=self.root/'cn.csv';self.write(p,[self.translated(source_sha256='0'*64)])
  with self.assertRaisesRegex(ValueError,'Original bytes changed'):import_csv(p,self.catalog)
 def test_variable_effect_cannot_be_removed(self):
  p=self.root/'cn.csv';self.write(p,[self.translated(translation='姓名\\end\\')])
  with self.assertRaisesRegex(ValueError,'control token mismatch'):import_csv(p,self.catalog)
if __name__=='__main__':unittest.main()
