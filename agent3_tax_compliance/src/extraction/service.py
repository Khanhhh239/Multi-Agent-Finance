"""Engine-independent extraction from the PLAN_03 normalized contract."""
from pathlib import Path
from uuid import uuid4
from ..adapters.ocr.protocol import NormalizedDocumentExtraction
from ..domain.cfr import CanonicalFinancialRecord,Derived,Parties,Party,Invoice,Totals
from ..domain.field import FieldObject
from ..domain.evidence import Provenance
from ..canonicalization.derive import sha,rederive,derived_field
from ..canonicalization.identity import allocate
from .contracts import ExtractionArtifact,ExtractionProfile,ExtractionIssue,Segmentation
from .invoice_fields import extract_headers
from .tables import discover_rows,build_items
from .vat_group_builder import build_groups

def implementation_sha():
    root=Path(__file__).resolve().parents[1]
    paths=sorted(p for folder in ('extraction','canonicalization','domain') for p in (root/folder).glob('*.py'))
    return sha({p.relative_to(root).as_posix():p.read_bytes().hex() for p in paths})

def canonicalize(document,source_format,master,profile,identity,*,record_id,artifact_id,created_at,extractor_sha256,relations=()):
    """Pure replay: IDs/timestamp/profile are explicit; no allocation or hidden IO."""
    document=NormalizedDocumentExtraction.model_validate_json(document.model_dump_json())
    if (document.tenant_id,document.taxpayer_id,document.taxpayer_master_revision)!=(master.tenant_id,master.taxpayer_id,master.revision):
        raise ValueError('document/master scope mismatch')
    issues=[];fields,candidates=extract_headers(document,profile,issues)
    numbers={c.normalized_value for c in candidates if c.semantic_field=='invoice.number'}
    segmentation=Segmentation(status='REVIEW_SPLIT' if len(numbers)>1 else 'SINGLE_CANDIDATE',
        page_groups=tuple((p.page_index,) for p in document.pages),
        reason='Competing invoice numbers require boundary confirmation.' if len(numbers)>1 else 'No conflicting labelled invoice numbers; review still required.')
    record=None;manifest=None;groups=()
    if segmentation.status=='SINGLE_CANDIDATE':
        rows=discover_rows(document,issues)
        if {e.anchor_id for e in identity.entries}!={anchor for anchor,_ in rows}: raise ValueError('identity map does not cover current row anchors')
        items,more=build_items(rows,identity,profile,issues);candidates.extend(more)
        count=fields['expected_rows'].value
        discovery='INCOMPLETE' if document.status!='COMPLETE' or (count is not None and int(count)!=len(items)) else 'UNKNOWN'
        if document.status=='COMPLETE' and items and count is not None and int(count)==len(items): discovery='COMPLETE'
        if discovery!='COMPLETE': issues.append(ExtractionIssue(code='ITEM_DISCOVERY_'+discovery,message='Row completeness is unproven or pages/rows are missing.'))
        currency=fields['currency']
        if currency.status=='MISSING' and profile.default_currency:
            currency=FieldObject(status='PRESENT',value=profile.default_currency,source='profile',confidence_basis='DETERMINISTIC',
                provenance=Provenance(method='profile-policy',adapter_version='extractor-v1',deterministic_policy_version=profile.version,
                    derived_from=(profile.currency_policy_reference,)))
        payload=dict(config_version=profile.version,creator='extractor-v1',stage='canonicalization',created_at=created_at,
            record_id=record_id,revision=1,tenant_id=document.tenant_id,taxpayer_id=document.taxpayer_id,
            taxpayer_master_revision=document.taxpayer_master_revision,source_id=document.source_id,source_format=source_format,
            record_type='INVOICE',document_id=document.document_id,
            parties=Parties(**{party:Party.model_validate({name:fields[party+'.'+name].model_dump(mode='json') for name in ('name','tax_id','address')}) for party in ('seller','buyer')}),
            invoice=Invoice.model_validate({name:fields['invoice.'+name].model_dump(mode='json') for name in ('number','series','issue_date')}),
            currency=currency,totals=Totals.model_validate({name:fields['totals.'+name].model_dump(mode='json') for name in ('net','vat','gross')}),
            items=items,item_discovery_status=discovery,derived=Derived(invoice_direction=derived_field(None,(),'AMBIGUOUS')))
        record=CanonicalFinancialRecord(**payload)
        record,manifest,more=rederive(record,master,profile,relations);issues.extend(more)
        groups=build_groups(items,discovery)
    else:
        issues.append(ExtractionIssue(code='REVIEW_SPLIT',message=segmentation.reason))
    return ExtractionArtifact(config_version=profile.version,creator='extractor-v1',stage='extraction',created_at=created_at,
        artifact_id=artifact_id,tenant_id=document.tenant_id,taxpayer_id=document.taxpayer_id,ingestion_id=document.ingestion_id,
        source_id=document.source_id,document_id=document.document_id,input_sha256=document.input_sha256,
        normalized_input_sha256=sha(document.model_dump(mode='json')),extractor_sha256=extractor_sha256,profile=profile,
        segmentation=segmentation,record=record,candidates=tuple(candidates),identity_map=identity,vat_groups=groups,
        derivation=manifest,issues=tuple(issues))

def extract(document,source_format,master,profile=None,*,previous_identity=None,mapping=None,lineage=(),relations=()):
    from datetime import datetime,timezone
    profile=profile or ExtractionProfile()
    rows=discover_rows(document,[])
    identity=allocate((a for a,_ in rows),previous_identity,mapping,lineage)
    return canonicalize(document,source_format,master,profile,identity,record_id='cfr-'+uuid4().hex,
        artifact_id='extract-'+uuid4().hex,created_at=datetime.now(timezone.utc),extractor_sha256=implementation_sha(),relations=relations)
