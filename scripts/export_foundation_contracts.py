import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent3_tax_compliance'))
from src.domain.cfr import CanonicalFinancialRecord
from src.domain.envelope import SourceEnvelope
from src.domain.evidence import Evidence, PageTransform
from src.domain.events import AuditEvent
from src.domain.field import FieldObject
from src.domain.interfaces import (Assessment, Correction, DetectedSource, Document, Extraction, StageResponse)
from src.domain.money import ExactDecimal
from src.domain.storage import Artifact, Job
from src.domain.taxpayer import TaxpayerMaster

MODELS = {
    'source_envelope': SourceEnvelope, 'field_text': FieldObject[str],
    'field_money': FieldObject[ExactDecimal], 'evidence': Evidence, 'page_transform': PageTransform,
    'cfr': CanonicalFinancialRecord, 'taxpayer_master': TaxpayerMaster,
    'audit_event': AuditEvent, 'artifact': Artifact, 'job': Job, 'document': Document,
    'detect_response': StageResponse[DetectedSource], 'extract_response': StageResponse[Extraction],
    'canonicalize_response': StageResponse[tuple[CanonicalFinancialRecord, ...]],
    'assess_response': StageResponse[Assessment], 'review_response': StageResponse[CanonicalFinancialRecord],
    'correction': Correction,
}


def export():
    destination = ROOT / 'agent3_tax_compliance/contracts/v1'
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, model in MODELS.items():
        schema = model.model_json_schema(mode='serialization')
        schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
        schema['$id'] = f'urn:financial:capture:1.0.0:{name}'
        path = destination / f'{name}.schema.json'
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / 'registry.json').write_text(json.dumps({
        'schema_version': '1.0.0', 'profile': 'capture-foundation-v1', 'schemas': hashes,
        'semantic_validation': 'src.domain model validators are mandatory after structural JSON Schema validation',
    }, indent=2) + '\n', encoding='utf-8')
    export_examples(destination)
    print(f'Exported {len(hashes)} contracts')


def export_examples(destination):
    from copy import deepcopy
    sys.path.insert(0, str(ROOT / 'agent3_tax_compliance/tests/contracts'))
    from factories import STAMP, envelope, field, record
    e=envelope(); r=record()
    common=dict(**STAMP,request_id='request-1',input_sha256=e.sha256,status='SUCCEEDED')
    detection=StageResponse[DetectedSource](**common,data=DetectedSource(
        envelope=e,detected_format=e.detected_format,detection_status='SUPPORTED'))
    extraction=StageResponse[Extraction](**common,data=Extraction(**STAMP,source_id=e.source_id,
        document_id=r.document_id,input_sha256=e.sha256,fields={'invoice.number':field('0000123')}))
    assessment=StageResponse[Assessment](**common,data=Assessment(**STAMP,record_id=r.record_id,
        record_revision=1,input_sha256=e.sha256,review_required=True,issue_codes=('UNCALIBRATED',)))
    objects=[('source_envelope',e),('cfr',r),('detect_response',detection),('extract_response',extraction),
             ('canonicalize_response',StageResponse[tuple[CanonicalFinancialRecord,...]](**common,data=(r,))),
             ('assess_response',assessment),('review_response',StageResponse[CanonicalFinancialRecord](**common,data=r))]
    valid=[dict(contract=name,payload=obj.model_dump(mode='json')) for name,obj in objects]
    invalid=[]
    for name, mutate in [
        ('money-float',lambda p:p['totals']['gross'].update(value=0.1)),
        ('missing-with-value',lambda p:p['totals']['gross'].update(status='MISSING')),
        ('unknown-direction-present',lambda p:p['derived'].update(invoice_direction=field('UNKNOWN'))),
        ('unsupported-version',lambda p:p.update(schema_version='2.0.0')),
    ]:
        payload=deepcopy(r.model_dump(mode='json')); mutate(payload)
        invalid.append(dict(name=name,contract='cfr',payload=payload))
    (destination/'examples.json').write_text(json.dumps(dict(schema_version='1.0.0',valid=valid,invalid=invalid),indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    export()
