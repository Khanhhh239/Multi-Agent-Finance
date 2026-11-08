"""Score retained public-pilot labels by source/layout; no model accuracy claims
for fields without labels. Writes only aggregate metadata, never invoice values.
"""
import argparse
import json
import math
import sys
import tempfile
import hashlib
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import extract,implementation_sha
from src.domain.taxpayer import TaxpayerMaster
from src.quality.completeness import flatten
from src.recovery.policy import diagnose


def normalized(value,path):
    text=' '.join(unicodedata.normalize('NFC',str(value)).split())
    if path.startswith('totals.'):
        try:return str(Decimal(text).normalize())
        except Exception:return text
    return text


def wilson(errors,n):
    if not n:return None
    z=1.96;p=errors/n;d=1+z*z/n;center=(p+z*z/(2*n))/d
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,center-radius),min(1,center+radius)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',type=Path,default=ROOT/'data invoice/real_invoice_pilot_v1');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    labels=json.loads((args.pilot/'labels.json').read_text(encoding='utf-8'))
    cases=[];groups=defaultdict(lambda:dict(labeled=0,correct=0,wrong_present=0,present=0,missing_or_ambiguous=0))
    datasets=defaultdict(lambda:defaultdict(lambda:dict(labeled=0,correct=0,wrong_present=0,present=0,missing_or_ambiguous=0)))
    seen=set();excluded=[]
    inputs=[(path,None) for path in sorted((args.pilot/'normalized').glob('*.json'))]
    # Reparse native PDFs with current geometry/reader code, rather than scoring
    # historical CFR snapshots as though they were produced by today's code.
    from benchmark_public_invoices import document
    from src.ingestion.pdf_reader import read_pdf
    from src.adapters.ocr.layout_merge import merge
    from src.adapters.ocr.registry import load_default_config
    from src.config import Settings
    with tempfile.TemporaryDirectory(prefix='pilot-native-score-') as directory:
        for case in sorted(labels):
            pdf=args.pilot/'cases'/(case+'.pdf')
            if not pdf.exists() or not (args.pilot/'verified_all_fields'/(case+'-native_only.json')).exists():continue
            folder=Path(directory)/case;folder.mkdir()
            page=read_pdf(pdf,folder,dict(source_id=case,document_id=case,input_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest()),Settings())[0]
            inputs.append((Path(case+'-native_only.json'),document(case,page,merge(page,()),load_default_config()).model_dump(mode='json')))
    for path,data in inputs:
        if data is None:data=json.loads(path.read_bytes())
        if not isinstance(data,dict) or 'pages' not in data:
            excluded.append({'case_id':path.stem,'reason':'TEXT_FRAGMENT_NOT_GEOMETRY_ARTIFACT'});continue
        doc=NormalizedDocumentExtraction.model_validate(data);case=doc.ingestion_id
        if case not in labels:continue
        previous=args.pilot/'verified_all_fields'/path.name
        if not previous.exists():continue
        old=ExtractionArtifact.model_validate_json(previous.read_bytes())
        if doc.input_sha256!=old.input_sha256:raise ValueError('Frozen input hash mismatch: '+path.stem)
        if not old.record:continue
        master=TaxpayerMaster(config_version='pilot-score-v1',creator='benchmark',stage='benchmark',tenant_id=doc.tenant_id,taxpayer_id=doc.taxpayer_id,
            revision=doc.taxpayer_master_revision,tax_code='0000000000',effective_from=date(1900,1,1),provenance_reference='benchmark-only-no-direction-label')
        new=extract(doc,old.record.source_format,master,old.profile)
        if not new.record:
            cases.append({'case_id':path.stem,'segmentation':new.segmentation.status,'scored_fields':0});continue
        fields=flatten(new.record);good=0;wrong=0;denom=0;present=0;missing=0
        dataset='training_unverified' if case.startswith('accounting_training') else 'public_document_pilot'
        for field_path,expected in labels[case]['fields'].items():
            if expected is None:continue
            denom+=1;observed=fields.get(field_path)
            is_present=bool(observed and observed.status=='PRESENT' and observed.value is not None)
            correct=is_present and normalized(observed.value,field_path)==normalized(expected,field_path)
            category=('tax_id' if field_path.endswith('tax_id') else 'names' if field_path.endswith('.name') else 'totals' if field_path.startswith('totals.') else 'date' if field_path.endswith('issue_date') else 'invoice_id' if field_path.startswith('invoice.') else 'currency')
            for row in (groups[category],datasets[dataset][category]):
                row['labeled']+=1;row['correct']+=int(correct);row['present']+=int(is_present)
                row['wrong_present']+=int(is_present and not correct);row['missing_or_ambiguous']+=int(not is_present)
            good+=int(correct);present+=int(is_present);wrong+=int(is_present and not correct);missing+=int(not is_present)
        plan=diagnose(new.record,new,doc);seen.add(case)
        cases.append({'case_id':path.stem,'source_invoice_group':case,'dataset_group':dataset,'input_sha256':doc.input_sha256,'labeled':denom,'correct':good,
            'wrong_present':wrong,'present':present,'missing_or_ambiguous':missing,'item_count_correct':len(new.record.items)==labels[case]['item_count'] if 'item_count' in labels[case] else None,
            'diagnostic_fields':len(plan['entries']),'scheduled_fields':plan['scheduled_fields'],'scheduled_crops':plan['scheduled_crops']})
    for row in [*groups.values(),*(r for ds in datasets.values() for r in ds.values())]:
        row['field_exact_match']=row['correct']/row['labeled'] if row['labeled'] else None
        row['wrong_present_rate']=row['wrong_present']/row['present'] if row['present'] else None
        row['wrong_present_95pct_wilson']=wilson(row['wrong_present'],row['present'])
    report={'checked_on':'2026-10-19','extractor_sha256':implementation_sha(),'distinct_invoice_groups':len(seen),'variants':len(cases),
        'cases':cases,'excluded':excluded,'groups':dict(groups),'dataset_groups':{k:dict(v) for k,v in datasets.items()},'normalization':'Unicode NFC + whitespace; Decimal numeric equivalence for totals only; case-sensitive names',
        'label_provenance':'Existing agent-checked pilot labels; no independent reviewer','split':'DEV_ALREADY_USED_FOR_FIXES',
        'unlabeled_fields_not_scored':True,'address_and_table_cell_accuracy':'NOT_EVALUATED_NO_COMPLETE_LABELS','holdout_accuracy':'NOT_EVALUATED',
        'model_runs_in_this_script':False,'counts_are_correlated_across_variants':True,'release_approved':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'variants':len(cases),'distinct_invoice_groups':len(seen),'groups':dict(groups)},ensure_ascii=True))


if __name__=='__main__':main()
