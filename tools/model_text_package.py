#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model-facing pure-text JSONL with detached, audited control reconstruction."""
import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from text_catalog import FIELDS, controls, normalize_newlines, read_rows
from validate_translation import RetailCodec

ROOT=Path(__file__).resolve().parents[1]
SPLIT=re.compile(r'(\\[^\\\r\n]+\\|<[^>\r\n]+>|\n)')
PROMPT='''Translate the provided Final Fantasy Tactics A2 pure-text fragments into concise Simplified Chinese.
CONTROL CHARACTER RULE (mandatory): Never translate, delete, add, reorder, normalize or alter control characters, placeholders, variable IDs or parameters. Report any unexpected control syntax instead of guessing. The exporter intentionally removed these from the model input: they are held in a separate immutable reconstruction manifest. You must not create or reconstruct them yourself. If any control-like text appears in source, stop and report that item.
Return JSONL only, exactly one object per input ID: {"id":"unchanged ID","translation":"pure Chinese text"}. Preserve every ID exactly once; do not add IDs or metadata. Do not include backslashes, script tokens, placeholders, newlines, tabs, zero-width characters or other Unicode control characters in translation fields. Translate only source, never IDs or numeric constraints. Keep names consistent and punctuation/spacing appropriate. Use short wording for a 12px monospaced Chinese font. Original byte budget and pixel footprint are hard upper bounds, not desired lengths. Do not claim an overlong translation fits; report it for a shorter revision.
Before translation, proofread input IDs and source: check uniqueness, missing or malformed records, unexpected control syntax and obvious extraction anomalies. Never repair an anomaly by silently changing IDs or control data. After translation, proofread all translations against source for omissions, mistranslations, terminology and excessive length, then check ID completeness and the control-character rule again. The importer independently validates the immutable manifest, source hashes, IDs, control reconstruction, byte budgets and static line layout. Failing rows are review-only and cannot enter a patch.
'''

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def codec():
    return RetailCodec(json.loads((ROOT/'config/western-charset.json').read_text()),[0]*168)

def fragment_id(source):
    return 't-'+hashlib.sha256(source.encode()).hexdigest()[:16]

def audit(manifest,catalog):
    expected=manifest.get('integrity_sha256')
    body={k:v for k,v in manifest.items() if k!='integrity_sha256'}
    if digest(body)!=expected:
        raise ValueError('Reconstruction manifest integrity differs')
    if hashlib.sha256(catalog.read_bytes()).hexdigest()!=manifest['catalog_sha256']:
        raise ValueError('Source catalog identity differs')
    refs={r['id']:r for r in read_rows(catalog) if int(r['id'].split(':')[1])==manifest['language']}
    fragments=manifest['fragments']
    for key,source in fragments.items():
        if fragment_id(source)!=key or SPLIT.search(source):
            raise ValueError('Fragment identity/control audit failed: '+key)
    seen=set()
    enc=codec()
    for row in manifest['recipes']:
        key=row['id']
        if key not in refs or key in seen or refs[key]['source_sha256']!=row['source_sha256']:
            raise ValueError('Recipe source identity/ID audit failed: '+key)
        seen.add(key)
        source=[]
        for part in row['parts']:
            if set(part)=={'text_id'}:
                source.append(fragments[part['text_id']])
            elif set(part)=={'protected','encoded_hex'}:
                if enc.token_bytes(part['protected']).hex()!=part['encoded_hex']:
                    raise ValueError('Protected token byte identity differs: '+key)
                source.append(part['protected'])
            else:
                raise ValueError('Unknown recipe part schema: '+key)
        if ''.join(source)!=normalize_newlines(refs[key]['source_text']):
            raise ValueError('Original source cannot be reconstructed: '+key)
    if seen!=set(refs):
        raise ValueError('Missing source recipes')
    return refs

