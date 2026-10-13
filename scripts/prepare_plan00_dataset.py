"""Offline PLAN_00 inventory, synthetic functional fixtures and leakage audit.

Run with the existing prototype interpreter (PyMuPDF + Pillow).
No OCR inference, downloads, database writes, or edits to existing datasets.
Real labels/paths remain in ignored local metadata; public reports use aggregates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import unicodedata

import pymupdf as fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / 'agent3_tax_compliance/configs/datasets/plan00_v1.json'
CFG = json.loads(CFG_PATH.read_text(encoding='utf-8'))
FIX = ROOT / CFG['fixture_root']
LOCAL = ROOT / CFG['local_metadata_root']
EVIDENCE = ROOT / 'docs/agent3/plans/evidence/plan00'
BENCH = ROOT / CFG['benchmark_root']


def digest(path):
    h = sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows), encoding='utf-8')


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def synthetic_document(group):
    doc = fitz.open()
    fields = []
    # Ten controlled layout positions, not ten representative real suppliers.
    offset = group * 3
    def page():
        p = doc.new_page(width=595, height=842)
        p.insert_font(fontname='fixture', fontfile=CFG['font_path'])
        p.insert_text((32, 34), 'DỮ LIỆU GIẢ LẬP — KHÔNG PHẢI HÓA ĐƠN THẬT', fontname='fixture', fontsize=10)
        return p
    p = page()
    def field(key, label, raw, value, y, page_index=0):
        current = doc[page_index]
        current.insert_text((38+offset, y), label, fontname='fixture', fontsize=10)
        current.insert_text((260, y), raw, fontname='fixture', fontsize=10)
        rects = current.search_for(raw)
        rect = next((r for r in rects if abs(r.y1-y) < 8 and r.x0 > 250), None)
        if rect is None:
            raise ValueError(f'Cannot locate fixture value {key}')
        fields.append({'field_path':key,'status':'OBSERVED','raw_text':raw,'normalized_value':value,
                       'evidence':[{'page_index':page_index,'bbox':[rect.x0/595,rect.y0/842,rect.x1/595,rect.y1/842]}]})
    field('seller.name','Tên người bán',f'CÔNG TY GIẢ LẬP {group:02}',f'CÔNG TY GIẢ LẬP {group:02}',90)
    field('seller.tax_id','MST người bán','0000000000','0000000000',120)
    field('buyer.name','Tên người mua','ĐƠN VỊ MUA GIẢ LẬP','ĐƠN VỊ MUA GIẢ LẬP',150)
    field('buyer.tax_id','MST người mua','0000000000000','0000000000000',180)
    field('invoice.number','Số hóa đơn',f'DEMO/{group:03}',f'DEMO/{group:03}',210)
    field('invoice.issue_date','Ngày lập','11/10/2026','2026-10-11',240)
    field('currency','Đơn vị tiền tệ','VND','VND',270)
    # Rows intentionally include numeric 0%, KCT and KKKNT in groups 7..9.
    treatments = ['8%', '0%', ['8%','KCT','KKKNT'][group % 3]] if group >= 7 else ['8%']
    net = 0
    vat = 0
    for i, treatment in enumerate(treatments):
        amount = (group+1)*100000 + i*10000
        rate = '0.08' if treatment=='8%' else ('0' if treatment=='0%' else None)
        tax = amount*8//100 if treatment=='8%' else 0
        net += amount; vat += tax
        base = f'items.demo-item-{group}-{i}'
        y = 350+i*85
        field(base+'.description',f'Mặt hàng {i+1}',f'HÀNG GIẢ LẬP {group}/{i}',f'HÀNG GIẢ LẬP {group}/{i}',y)
        field(base+'.net_amount','Tiền trước thuế',str(amount),str(amount),y+20)
        field(base+'.vat_treatment','Thuế suất / nhóm',treatment,'TAXABLE_RATE' if rate is not None else treatment,y+40)
        if rate is not None:
            # Same observed token carries the normalized rate, not an invented legal category.
            fields.append({**fields[-1], 'field_path':base+'.vat_rate','normalized_value':rate})
        else:
            fields.append({'field_path':base+'.vat_rate','status':'NOT_ANNOTATED','raw_text':None,'normalized_value':None,'evidence':[]})
    if group == 8:
        page()
    total_page = 1 if group==8 else 0
    field('totals.net','Cộng trước thuế',str(net),str(net),650,total_page)
    field('totals.vat','Tiền thuế',str(vat),str(vat),680,total_page)
    field('totals.gross','Tổng thanh toán',str(net+vat),str(net+vat),710,total_page)
    fields.append({'field_path':'vat_category','status':'NOT_ANNOTATED','raw_text':None,'normalized_value':None,'evidence':[]})
    return doc, fields


def make_fixtures():
    FIX.mkdir(parents=True, exist_ok=True)
    rows = []
    annotations = []
    for group in range(10):
        split = next(s for s,g in CFG['synthetic_split_groups'].items() if group in g)
        doc, fields = synthetic_document(group)
        # no_new_id makes the PDF deterministic for a fixed rendering runtime/font.
        text_bytes = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
        images = [p.get_pixmap(matrix=fitz.Matrix(1,1), alpha=False).tobytes('png') for p in doc]
        scan = fitz.open()
        for image in images:
            scan.new_page(width=595,height=842).insert_image(fitz.Rect(0,0,595,842),stream=image)
        for kind, ext, blob in [('PDF_TEXT','pdf',text_bytes),('PDF_IMAGE','pdf',scan.tobytes(garbage=4,deflate=True,no_new_id=True)),('IMAGE','png',images[0])]:
            docid = f'syn-{group:02}-{kind.lower()}'
            path = FIX/f'{docid}.{ext}'
            path.write_bytes(blob)
            # Single image is deliberately an incomplete view of the two-page group 8.
            page_count = 1 if kind=='IMAGE' else len(doc)
            ann_fields=[]
            for f in fields:
                if any(e['page_index'] >= page_count for e in f['evidence']):
                    ann_fields.append({'field_path':f['field_path'],'status':'NOT_ANNOTATED','raw_text':None,'normalized_value':None,'evidence':[]})
                else: ann_fields.append(f)
            ann = {'schema_version':'1.0.0','annotation_version':'synthetic-v1','document_id':docid,
                   'origin':'SYNTHETIC','review_status':'GENERATOR_VERIFIED_NOT_INDEPENDENTLY_REVIEWED',
                   'page_count':page_count,'fields':ann_fields}
            ann_path=FIX/f'{docid}.annotation.json'
            write_json(ann_path,ann)
            rows.append({'schema_version':'1.0.0','dataset_id':'functional_set_v1','version':CFG['dataset_version'],
                         'document_id':docid,'sha256':digest(path),'path':relative(path),'document_family':'SYNTHETIC_INVOICE',
                         'source_kind':kind,'page_count':page_count,'permission_basis':'PROJECT_GENERATED_NO_CUSTOMER_DATA',
                         'split':split,'template_group':f'synthetic-template-{group:02}',
                         'duplicate_family':f'synthetic-logical-{group:02}',
                         'label_coverage':sorted(f['field_path'] for f in ann_fields if f['status']=='OBSERVED'),
                         'annotation_version':'synthetic-v1','annotation_path':relative(ann_path),'origin':'SYNTHETIC',
                         'accuracy_evaluation_eligible':False,'limitations':['INVALID_DEMO_TAX_IDS','CONTROLLED_LAYOUT_NOT_REPRESENTATIVE'] + (['INCOMPLETE_MULTIPAGE_VIEW'] if group==8 and kind=='IMAGE' else [])})
            annotations.append(ann)
        scan.close();doc.close()
    write_jsonl(FIX/'manifest.jsonl',rows)
    # Metadata-only negative contracts; never counted as accuracy documents.
    write_json(FIX/'negative_cases.json',{'schema_version':'1.0.0','cases':[
        {'id':'receipt-no-buyer','family':'RECEIPT','buyer_status':'ABSENT_CONFIRMED','expected':'Do not derive buyer from tenant'},
        {'id':'unannotated-buyer','buyer_status':'NOT_ANNOTATED','expected':'Exclude from field accuracy denominator'},
        {'id':'unreadable-tax-id','seller_tax_id_status':'UNREADABLE','expected':'No guessed normalized value'},
        {'id':'vat-kct-vs-zero','expected':'KCT/KKKNT not numeric zero; legal category not inferred from rate'},
        {'id':'missing-page','source':'syn-08-image','expected':'Do not claim complete item/total discovery'},
        {'id':'document-pages','source':'syn-08-pdf_text','expected':'Both pages stay in one document and one split'}]})
    # Known resized/rotated variants for auditing the near-duplicate detector itself.
    source=FIX/'syn-00-image.png'
    with Image.open(source) as im:
        im.resize((im.width//2,im.height//2)).save(FIX/'duplicate-resized.png')
        im.transpose(Image.Transpose.ROTATE_90).save(FIX/'duplicate-rotated.png')
    return rows,annotations


def dhashes(path):
    with Image.open(path) as im:
        im=im.convert('L')
        result=[]
        for angle in (0,90,180,270):
            small=im.rotate(angle,expand=True).resize((9,8),Image.Resampling.LANCZOS)
            p=[small.getpixel((x,y)) for y in range(8) for x in range(9)]
            result.append(sum(int(p[y*9+x]>p[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8)))
        return result


def inventory_real():
    gt={r['image_id']:r for r in read_jsonl(BENCH/'data/ground_truth/fields/all.jsonl')}
    rows=[]
    checks=Counter()
    hashes=defaultdict(list)
    perceptual={}
    for split in ['dev','test']:
        for old in read_jsonl(BENCH/f'data/manifests/full_image_{split}.jsonl'):
            path=Path(old['image_path'])
            h=digest(path)
            checks['hash_match' if h==old.get('sha256') else 'hash_mismatch']+=1
            docid='mcocr-'+sha256(old['image_id'].encode()).hexdigest()[:20]
            labels=sorted({f['label'] for f in gt.get(old['image_id'],{}).get('fields',[])})
            rows.append({'schema_version':'1.0.0','dataset_id':'mcocr_existing_inventory','version':CFG['dataset_version'],
                         'document_id':docid,'sha256':h,'path':relative(path),'document_family':'RECEIPT',
                         'source_kind':'IMAGE','page_count':1,'permission_basis':'UNVERIFIED_LOCAL_REGISTRATION',
                         'split':'QUARANTINE','legacy_split':split,'template_group':None,'duplicate_family':None,
                         'label_coverage':labels,'annotation_version':'benchmark-existing-v1','origin':'REAL_PUBLIC_DATASET',
                         'accuracy_evaluation_eligible':False,'limitations':['PERMISSION_RECORD_NOT_FOUND','TEMPLATE_GROUPS_NOT_AUDITED','LEGACY_TEST_ALREADY_USED_IN_SMOKE']})
            hashes[h].append(docid)
            perceptual[docid]=dhashes(path)
    # Broad cheap candidates only; human/template audit must resolve them.
    candidates=[]
    names=sorted(perceptual)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            distance=min((perceptual[a][0]^v).bit_count() for v in perceptual[b])
            if distance<=4: candidates.append({'a':a,'b':b,'dhash_distance':distance,'status':'UNREVIEWED_CANDIDATE'})
    exact=[v for v in hashes.values() if len(v)>1]
    legacy_split={r['document_id']:r['legacy_split'] for r in rows}
    cross=[v for v in exact if len({legacy_split[i] for i in v})>1]
    return rows, {'hash_verification':dict(checks),'exact_duplicate_groups':exact,
                  'exact_groups_crossing_legacy_splits':cross,
                  'near_duplicate_candidates':candidates,'algorithm':'rotation-aware dHash 9x8; distance<=4; candidate-only',
                  'template_independence_verified':False}


def build():
    synthetic,annotations=make_fixtures()
    real,audit=inventory_real()
    LOCAL.mkdir(parents=True,exist_ok=True)
    rows=synthetic+real
    write_jsonl(LOCAL/'dataset_manifest.jsonl',rows)
    source=FIX/'syn-00-image.png'
    a=dhashes(source)[0]
    variant_checks={p.name:min((a^v).bit_count() for v in dhashes(p)) for p in [FIX/'duplicate-resized.png',FIX/'duplicate-rotated.png']}
    audit.update({'schema_version':'1.0.0','known_variant_distances':variant_checks,'synthetic_families_kept_together':True})
    write_json(LOCAL/'duplicate_report.json',audit)
    split={'schema_version':'1.0.0','config_sha256':digest(CFG_PATH),'manifest_sha256':digest(LOCAL/'dataset_manifest.jsonl'),
           'frozen_for_functional_tests_only':True,'accuracy_test_frozen':False,
           'assignments':[{'document_id':r['document_id'],'split':r['split'],'template_group':r['template_group'],'duplicate_family':r['duplicate_family']} for r in rows],
           'policy':'Real data quarantined; synthetic siblings and all pages stay in one split; no claim of real template-disjoint evaluation'}
    write_json(LOCAL/'split_manifest.json',split)
    coverage=Counter((r['document_family'],r['source_kind'],r['split'],r['origin']) for r in rows)
    with (EVIDENCE/'coverage_matrix.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['document_family','source_kind','split','origin','documents','accuracy_eligible'])
        for k,count in sorted(coverage.items()):w.writerow([*k,count,False])
        for kind in ['PDF_TEXT','PDF_IMAGE','IMAGE']:w.writerow(['REAL_VIETNAMESE_TAX_INVOICE',kind,'UNAVAILABLE','REAL',0,False])
    summary={'schema_version':'1.0.0','generator_sha256':digest(Path(__file__)),'config_sha256':digest(CFG_PATH),
             'font_sha256':digest(Path(CFG['font_path'])),'versions':{n:importlib.metadata.version(n) for n in ['PyMuPDF','Pillow']},
             'manifest_sha256':digest(LOCAL/'dataset_manifest.jsonl'),'split_sha256':digest(LOCAL/'split_manifest.json'),
             'synthetic_documents':len(synthetic),'synthetic_logical_documents':10,'synthetic_pages':sum(r['page_count'] for r in synthetic),
             'real_inventory_documents':len(real),'hash_verification':audit['hash_verification'],
             'real_exact_duplicate_groups':len(audit['exact_duplicate_groups']),
             'real_near_duplicate_candidate_pairs':len(audit['near_duplicate_candidates']),
             'exact_duplicate_groups_crossing_legacy_splits':len(audit['exact_groups_crossing_legacy_splits']),
             'known_variant_distances':variant_checks,'independent_annotation_review':'PENDING',
             'gate':'PARTIAL_BLOCKED_REAL_DATA_AND_SECOND_REVIEW'}
    write_json(EVIDENCE/'build_summary.json',summary)
    write_json(EVIDENCE/'annotation_examples.json',{'schema_version':'1.0.0','examples':[annotations[i] for i in [0,3,18,24,27]],'independent_review':'PENDING'})
    verify()
    print(json.dumps(summary,ensure_ascii=True))


def verify():
    rows=read_jsonl(LOCAL/'dataset_manifest.jsonl')
    ids=set();splits=defaultdict(set);templates=defaultdict(set)
    for r in rows:
        assert r['document_id'] not in ids, 'Duplicate document ID'
        ids.add(r['document_id'])
        path=ROOT/r['path']
        assert path.is_file() and digest(path)==r['sha256'], 'Missing or modified source'
        if r['origin']=='REAL_PUBLIC_DATASET':
            assert r['split']=='QUARANTINE' and not r['accuracy_evaluation_eligible']
            continue
        splits[r['duplicate_family']].add(r['split']);templates[r['template_group']].add(r['split'])
        ann=json.loads((ROOT/r['annotation_path']).read_text(encoding='utf-8'))
        assert ann['page_count']==r['page_count']
        for field in ann['fields']:
            if field['status']=='OBSERVED':
                assert field['raw_text'] and field['normalized_value'] is not None and field['evidence']
            else: assert field['normalized_value'] is None
            for e in field['evidence']:
                x0,y0,x1,y1=e['bbox']
                assert 0<=x0<x1<=1 and 0<=y0<y1<=1 and 0<=e['page_index']<ann['page_count']
        if r['source_kind'].startswith('PDF'):
            with fitz.open(path) as doc:
                assert len(doc)==r['page_count']
                hastext=any(p.get_text().strip() for p in doc)
                assert hastext==(r['source_kind']=='PDF_TEXT')
                if hastext:
                    for field in ann['fields']:
                        for e in field['evidence']:
                            rect=fitz.Rect(e['bbox'][0]*595,e['bbox'][1]*842,e['bbox'][2]*595,e['bbox'][3]*842)
                            # Bbox resolves to actual text, including Vietnamese accents.
                            extracted=doc[e['page_index']].get_textbox(rect+(-1,-1,1,1)).strip()
                            assert unicodedata.normalize('NFC',field['raw_text']) in unicodedata.normalize('NFC',extracted), field['field_path']
    assert all(len(v)==1 for v in splits.values()), 'Duplicate family leaks across splits'
    assert all(len(v)==1 for v in templates.values()), 'Template group leaks across splits'
    counts=Counter(r['source_kind'] for r in rows if r['origin']=='SYNTHETIC')
    assert counts=={'PDF_TEXT':10,'PDF_IMAGE':10,'IMAGE':10}
    split=json.loads((LOCAL/'split_manifest.json').read_text(encoding='utf-8'))
    assert split['manifest_sha256']==digest(LOCAL/'dataset_manifest.jsonl')
    assert {r['document_id']:r['split'] for r in rows}=={r['document_id']:r['split'] for r in split['assignments']}
    audit=json.loads((LOCAL/'duplicate_report.json').read_text(encoding='utf-8'))
    assert all(d<=4 for d in audit['known_variant_distances'].values()), 'Known transform duplicate not detected'
    print(f'PASS: {len(rows)} sources hashed; 30 synthetic fixtures; geometry/native-scan types; split leakage and known variants checked')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    verify() if args.verify_only else build()
