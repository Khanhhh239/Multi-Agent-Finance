"""Validate mapped FATURA contracts using the system Python's jsonschema.

Records annotation checksums once; subsequent runs reject modified snapshots.
No image/model inference. Run after prepare_fatura_dataset + finalize_fatura_pilot.
"""
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data invoice/plan00_local/fatura_v1'
CFG=ROOT/'agent3_tax_compliance/configs/datasets'


def digest(path):return sha256(path.read_bytes()).hexdigest()


def main():
    annotation_schema=json.loads((CFG/'annotation_v1.schema.json').read_text(encoding='utf-8'))
    manifest_schema=json.loads((CFG/'manifest_v1.schema.json').read_text(encoding='utf-8'))
    for schema in [annotation_schema,manifest_schema]:Draft202012Validator.check_schema(schema)
    av=Draft202012Validator(annotation_schema);mv=Draft202012Validator(manifest_schema)
    rows=[json.loads(l) for l in (OUT/'dataset_manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    checksums={};counts=Counter()
    for i,row in enumerate(rows,1):
        mv.validate(row)
        path=ROOT/row['annotation_path']
        ann=json.loads(path.read_text(encoding='utf-8'));av.validate(ann)
        assert ann['document_id']==row['document_id']
        assert ann['review_status']=='SECOND_REVIEW_PENDING' and not row['accuracy_evaluation_eligible']
        fields={f['field_path']:f for f in ann['fields']}
        assert len(fields)==len(ann['fields']), 'Duplicate semantic field'
        for f in fields.values():
            if f['status']=='OBSERVED':
                counts[f['field_path']]+=1
                if f['field_path'].startswith('totals.'):
                    assert isinstance(f['normalized_value'],str) and Decimal(f['normalized_value']).is_finite()
            for e in f['evidence']:
                x0,y0,x1,y1=e['bbox'];assert 0<=x0<x1<=1 and 0<=y0<y1<=1 and e['page_index']==0
        for name in ['seller.tax_id','buyer.tax_id','vat_category','items']:
            assert fields[name]['status']=='NOT_ANNOTATED' and fields[name]['normalized_value'] is None
        checksums[row['document_id']]=digest(path)
        if i%5000==0:print(f'Validated {i} manifests and annotations',flush=True)
    assert len(rows)==20000 and len(checksums)==20000
    snapshot=OUT/'annotation_checksums.json'
    if snapshot.exists():
        assert json.loads(snapshot.read_text(encoding='utf-8'))==checksums, 'Annotation snapshot changed: version/review before resealing'
    else:snapshot.write_text(json.dumps(checksums,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    summary={'schema_version':'1.0.0','checked_date':'2026-10-11','manifest_rows_validated':len(rows),
             'annotation_files_validated':len(checksums),'annotation_schema_sha256':digest(CFG/'annotation_v1.schema.json'),
             'manifest_schema_sha256':digest(CFG/'manifest_v1.schema.json'),'annotation_checksums_sha256':digest(snapshot),
             'manifest_sha256':digest(OUT/'dataset_manifest.jsonl'),'script_sha256':digest(Path(__file__)),
             'observed_field_counts_image_variants':dict(counts),'money_representation':'decimal strings',
             'schema_and_ownership_and_status_and_bounds':'PASS','human_adjudication':'PENDING','release_accuracy_eligible':False}
    target=ROOT/'docs/agent3/plans/evidence/plan00/fatura_contract_validation.json'
    target.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    catalog_path=ROOT/'data invoice/plan00_local/dataset_catalog.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    for d in catalog['datasets']:
        if d['id']=='fatura-mapped-v1':d['annotation_checksums']=snapshot.relative_to(ROOT).as_posix()
    catalog_path.write_text(json.dumps(catalog,indent=2)+'\n',encoding='utf-8')
    print('PASS: 20000 manifest/annotation schemas, exact money representation, statuses, geometry and annotation snapshot',flush=True)


if __name__=='__main__':main()