def export(catalog,output,language=0,metrics=None,batch_size=128,source_cjk_bytes=None):
    enc=codec()
    if source_cjk_bytes not in (None,2,3):raise ValueError('Source CJK planning width must be 2 or 3 bytes')
    enc.extended_bytes=source_cjk_bytes
    if metrics:
        enc.widths=json.loads(metrics.read_text())['widths']
    fragments={}
    recipes=[]
    for row in read_rows(catalog):
        if int(row['id'].split(':')[1])!=language:
            continue
        parts=[]
        for piece in SPLIT.split(normalize_newlines(row['source_text'])):
            if not piece:
                continue
            if SPLIT.fullmatch(piece):
                parts.append(dict(protected=piece,encoded_hex=enc.token_bytes(piece).hex()))
            else:
                key=fragment_id(piece)
                if key in fragments and fragments[key]!=piece:
                    raise ValueError('Fragment ID collision')
                fragments[key]=piece
                parts.append(dict(text_id=key))
        recipes.append(dict(id=row['id'],source_sha256=row['source_sha256'],parts=parts))
    manifest=dict(schema_version=1,language=language,catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),fragments=fragments,recipes=recipes)
    manifest['integrity_sha256']=digest(manifest)
    audit(manifest,catalog)  # Mandatory before any model-facing export.
    output.mkdir(parents=True,exist_ok=True)
    batches=output/'batches'
    batches.mkdir(exist_ok=True)
    lines=[]
    for key,source in fragments.items():
        dimensions=enc.analyze(source)
        limits=dict(max_encoded_bytes=dimensions['encoded_bytes'],cjk_bytes=source_cjk_bytes or 3,max_lines=1,
                    max_width_px=max(dimensions['pages'][0]) if metrics else None)
        lines.append(json.dumps(dict(id=key,source=source,translation='',limits=limits),ensure_ascii=False)+'\n')
    (output/'model-input.jsonl').write_text(''.join(lines))
    for start in range(0,len(lines),batch_size):
        (batches/f'part-{start//batch_size+1:04d}.jsonl').write_text(''.join(lines[start:start+batch_size]))
    (output/'reconstruction.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (output/'PROMPT.txt').write_text(PROMPT)
    report=dict(source_rows=len(recipes),unique_text_fragments=len(fragments),pre_translation_audit='passed',controls_exposed_to_model=False,source_cjk_planning_bytes=source_cjk_bytes,manifest_sha256=manifest['integrity_sha256'])
    (output/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def assemble(catalog,manifest_path,response,output,allow_partial=False):
    manifest=json.loads(manifest_path.read_text())
    refs=audit(manifest,catalog)
    translations={}
    for line in response.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        item=json.loads(line)
        if set(item)!={'id','translation'}:
            raise ValueError('Response must contain only id and translation')
        key=item['id'];text=item['translation']
        if not isinstance(key,str) or key not in manifest['fragments'] or key in translations:
            raise ValueError('Unknown or duplicate response ID')
        if not isinstance(text,str) or not text:
            raise ValueError('Missing translation: '+key)
        if '\\' in text or SPLIT.search(text) or any(unicodedata.category(c).startswith('C') for c in text):
            raise ValueError('Control/newline/placeholder injection in translation: '+key)
        translations[key]=text
    missing=set(manifest['fragments'])-set(translations)
    if missing and not allow_partial:
        raise ValueError(f'Missing {len(missing)} translation IDs; partial imports require --allow-partial')
    recipes={r['id']:r for r in manifest['recipes']}
    reviewed=0
    with output.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
        writer.writeheader()
        for key,row in refs.items():
            parts=recipes[key]['parts']
            if any('text_id' in part and part['text_id'] not in translations for part in parts):
                writer.writerow(row)
                continue
            text=''.join(translations[part['text_id']] if 'text_id' in part else part['protected'] for part in parts)
            if controls(text)!=controls(row['source_text']):
                raise ValueError('Reconstructed controls differ: '+key)
            if text:
                row=dict(row,translation=text,status='review',notes='Detached controls restored exactly; length/layout and proofreading acceptance pending')
                reviewed+=1
            writer.writerow(row)
    return dict(reconstructed_rows=reviewed,missing_fragments=len(missing),status='review',patch_eligible=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('export');e.add_argument('--language',type=int,choices=range(4),default=0);e.add_argument('--metrics',type=Path);e.add_argument('--batch-size',type=int,default=128);e.add_argument('--source-cjk-bytes',type=int,choices=[2,3],help='Planning only: accept an existing Chinese source catalog')
    i=sub.add_parser('import');i.add_argument('--manifest',required=True,type=Path);i.add_argument('--response',required=True,type=Path);i.add_argument('--allow-partial',action='store_true')
    for command in (e,i):
        command.add_argument('--catalog',required=True,type=Path);command.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.resolve()==a.catalog.resolve() or (a.command=='import' and a.output.resolve() in (a.manifest.resolve(),a.response.resolve())):
        p.error('Output must not overwrite an input')
    if a.command=='export' and a.batch_size<1:p.error('Batch size must be positive')
    if a.command=='export':result=export(a.catalog,a.output,a.language,a.metrics,a.batch_size,a.source_cjk_bytes)
    else:result=assemble(a.catalog,a.manifest,a.response,a.output,a.allow_partial)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
