"""Normalize FATURA labels for local review; preserve original data and splits.

No OCR/training or legal validation. Ambiguous values remain NOT_ANNOTATED;
source candidates and geometry diagnostics are retained in a local sidecar.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'agent3_tax_compliance/configs/datasets/fatura_mapping_v1.json'
CFG=json.loads(CONFIG.read_text(encoding='utf-8'))
SOURCE=ROOT/CFG['source_root']
OUT=ROOT/CFG['output_root']
REPORT=ROOT/'docs/agent3/plans/evidence/plan00/fatura_mapping_summary.json'
FIELDS=[*CFG['aliases'],'currency','seller.tax_id','buyer.tax_id','vat_category','items']
ISO_CURRENCY=re.compile(r'\b(USD|EUR|INR|GBP|AUD|CAD|VND|CNY|JPY|CHF|NZD)\b')


def hash_file(path):
    h=sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def rel(path):return path.resolve().relative_to(ROOT).as_posix()


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def rank(value):return sha256(f"{CFG['seed']}:{value}".encode()).hexdigest()


def split_groups():
    exposed=set(CFG['previously_inspected_templates'])
    sizes=CFG['template_split_counts']
    if sum(sizes.values())!=50 or sizes['dev']<len(exposed):raise ValueError('Invalid split sizes')
    ordered=sorted(set(range(1,51))-exposed,key=rank)
    dev=sorted(exposed)+ordered[:sizes['dev']-len(exposed)]
    remaining=[t for t in ordered if t not in dev]
    return {'dev':sorted(dev),'calibration':sorted(remaining[:sizes['calibration']]),'test':sorted(remaining[sizes['calibration']:])}


def normalize_date(raw):
    value=re.sub(r'^(?:invoice\s*)?date\s*[:#]?\s*','',raw.strip(),flags=re.I)
    values=set()
    for fmt in ['%d-%b-%Y','%d/%b/%Y','%d %b %Y','%Y-%m-%d','%Y/%m/%d','%d-%B-%Y','%B %d, %Y']:
        try:values.add(datetime.strptime(value,fmt).date().isoformat())
        except ValueError:pass
    # Numeric local dates are accepted only if the order is unambiguous.
    m=re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',value)
    if m:
        a,b,y=map(int,m.groups())
        for month,day in [(a,b),(b,a)]:
            try:values.add(datetime(y,month,day).date().isoformat())
            except ValueError:pass
    return next(iter(values)) if len(values)==1 else None


def normalize_money(raw):
    # Reject unsupported grouping; do not choose the largest of several amounts.
    cleaned=re.sub(r'[-+]?\d+(?:[.,]\d+)?\s*%','',raw)
    tokens=re.findall(r'(?<![\w])[-+]?\d[\d.,]*(?![\w])',cleaned)
    values=[]
    for token in tokens:
        if re.fullmatch(r'[-+]?\d+(?:\.\d{1,2})?',token):number=token
        elif re.fullmatch(r'[-+]?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?',token):number=token.replace(',','')
        elif re.fullmatch(r'[-+]?\d+,\d{1,2}',token):number=token.replace(',','.')
        elif re.fullmatch(r'[-+]?\d{1,3}(?:\.\d{3})+,\d{1,2}',token):number=token.replace('.','').replace(',','.')
        else:return None
        try:
            value=Decimal(number)
            if value.is_finite():values.append(format(value,'f'))
        except InvalidOperation:return None
    return values[0] if len(values)==1 else None


def normalize_value(field,key,raw):
    raw=raw.strip()
    if field=='seller.name':return raw if '\n' not in raw else None
    if field=='buyer.name':
        text=re.sub(r'^(?:bill[ _]*to|buyer)\s*:?\s*','',raw,flags=re.I)
        first=text.splitlines()[0].strip() if text else ''
        return first or None
    if field=='invoice.issue_date':return normalize_date(raw)
    if field=='invoice.number':
        value=re.sub(r'^(?:invoice\s*(?:number|num\.?|no\.?|id|#)?|number|no\.?|id)\s*[:#]?\s*','',raw,flags=re.I).strip()
        return value if value and '\n' not in value else None
    if field=='totals.vat' and not re.search(r'\bVAT\b',raw,flags=re.I):return None
    if field.startswith('totals.'):return normalize_money(raw)
    return None


def transform_bbox(raw,width,height,hf_boxes):
    box=raw.get('bbox')
    if not isinstance(box,list) or len(box)!=2 or any(not isinstance(p,list) or len(p)!=2 for p in box):
        return None,'NO_SUPPORTED_BBOX'
    (ax,ay),(bx,by)=box
    if any(not isinstance(v,(int,float)) for v in [ax,ay,bx,by]):return None,'NON_NUMERIC_BBOX'
    x0,x1=sorted([ax,bx]);low,high=sorted([ay,by]);y0,y1=height-high,height-low
    pixel=[x0,y0,x1,y1]
    if not (0<=x0<x1<=width and 0<=y0<y1<=height):return None,'OUT_OF_BOUNDS_BBOX'
    distance=min((max(abs(a-b) for a,b in zip(pixel,b)) for b in hf_boxes if len(b)==4),default=float('inf'))
    if distance>CFG['geometry_tolerance_px']:return None,'HF_GEOMETRY_MISMATCH'
    return [x0/width,y0/height,x1/width,y1/height],'HF_GEOMETRY_CONFIRMED'


def map_annotation(original,hf,width,height,docid):
    fields=[];proposals=[];issues=Counter()
    for field in FIELDS:
        candidates=[]
        keys=CFG['aliases'].get(field,[])
        if field=='currency':keys=['TOTAL','SUB_TOTAL','TAX','AMOUNT_DUE']
        for key in keys:
            obj=original.get(key)
            if not isinstance(obj,dict) or not isinstance(obj.get('text'),str) or not obj['text'].strip():continue
            raw=obj['text'];box,geometry=transform_bbox(obj,width,height,hf['bboxes'])
            value=normalize_value(field,key,raw) if field!='currency' else None
            if field=='currency':
                codes=set(ISO_CURRENCY.findall(raw))
                value=next(iter(codes)) if len(codes)==1 else None
            candidates.append({'source_key':key,'raw_text':raw,'normalized_value':value,
                               'original_bbox':obj.get('bbox'),'mapped_bbox':box,'geometry_status':geometry})
        proposals.append({'field_path':field,'candidates':candidates})
        usable=[c for c in candidates if c['normalized_value'] is not None and c['mapped_bbox'] is not None]
        # An unresolved alias is not silently ignored in favour of a usable candidate.
        if candidates and len(usable)==len(candidates) and len({c['normalized_value'] for c in usable})==1:
            selected=usable[0]
            fields.append({'field_path':field,'status':'OBSERVED','raw_text':selected['raw_text'],
                           'normalized_value':selected['normalized_value'],
                           'evidence':[{'page_index':0,'bbox':selected['mapped_bbox']}]})
        else:
            reason='NO_SUPPORTED_SEMANTIC_LABEL' if not candidates else 'NORMALIZATION_OR_GEOMETRY_UNRESOLVED'
            if field in ['seller.tax_id','buyer.tax_id']:reason='GSTIN_NOT_VIETNAMESE_TAX_ID'
            if field=='items':reason='TABLE_REGION_ONLY_NO_VERIFIED_ROW_LABELS'
            if field=='vat_category':reason='NO_INDEPENDENT_LEGAL_TAXONOMY_EVIDENCE'
            fields.append({'field_path':field,'status':'NOT_ANNOTATED','raw_text':None,'normalized_value':None,'reason':reason,'evidence':[]})
            issues[reason]+=1
        for c in candidates:
            if c['geometry_status']!='HF_GEOMETRY_CONFIRMED':issues[c['geometry_status']]+=1
    return {'schema_version':'1.0.0','annotation_version':CFG['dataset_version'],'document_id':docid,
            'origin':'SYNTHETIC','review_status':'SECOND_REVIEW_PENDING','page_count':1,'fields':fields},proposals,issues


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    groups=split_groups();which={t:s for s,ts in groups.items() for t in ts}
    pilot_templates=sorted(groups['dev'],key=lambda t:rank(f'pilot:{t}'))[:CFG['pilot_templates']]
    pilot_keys={(t,i) for t in pilot_templates for i in CFG['pilot_instances']}
    hf_index={re.match(r'(Template\d+_Instance\d+)',p.name)[1]:p for p in (SOURCE/'Annotations/layoutlm_HF_format').glob('*.json')}
    coverage=Counter();issues=Counter();manifest=[];pilot=[];hash_groups=defaultdict(list)
    source_hashes={};hf_invalid=0
    with (OUT/'provenance.jsonl').open('w',encoding='utf-8') as provenance:
        for n,p in enumerate(sorted((SOURCE/'Annotations/Original_Format').glob('*.json'))):
            match=re.fullmatch(r'Template(\d+)_Instance(\d+)',p.stem)
            if not match:raise ValueError(f'Unknown document name {p.name}')
            template,instance=map(int,match.groups());split=which[template]
            original=json.loads(p.read_text(encoding='utf-8'))
            hf=json.loads(hf_index[p.stem].read_text(encoding='utf-8'))
            if not len(hf['words'])==len(hf['ner_tags'])==len(hf['bboxes']):
                hf_invalid+=1;raise ValueError(f'HF array lengths mismatch: {p.stem}')
            with Image.open(SOURCE/'images'/f'{p.stem}.jpg') as im:width,height=im.size
            logical=f'fatura-T{template:02}-I{instance:03}'
            ann,proposals,problems=map_annotation(original,hf,width,height,logical)
            issues.update(problems)
            for field in ann['fields']:coverage[(split,field['field_path'],field['status'])]+=1
            source_hashes[logical]={'original':hash_file(p),'hf':hash_file(hf_index[p.stem])}
            provenance.write(json.dumps({'document_id':logical,'source_annotations':{'original':rel(p),'hf':rel(hf_index[p.stem])},
                                         'source_hashes':source_hashes[logical],'original_size':[width,height],
                                         'coordinate_transform':'[min(x)/W, (H-max(y))/H, max(x)/W, (H-min(y))/H]',
                                         'proposals':proposals,'unmapped_keys':sorted(set(original)-set(k for v in CFG['aliases'].values() for k in v))},ensure_ascii=False)+'\n')
            variants=[]
            for variant in ['images','colored_images']:
                image_path=SOURCE/variant/f'{p.stem}.jpg'
                with Image.open(image_path) as im:
                    if im.size!=(width,height):raise ValueError('Variant geometry differs')
                docid=logical+('-white' if variant=='images' else '-colored')
                variant_ann={**ann,'document_id':docid}
                ann_path=OUT/'annotations'/f'{docid}.json';dump(ann_path,variant_ann)
                image_hash=hash_file(image_path);hash_groups[image_hash].append((logical,split))
                row={'schema_version':'1.0.0','dataset_id':'fatura_v2_mapped','version':CFG['dataset_version'],
                     'document_id':docid,'sha256':image_hash,'path':rel(image_path),'document_family':'SYNTHETIC_INVOICE',
                     'source_kind':'IMAGE','page_count':1,'permission_basis':CFG['permission_basis'],'split':split,
                     'template_group':f'fatura-template-{template:02}','duplicate_family':logical,
                     'label_coverage':[f['field_path'] for f in ann['fields'] if f['status']=='OBSERVED'],
                     'annotation_version':CFG['dataset_version'],'annotation_path':rel(ann_path),'origin':'SYNTHETIC',
                     'accuracy_evaluation_eligible':False,'limitations':['INTERNATIONAL_SYNTHETIC','TERMS_NOT_CONFIRMED','SECOND_REVIEW_PENDING','ITEM_ROW_LABELS_UNVERIFIED']}
                manifest.append(row);variants.append(row)
            if (template,instance) in pilot_keys:
                pilot.append({'logical_document_id':logical,'template':template,'instance':instance,'split':'dev',
                              'white_path':variants[0]['path'],'colored_path':variants[1]['path'],
                              'annotation_path':variants[0]['annotation_path'],'source_annotation_path':rel(p),
                              'automated_geometry':'PASS_FOR_OBSERVED_FIELDS','independent_review':'PENDING'})
            if (n+1)%2000==0:print(f'Mapped {n+1} logical invoices',flush=True)
    duplicate_cross=[v for v in hash_groups.values() if len({s for _,s in v})>1]
    if duplicate_cross:raise ValueError('Exact image duplicate crosses template split; regroup before release')
    manifest.sort(key=lambda x:x['document_id']);pilot.sort(key=lambda x:(x['template'],x['instance']))
    (OUT/'dataset_manifest.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in manifest),encoding='utf-8')
    dump(OUT/'pilot_manifest.json',{'schema_version':'1.0.0','version':CFG['dataset_version'],'logical_documents':pilot,'scope':'50 dev-only logical documents; paired backgrounds not independent samples'})
    dump(OUT/'split_manifest.json',{'schema_version':'1.0.0','version':CFG['dataset_version'],'seed':CFG['seed'],
                                 'template_groups':groups,'policy':'dev/calibration/test template-disjoint; source variants together; prior inspected templates dev-only',
                                 'manifest_sha256':hash_file(OUT/'dataset_manifest.jsonl'),
                                 'accuracy_test_frozen':False,'reason':'pending terms, label review and pilot QA; no model predictions used'})
    import csv
    with (OUT/'pilot_review.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['logical_document_id','template','instance','split','automated_geometry','visual_review','reviewer','issues','independent_review'])
        for p in pilot:w.writerow([p['logical_document_id'],p['template'],p['instance'],'dev',p['automated_geometry'],'PENDING','','','PENDING'])
    with (OUT/'field_coverage.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['split','field_path','annotation_status','logical_documents'])
        for key,count in sorted(coverage.items()):w.writerow([*key,count])
    summary={'schema_version':'1.0.0','checked_date':'2026-10-11','dataset_version':CFG['dataset_version'],
             'config_sha256':hash_file(CONFIG),'script_sha256':hash_file(Path(__file__)),
             'manifest_sha256':hash_file(OUT/'dataset_manifest.jsonl'),'split_manifest_sha256':hash_file(OUT/'split_manifest.json'),
             'provenance_sha256':hash_file(OUT/'provenance.jsonl'),
             'logical_documents':len(source_hashes),'image_variants':len(manifest),'annotations':len(manifest),
             'template_split_counts':{k:len(v) for k,v in groups.items()},'logical_split_counts':dict(Counter(r['split'] for r in manifest if r['document_id'].endswith('-white'))),
             'pilot_logical_documents':len(pilot),'pilot_templates':len(pilot_templates),'pilot_dev_only':all(p['split']=='dev' for p in pilot),
             'hf_array_length_errors':hf_invalid,'exact_image_hash_groups':sum(len(v)>1 for v in hash_groups.values()),
             'exact_hash_groups_crossing_splits':len(duplicate_cross),'mapping_issue_counts':dict(issues),
             'field_coverage':{s:{field:{status:coverage[(s,field,status)] for status in ['OBSERVED','NOT_ANNOTATED']} for field in FIELDS} for s in groups},
             'accuracy_evaluation_eligible':False,'independent_review':'PENDING','training_or_ocr_run':False}
    dump(REPORT,summary)
    catalog_path=ROOT/'data invoice/plan00_local/dataset_catalog.json'
    dump(catalog_path,{'schema_version':'1.0.0','checked_date':'2026-10-11','datasets':[
        {'id':'plan00-v1','manifest':'data invoice/plan00_local/dataset_manifest.jsonl','scope':'existing receipt inventory plus project-generated functional set; preserved'},
        {'id':CFG['dataset_version'],'manifest':rel(OUT/'dataset_manifest.jsonl'),'split_manifest':rel(OUT/'split_manifest.json'),'pilot':rel(OUT/'pilot_manifest.json'),'accuracy_evaluation_eligible':False}]})
    verify()
    print(json.dumps({k:v for k,v in summary.items() if k!='field_coverage'}),flush=True)


def verify():
    rows=[json.loads(l) for l in (OUT/'dataset_manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    groups=defaultdict(set);families=defaultdict(set);ids=set();counts=Counter()
    for row in rows:
        if row['document_id'] in ids:raise ValueError('Duplicate document ID')
        ids.add(row['document_id']);groups[row['template_group']].add(row['split']);families[row['duplicate_family']].add(row['split'])
        if hash_file(ROOT/row['path'])!=row['sha256']:raise ValueError('Image hash changed')
        ann=json.loads((ROOT/row['annotation_path']).read_text(encoding='utf-8'))
        if ann['document_id']!=row['document_id']:raise ValueError('Annotation ownership mismatch')
        if row['accuracy_evaluation_eligible']:raise ValueError('Unreviewed dataset incorrectly eligible')
        observed=[]
        for field in ann['fields']:
            if field['status']=='OBSERVED':
                if field['normalized_value'] is None or not field['evidence']:raise ValueError('Observed field missing value/evidence')
                observed.append(field['field_path'])
                for e in field['evidence']:
                    x0,y0,x1,y1=e['bbox']
                    if not 0<=x0<x1<=1 or not 0<=y0<y1<=1:raise ValueError('Invalid normalized bbox')
            elif field['normalized_value'] is not None:raise ValueError('Unannotated value must be null')
        if sorted(observed)!=sorted(row['label_coverage']):raise ValueError('Coverage mismatch')
        counts[row['split']]+=1
    if len(rows)!=20000 or len(families)!=10000:raise ValueError('Incomplete source coverage')
    if any(len(v)!=1 for v in [*groups.values(),*families.values()]):raise ValueError('Split leakage')
    split=json.loads((OUT/'split_manifest.json').read_text(encoding='utf-8'))
    if split['manifest_sha256']!=hash_file(OUT/'dataset_manifest.jsonl'):raise ValueError('Split manifest stale')
    for r in rows:
        t=int(r['template_group'].rsplit('-',1)[1])
        if t not in split['template_groups'][r['split']]:raise ValueError('Assignment differs from frozen groups')
    pilot=json.loads((OUT/'pilot_manifest.json').read_text(encoding='utf-8'))['logical_documents']
    if len(pilot)!=50 or len({p['logical_document_id'] for p in pilot})!=50:raise ValueError('Pilot count/identity')
    if any(p['split']!='dev' or p['template'] not in split['template_groups']['dev'] for p in pilot):raise ValueError('Pilot exposes holdout')
    print(f'PASS: {len(rows)} variants, {len(families)} logical invoices, ownership/hash/geometry/split/pilot checks',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');args=p.parse_args()
    verify() if args.verify_only else build()
