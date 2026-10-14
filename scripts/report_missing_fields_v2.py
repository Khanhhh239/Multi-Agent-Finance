"""Aggregate second-round PLAN_06 fixes without publishing invoice text."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.extraction.invoice_fields import clean_label,labelled,normalize_field
from src.extraction.contracts import ExtractionProfile
from src.canonicalization.normalize import key

LOCAL=ROOT/'data invoice/ocr_extraction_v2'
PUBLIC=ROOT/'docs/agent3/plans/evidence/ocr_extraction_v2'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    runs=('plan06_default_missing_fields_fix_01','plan06_missing_fields_fix_02')
    replays={name:read(LOCAL/name/'summary.json') for name in runs}
    aggregates=[]
    for name,summary in replays.items():
        for mode in ('native_only','scan','hybrid'):
            rows=[r for r in summary['rows'] if r['mode']==mode and not r['case'].startswith('accounting_training')]
            counts=Counter()
            for row in rows:counts.update(row['counts'])
            aggregates.append(dict(run_id=name,mode=mode,documents=len(rows),counts=dict(counts)))
    labels=read(ROOT/'data invoice/real_invoice_pilot_v1/labels.json')
    region=LOCAL/'plan06_region_dpi_01'
    manifest={r['image']:r for r in read(region/'manifest.json')}
    region_scores=[]
    for filename in ('results.json','results-beam-300.json'):
        result=read(region/filename)
        for row in result['rows']:
            spec=manifest[row['image']];raw=row['result']['document_text_raw']
            field=spec['field'];value=raw.lstrip(':： ')
            if field.endswith('tax_id'):
                _,parsed=labelled(raw,{'tax':('ma so thue','mst')})
                if parsed is not None:value=parsed
            elif field=='invoice.series':
                _,parsed=labelled(raw,{'series':('ky hieu',)})
                if parsed is not None:value=parsed
            elif field=='invoice.issue_date':
                match=re.fullmatch(r'ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})\s*\)?',key(clean_label(raw)))
                value='/'.join(match.groups()) if match else raw
            values=normalize_field(field,value,ExtractionProfile(number_locale='VI'))
            region_scores.append(dict(case=spec['case'],field=field,dpi=spec['dpi'],decode=result.get('decode','greedy'),
                outcome='CORRECT_PARSED' if labels[spec['case']]['fields'][field] in values else 'UNRESOLVED',
                elapsed_seconds=row['elapsed_seconds'],crop_sha256=row['image_sha256']))
    report=dict(parent_plan='PLAN_06',label_status='SELF_CHECK_NOT_INDEPENDENT',
        extractor_sha256=replays[runs[0]]['extractor_sha256'],aggregates=aggregates,
        changes={name:summary['changes'] for name,summary in replays.items()},
        region_experiments=region_scores,region_recovery_in_runtime=False,
        experimental_split_default=False,remaining=['four missing fields on default OCR; three on split OCR',
            'two case-sensitive name mismatches on split OCR','runtime region recovery',
            'new-template evaluation and UI self acceptance'])
    (PUBLIC/'missing_fields_round_02.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(aggregates=aggregates,region=region_scores),ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()
