#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export explicitly authorized textual recovery/translation data, without ROM bytes."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from text_catalog import FIELDS, controls, read_rows


def export(catalog, mapping_paths, revised_csv, output, exclusions=None):
    rows=list(read_rows(catalog))
    excluded={}
    if exclusions:
        excluded={r['id']:r for r in (json.loads(line) for line in exclusions.read_text().splitlines())}
    candidates={}
    identities={(r['source_text'],r['source_sha256']) for r in rows if r['id'].split(':')[1]=='0'}
    for path in mapping_paths:
        for line in path.read_text(encoding='utf-8').splitlines():
            item=json.loads(line)
            source=item.get('source_text',item.get('source'))
            keys=[(source,item['source_sha256'])] if 'source_sha256' in item else [key for key in identities if key[0]==source]
            if not keys or any(key not in identities for key in keys):
                raise ValueError('Translation source absent from catalog')
            if controls(source) != controls(item['translation']) or '\0' in item['translation']:
                raise ValueError('Translation changed control tokens')
            for key in keys:
                if key in candidates and candidates[key] != item['translation']:
                    raise ValueError('Conflicting translation sources')
                candidates[key]=item['translation']
    revised={r['id']:r for r in read_rows(revised_csv)} if revised_csv else {}
    output.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(catalog,output/'catalog.csv')
    translated=review=untranslated=0
    with (output/'machine-cn.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
        writer.writeheader()
        for row in rows:
            if row['id'].split(':')[1] != '0':
                continue
            row=dict(row)
            key=(row['source_text'],row['source_sha256'])
            if key in candidates:
                row.update(translation=candidates[key],status='review',notes='Terra draft; encoding, capacity and runtime gates pending')
            update=revised.get(row['id'])
            if update and update['translation']:
                if update['source_sha256'] != row['source_sha256'] or controls(update['translation']) != controls(row['source_text']):
                    raise ValueError('Revised translation source/control mismatch')
                row.update({k:update[k] for k in ('translation','status','notes')})
            if row['id'] in excluded:
                if excluded[row['id']]['source_sha256']!=row['source_sha256']:
                    raise ValueError('Naming exclusion source identity differs')
                row.update(translation='',status='untranslated',notes='Excluded naming screen; preserve original')
            translated+=row['status']=='translated'
            review+=row['status']=='review'
            untranslated+=row['status']=='untranslated'
            writer.writerow(row)
    manifest=dict(schema_version=1,catalog_rows=len(rows),language_slot=0,
                  slot0_rows=translated+review+untranslated,planned_accepted_rows=translated,
                  review_rows=review,untranslated_rows=untranslated,full_translation=False,
                  runtime_cjk_encoding_verified=False,excluded_naming_rows=len(excluded),
                  files={name:dict(sha256=hashlib.sha256((output/name).read_bytes()).hexdigest(),bytes=(output/name).stat().st_size)
                         for name in ('catalog.csv','machine-cn.csv')})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',required=True,type=Path)
    p.add_argument('--mapping',action='append',default=[],type=Path)
    p.add_argument('--revised-csv',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--exclude-ids',type=Path)
    a=p.parse_args()
    print(json.dumps(export(a.catalog,a.mapping,a.revised_csv,a.output,a.exclude_ids),indent=2))

if __name__=='__main__':main()
