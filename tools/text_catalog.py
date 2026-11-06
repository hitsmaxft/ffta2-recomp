#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""RFC 4180 UTF-8 CSV export/import for complete FFTA2 translation catalogs."""
import argparse,csv,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIELDS=['id','rom_offset','byte_length','source_sha256','source_text','translation','status','notes']
REQUIRED={'id','source_sha256','translation','status'}
FAMILIES={'message','event','questtext','uwasatext','freepapermes'}
ROM_SHA='f9beac8372ec07cd368265289673294d5be73af38935e9c4194f63f2e3735b59'
def read_rows(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f)
  if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):raise ValueError('Missing required CSV columns')
  if len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('Duplicate CSV column')
  seen=set()
  for row in reader:
   if None in row or any(v is None for v in row.values()):raise ValueError(f'Malformed CSV row ending at physical line {reader.line_num}')
   key=row['id'];parts=key.split(':')
   if len(parts)!=4 or parts[0] not in FAMILIES or not all(x.isdigit() for x in parts[1:]):raise ValueError('Invalid stable text ID: '+key)
   if key in seen:raise ValueError('Duplicate text ID: '+key)
   seen.add(key)
   if row['status'] not in ['untranslated','translated','review']:raise ValueError('Invalid translation status: '+key)
   yield row

def normalize_newlines(s):return s.replace('\r\n','\n').replace('\r','\n')

def controls(s):
 # Newlines are layout; every encoded script token must retain order and parameters.
 return re.findall(r'\\[^\\\r\n]+\\|<unknown:[0-9A-Fa-f]+>',s)

def import_csv(path,catalog):
 ref={row['id']:row for row in read_rows(catalog)};result={};records=[]
 for row in read_rows(path):
  key=row['id']
  if key not in ref:raise ValueError('ID absent from source catalog: '+key)
  original=ref[key]
  if row['source_sha256']!=original['source_sha256']:raise ValueError('Original bytes changed: '+key)
  for field in ['rom_offset','byte_length','source_text']:
   if row.get(field) and (normalize_newlines(row[field]) if field=='source_text' else row[field])!=(normalize_newlines(original[field]) if field=='source_text' else original[field]):raise ValueError('Source metadata mismatch: '+key+' '+field)
  if row['status']!='translated':continue
  row['translation']=normalize_newlines(row['translation'])
  if not row['translation']:raise ValueError('Empty translated field: '+key)
  if '\0' in row['translation']:raise ValueError('NUL in translation: '+key)
  if controls(row['translation'])!=controls(original['source_text']):raise ValueError('Script control token mismatch: '+key)
  result[key]=row['translation'];records.append({k:row.get(k,'') for k in FIELDS if k!='source_text'})
 return dict(schema_version=1,rom_sha256=ROM_SHA,strings=result,records=records)

def export(extraction,out):
 inv=json.loads((extraction/'rom_inventory.json').read_text())
 if inv['sha256']!=ROM_SHA:raise ValueError('Unsupported extraction revision')
 count=0
 with out.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n');w.writeheader()
  for lang in range(4):
   for family in sorted(FAMILIES):
    with (extraction/'analysis'/f'{family}_{lang}.tsv').open(encoding='utf-8',newline='') as src:
     for row in csv.DictReader(src,delimiter='\t'):
      if 'raw_hex' not in row:raise ValueError('Extraction must include raw_hex; rerun the extractor')
      raw=bytes.fromhex(row['raw_hex']);key=f'{family}:{lang}:{row["block"]}:{row["string"]}'
      w.writerow(dict(id=key,rom_offset=row['rom_offset'],byte_length=row['byte_length'],source_sha256=hashlib.sha256(raw).hexdigest(),source_text=row['text'],translation='',status='untranslated',notes=''));count+=1
 return count

def main():
 p=argparse.ArgumentParser();sp=p.add_subparsers(dest='command',required=True)
 e=sp.add_parser('export');e.add_argument('--extraction',type=Path,required=True);e.add_argument('--output',type=Path,required=True)
 i=sp.add_parser('import');i.add_argument('csv',type=Path);i.add_argument('--catalog',required=True,type=Path);i.add_argument('--output',required=True,type=Path)
 a=p.parse_args()
 if a.output.resolve()==ROOT or ROOT in a.output.resolve().parents:p.error('Private catalog outputs must stay outside source checkout')
 a.output.parent.mkdir(parents=True,exist_ok=True)
 if a.command=='export':print('Exported',export(a.extraction,a.output),'CSV rows')
 else:
  result=import_csv(a.csv,a.catalog);a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print('Imported',len(result['strings']),'translated records')
if __name__=='__main__':main()
