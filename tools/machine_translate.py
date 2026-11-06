#!/usr/bin/env python3
"""Resume validated, deduplicated catalog translation using Codex Terra."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from text_catalog import FIELDS, controls, read_rows

TOKEN = re.compile(r'\\[^\\\r\n]+\\|<unknown:[0-9A-Fa-f]+>')
MARKER = re.compile(r'⟦(\d+)⟧')
SCHEMA = {'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':{'id':{'type':'integer'},'text':{'type':'string'}},'required':['id','text'],'additionalProperties':False}}},'required':['items'],'additionalProperties':False}


def mask(text):
    tokens = []
    def replace(match):
        tokens.append(match.group())
        return f'⟦{len(tokens)-1}⟧'
    return TOKEN.sub(replace, text), tokens


def unmask(text, tokens):
    if [int(x) for x in MARKER.findall(text)] != list(range(len(tokens))):
        raise ValueError('Placeholder sequence changed')
    if '⟦' in MARKER.sub('', text) or '⟧' in MARKER.sub('', text):
        raise ValueError('Malformed placeholder')
    return MARKER.sub(lambda m: tokens[int(m.group(1))], text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--batch-size', type=int, default=24)
    p.add_argument('--batch-chars', type=int, default=3000)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if args.batch_size < 1 or args.batch_chars < 1: p.error('Batch limits must be positive')
    rows = list(read_rows(args.catalog))
    unique = list(dict.fromkeys(r['source_text'] for r in rows if r['id'].split(':')[1] == '0'))
    digest = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = args.output_dir / 'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())['catalog_sha256'] != digest:
        raise ValueError('Catalog differs from checkpoint manifest')
    manifest.write_text(json.dumps({'catalog_sha256':digest,'unique_slot0':len(unique),'model':'gpt-6.1-terra'},indent=2)+'\n')
    checkpoint = args.output_dir / 'translations.jsonl'
    completed = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding='utf-8').splitlines():
            rec = json.loads(line)
            if rec['source'] in completed and completed[rec['source']] != rec['translation']: raise ValueError('Conflicting checkpoint')
            if controls(rec['source']) != controls(rec['translation']): raise ValueError('Invalid checkpoint controls')
            completed[rec['source']] = rec['translation']
    pending = [s for s in unique if s not in completed]
    print(f'slot0 rows={sum(r["id"].split(":")[1] == "0" for r in rows)} unique={len(unique)} completed={len(completed)} pending={len(pending)}', flush=True)
    if args.dry_run: return
    with tempfile.TemporaryDirectory(prefix='ffta2-terra-') as td:
        schema = Path(td) / 'schema.json'; schema.write_text(json.dumps(SCHEMA))
        while pending:
            batch=[]; size=0
            while pending and len(batch)<args.batch_size and (not batch or size+len(pending[0])<=args.batch_chars):
                source=pending.pop(0); batch.append(source); size+=len(source)
            data=[{'id':i,'text':mask(s)[0]} for i,s in enumerate(batch)]
            prompt=('Translate every text from Final Fantasy Tactics A2 into natural concise Simplified Chinese. '
                    'Preserve all placeholders ⟦number⟧ exactly once in the same order. Do not invent placeholders. '
                    'Keep line widths short for a Nintendo DS screen. Preserve fictional names consistently. '
                    'Return all IDs in JSON. Input: '+json.dumps(data,ensure_ascii=False))
            out=Path(td)/'result.json'
            out.unlink(missing_ok=True)
            proc=subprocess.run(['/opt/homebrew/bin/codex','exec','-m','gpt-6.1-terra','--ignore-user-config','--ephemeral','--skip-git-repo-check','--output-schema',str(schema),'-o',str(out),prompt],capture_output=True,text=True)
            if proc.returncode != 0: raise RuntimeError('Terra failed: '+proc.stderr[-4000:])
            result=json.loads(out.read_text())['items']
            if sorted(x['id'] for x in result)!=list(range(len(batch))): raise ValueError('Missing or duplicate response IDs')
            verified=[]
            for item in result:
                s=batch[item['id']]; translated=unmask(item['text'],mask(s)[1])
                if not translated or controls(s)!=controls(translated) or '\0' in translated: raise ValueError('Invalid translation')
                verified.append((s,translated))
            with checkpoint.open('a',encoding='utf-8') as f:
                for s,t in verified: f.write(json.dumps({'source':s,'translation':t},ensure_ascii=False)+'\n')
                f.flush()
            completed.update(verified)
            print(f'completed={len(completed)}/{len(unique)}',flush=True)
            export(rows,completed,args.output_dir/'catalog.csv')
    export(rows,completed,args.output_dir/'catalog.csv')


def export(rows, completed, path):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,quoting=csv.QUOTE_ALL,lineterminator='\r\n');w.writeheader()
        for r in rows:
            if r['id'].split(':')[1]=='0' and r['source_text'] in completed:
                r=dict(r,translation=completed[r['source_text']],status='review',notes='Machine translated by gpt-6.1-terra; review required')
            w.writerow(r)
    tmp.replace(path)

if __name__=='__main__': main()
