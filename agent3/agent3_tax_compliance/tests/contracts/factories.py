from datetime import date
from hashlib import sha256

from src.domain.cfr import CanonicalFinancialRecord, Derived, Invoice, Parties, Party, Totals
from src.domain.envelope import SourceEnvelope
from src.domain.field import FieldObject
from src.domain.taxpayer import AccessContext, TaxpayerMaster

STAMP = dict(config_version='test-v1', creator='fixture', stage='contract-test', created_at='2026-10-11T00:00:00Z')
RAW = b'%PDF-1.4 synthetic fixture; not a real document'


def field(value=None, status=None):
    return dict(value=value, status=status or ('PRESENT' if value is not None else 'MISSING'),
                source='synthetic', confidence_basis='UNAVAILABLE', confidence=None,
                provenance=dict(method='fixture', adapter_version='v1'))


def context(tenant='tenant-a', taxpayers=('payer-a', 'payer-b')):
    return AccessContext(actor_id='fixture-admin', tenant_id=tenant, taxpayer_ids=frozenset(taxpayers),
                         permissions=frozenset({'READ','WRITE','ADMIN'}))


def master(taxpayer='payer-a', tenant='tenant-a'):
    return TaxpayerMaster(**STAMP, tenant_id=tenant, taxpayer_id=taxpayer, revision=1,
                          tax_code='1234567890', effective_from=date(2026, 1, 1), provenance_reference='synthetic-master')


def envelope():
    return SourceEnvelope(**STAMP, tenant_id='tenant-a', taxpayer_id='payer-a', taxpayer_master_revision=1,
                          request_id='request-1', source_id='source-1', sha256=sha256(RAW).hexdigest(),
                          size_bytes=len(RAW), declared_mime='application/pdf', detected_format='PDF',
                          adapter_version='v1', profile_version='v1')


def record():
    return CanonicalFinancialRecord(**STAMP, record_id='record-1', revision=1, tenant_id='tenant-a',
        taxpayer_id='payer-a', taxpayer_master_revision=1, source_id='source-1', source_format='PDF',
        document_id='document-1', record_type='INVOICE', parties=Parties(seller=Party(), buyer=Party()),
        invoice=Invoice(number=FieldObject[str](**field('0000123'))),
        totals=Totals(gross=field('9007199254740993.1')),
        derived=Derived(invoice_direction=field(status='AMBIGUOUS')))
