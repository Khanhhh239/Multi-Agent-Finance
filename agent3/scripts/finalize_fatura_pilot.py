"""Record the AI visual checks performed in this session; validate curated facts.

This script does not inspect images itself or substitute human review.
Input review notes are versioned independently of importer output.
"""
import csv
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data invoice/plan00_local/fatura_v1'
REVIEW=ROOT/'agent3_tax_compliance/configs/datasets/fatura_pilot_visual_review_v1.json'


def main():
    review=json.loads(REVIEW.read_text(encoding='utf-8'))
    pilot=json.loads((BASE/'pilot_manifest.json').read_text(encoding='utf-8'))['logical_documents']
    expected_ids={f'fatura-T{t:02}-I{i:03}' for t in review['reviewed_white_templates'] for i in review['reviewed_instances_per_template']}
    if {p['logical_document_id'] for p in pilot}!=expected_ids:raise ValueError('Visual review does not cover selected pilot')
    compared=0
    for docid,expected in review['visually_read_expected_fields'].items():
        ann=json.loads((BASE/'annotations'/f'{docid}-white.json').read_text(encoding='utf-8'))
        actual={f['field_path']:f['normalized_value'] for f in ann['fields']}
        for field,value in expected.items():
            if actual[field]!=value:raise ValueError(f'Visual mismatch: {docid}/{field}: {actual[field]} vs {value}')
            compared+=1
    findings={18:'SHIP_TO_NOT_BUYER',30:'SHIP_TO_NOT_BUYER',36:'AMOUNT_DUE_NOT_TOTAL',37:'AMOUNT_DUE_NOT_TOTAL'}
    with (BASE/'pilot_review.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['logical_document_id','template','instance','split','automated_geometry','visual_review','reviewer','issues','independent_review'])
        for p in pilot:
            w.writerow([p['logical_document_id'],p['template'],p['instance'],'dev',p['automated_geometry'],
                        'AI_VISUAL_REVIEWED_NOT_ADJUDICATED','Codex',findings.get(p['template'],'SEE_REVIEW_NOTES'),'PENDING'])
    # Refresh only the FATURA rows of the overview; preserve original dataset counts.
    coverage_path=ROOT/'docs/agent3/plans/evidence/plan00/coverage_matrix.csv'
    with coverage_path.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f);headers=reader.fieldnames;coverage=[r for r in reader if r['origin']!='SYNTHETIC_FATURA']
    from collections import Counter
    counts=Counter(json.loads(l)['split'] for l in (BASE/'dataset_manifest.jsonl').read_text(encoding='utf-8').splitlines())
    for split,count in sorted(counts.items()):
        coverage.append({'document_family':'SYNTHETIC_INVOICE','source_kind':'IMAGE','split':split,'origin':'SYNTHETIC_FATURA','documents':count,'accuracy_eligible':False})
    with coverage_path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader();writer.writerows(coverage)
    report={'schema_version':'1.0.0','checked_date':review['checked_date'],'pilot_logical_documents':len(pilot),
            'pilot_templates':len({p['template'] for p in pilot}),'white_images_visually_inspected':len(expected_ids),
            'colored_images_visually_inspected':0,'curated_visual_fact_checks_passed':compared,
            'review_notes_sha256':sha256(REVIEW.read_bytes()).hexdigest(),
            'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'mapped_manifest_sha256':sha256((BASE/'dataset_manifest.jsonl').read_bytes()).hexdigest(),
            'review_type':'AI_HEADER_AND_PRINTED_VALUE_SPOT_CHECK_NOT_EXHAUSTIVE_TRANSCRIPTION',
            'independent_human_review':'PENDING','accuracy_or_legal_compliance_claim':False,
            'findings':review['findings']}
    target=ROOT/'docs/agent3/plans/evidence/plan00/fatura_pilot_review_summary.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: recorded {len(pilot)} AI visual reviews; {compared} independently entered visual facts match; human adjudication pending')


if __name__=='__main__':main()
