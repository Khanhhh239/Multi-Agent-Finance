"""Read-only dev replay of retained OCR; counts are diagnostics, not accuracy."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.domain.taxpayer import TaxpayerMaster
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import extract,implementation_sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    db=sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    cases=[]
    try:
        rows=db.execute('SELECT * FROM cfr_extractions ORDER BY rowid DESC LIMIT 50').fetchall()
        for n,row in enumerate(rows,1):
            if hashlib.sha256(row['payload'].encode()).hexdigest()!=row['sha256']:raise ValueError('Artifact integrity failure')
            old=ExtractionArtifact.model_validate_json(row['payload'])
            if old.record is None:continue
            ocr=db.execute('SELECT payload,sha256 FROM ocr_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=?',
                (row['tenant_id'],row['taxpayer_id'],row['ingestion_id'],row['ocr_config_key'])).fetchone()
            if hashlib.sha256(ocr['payload'].encode()).hexdigest()!=ocr['sha256']:raise ValueError('OCR integrity failure')
            doc=NormalizedDocumentExtraction.model_validate_json(ocr['payload'])
            master=db.execute('SELECT payload FROM taxpayer_masters WHERE tenant_id=? AND taxpayer_id=? AND revision=?',
                (row['tenant_id'],row['taxpayer_id'],doc.taxpayer_master_revision)).fetchone()
            new=extract(doc,old.record.source_format,TaxpayerMaster.model_validate_json(master['payload']),old.profile)
            record=new.record
            cases.append({'case_id':f'dev-{n:02d}','input_sha256':doc.input_sha256,
                'label_status':'NOT_ANNOTATED','split':'DEV_ALREADY_USED_FOR_FIXES',
                'before_items':len(old.record.items),'after_items':len(record.items) if record else None,
                'item_status':record.item_discovery_status if record else None,
                'before_issues':[i.code for i in old.issues],'after_issues':[i.code for i in new.issues],
                'old_extractor_sha256':old.extractor_sha256,
                'item_evidence_present':bool(record and record.items and all(i.description and i.description.provenance.evidence for i in record.items))})
    finally:db.close()
    report={'checked_on':'2026-10-18','scope':'Read-only cached OCR dev replay; no runtime OCR, independent labels or holdout accuracy.',
            'extractor_sha256':implementation_sha(),'cases':cases,'auto_accept':'DISABLED'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'cases':len(cases),'counts':[(c['case_id'],c['before_items'],c['after_items']) for c in cases]}))


if __name__=='__main__':main()
