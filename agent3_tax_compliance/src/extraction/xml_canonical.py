"""Signed-XML e-invoice to ExtractionArtifact. Pure replay: IDs, timestamp and profile are explicit.

Field locations are carried as XPaths in Provenance.derived_from (there is no page or bounding box).
Fields claim `xml-signed-v1` only when the seller signature verified; the quality stage re-verifies the
signature from the raw source bytes before it grants DETERMINISTIC_VERIFIED.
"""
import re
from decimal import Decimal, InvalidOperation

from ..canonicalization.derive import derived_field, rederive, sha
from ..domain.cfr import CanonicalFinancialRecord, Derived, Invoice, Item, Parties, Party, Totals
from ..domain.envelope import SourceFormat
from ..domain.evidence import Provenance
from ..domain.field import FieldObject
from .contracts import ExtractionArtifact, ExtractionIssue, Segmentation
from .vat_group_builder import build_groups
from .xml_invoice import extract

XML_OCR_KEY = 'xml-direct-v1'  # sentinel stored where OCR-derived artifacts keep their OCR config key
ADAPTER = 'xml-extractor-v1'
TAX_CODE = re.compile(r'^(?:[0-9]{10}(?:[0-9]{3}|-[0-9]{3})?|[0-9]{12})$')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def duplicate_key(raw: bytes):
    """Identity of an invoice for duplicate detection: seller tax id, template+symbol, number."""
    f = extract(raw).fields
    values = (f['seller_tax_id'].value, (f['template'].value or '') + (f['symbol'].value or ''), f['number'].value)
    return values if all(values) else None


def duplicate_issues(db, ctx, payer, ingestion_id, raw):
    key = duplicate_key(raw)
    if key is None:
        return ()
    rows = db.execute("SELECT json_extract(payload,'$.record.record_id') AS record_id FROM cfr_extractions "
                      "WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id!=? "
                      "AND json_extract(payload,'$.record.parties.seller.tax_id.value')=? "
                      "AND json_extract(payload,'$.record.invoice.series.value')=? "
                      "AND json_extract(payload,'$.record.invoice.number.value')=? ORDER BY rowid",
                      (ctx.tenant_id, payer, ingestion_id, *key)).fetchall()
    return tuple(ExtractionIssue(code='XML_CHECK_DUPLICATE', field_path='invoice.number',
                                 message=f'Same seller, symbol and number were already captured as record {r["record_id"]}.') for r in rows)


def row_anchor(index):
    return f'xml:HHDVu:{index}'


def anchors(raw: bytes):
    from .xml_signature import safe_parse
    root = safe_parse(raw)
    return [row_anchor(i) for i, _ in enumerate(root.findall('DLHDon/NDHDon/DSHHDVu/HHDVu'), 1)]


def _fields(inv):
    policy = inv.fidelity_policy
    issues = []

    def make(xf, convert, path):
        paths = tuple(x.xpath for x in xf) if isinstance(xf, tuple) else (xf.xpath,)
        values = [x.value for x in xf] if isinstance(xf, tuple) else [xf.value]
        miss = lambda status='MISSING': FieldObject(status=status, source='xml',  # noqa: E731
                                                    provenance=Provenance(method='xml-tag', adapter_version=ADAPTER, derived_from=paths))
        if any(v is None for v in values):
            return miss()
        try:
            value = convert(*values)
        except (ValueError, InvalidOperation):
            value = None
        if value is None:
            issues.append(ExtractionIssue(code='UNPARSEABLE_XML_VALUE', message=f'Unreadable value at {paths[0]}.'))
            return miss()
        return FieldObject(value=value, status='PRESENT', confidence_basis='DETERMINISTIC', source='xml',
                           provenance=Provenance(method='xml-tag', adapter_version=ADAPTER, deterministic_policy_version=policy, derived_from=paths))

    def money(s):
        d = Decimal(s)
        return d if d.is_finite() else None

    def tax(s):
        return s if TAX_CODE.fullmatch(s) else None

    def day(s):
        return s if DATE.fullmatch(s) else None

    def cur(s):
        return s if re.fullmatch(r'[A-Z]{3}', s) else None

    text = lambda s: s  # noqa: E731
    f = inv.fields
    parties = Parties(
        seller=Party(name=make(f['seller_name'], text, 'name'), tax_id=make(f['seller_tax_id'], tax, 'tax'), address=make(f['seller_address'], text, 'addr')),
        buyer=Party(name=make(f['buyer_name'], text, 'name'), tax_id=make(f['buyer_tax_id'], tax, 'tax'), address=make(f['buyer_address'], text, 'addr')))
    invoice = Invoice(number=make(f['number'], text, 'n'), series=make((f['template'], f['symbol']), lambda a, b: a + b, 's'),
                      issue_date=make(f['issue_date'], day, 'd'))
    totals = Totals(net=make(f['net_total'], money, 'n'), vat=make(f['vat_total'], money, 'v'), gross=make(f['gross_total'], money, 'g'))
    currency = make(f['currency'], cur, 'c')
    return parties, invoice, totals, currency, issues


def _item(inv, row, item_id, number):
    policy = inv.fidelity_policy

    def fo(key, convert, status_if_empty='MISSING'):
        xf = row[key]
        prov = lambda **k: Provenance(method='xml-tag', adapter_version=ADAPTER, derived_from=(xf.xpath,), **k)  # noqa: E731
        if xf.value is None:
            return FieldObject(status=status_if_empty, source='xml', provenance=prov())
        try:
            value = convert(xf.value)
        except (ValueError, InvalidOperation):
            value = None
        if value is None:
            return FieldObject(status='MISSING', source='xml', provenance=prov())
        return FieldObject(value=value, status='PRESENT', confidence_basis='DETERMINISTIC', source='xml',
                           provenance=prov(deterministic_policy_version=policy))

    rate_text = row['rate'].value
    prov = Provenance(method='xml-tag', adapter_version=ADAPTER, derived_from=(row['rate'].xpath,))
    if rate_text in ('KCT', 'KKKNT'):
        treatment = FieldObject(value=rate_text, status='PRESENT', confidence_basis='DETERMINISTIC', source='xml',
                                provenance=prov.model_copy(update={'deterministic_policy_version': policy}))
        rate = FieldObject(status='NOT_APPLICABLE', source='xml', provenance=prov)
    elif rate_text and re.fullmatch(r'\d{1,2}(?:\.\d+)?%', rate_text):
        treatment = FieldObject(value='TAXABLE_RATE', status='PRESENT', confidence_basis='DETERMINISTIC', source='xml',
                                provenance=prov.model_copy(update={'deterministic_policy_version': policy}))
        rate = FieldObject(value=Decimal(rate_text[:-1]) / 100, status='PRESENT', confidence_basis='DETERMINISTIC', source='xml',
                           provenance=prov.model_copy(update={'deterministic_policy_version': policy}))
    else:
        treatment = FieldObject(status='MISSING', source='xml', provenance=prov)
        rate = FieldObject(status='MISSING', source='xml', provenance=prov)
    dec = lambda s: Decimal(s)  # noqa: E731
    return Item(item_id=item_id, line_number=number, description=fo('description', lambda s: s), quantity=fo('quantity', dec),
                unit_price=fo('unit_price', dec), net=fo('net', dec), vat_treatment=treatment, vat_rate=rate)


def canonicalize_xml(raw, master, profile, identity, *, tenant_id, taxpayer_id, ingestion_id, source_id, document_id, input_sha256,
                     record_id, artifact_id, created_at, extractor_sha256, relations=(), extra_issues=()):
    inv = extract(raw, today=created_at.date())
    if (tenant_id, taxpayer_id) != (master.tenant_id, master.taxpayer_id):
        raise ValueError('document/master scope mismatch')
    if {e.anchor_id for e in identity.entries} != set(anchors(raw)):
        raise ValueError('identity map does not cover current row anchors')
    ids = {e.anchor_id: e.item_id for e in identity.entries}
    parties, invoice, totals, currency, issues = _fields(inv)
    items = tuple(_item(inv, row, ids[row_anchor(i)], i) for i, row in enumerate(inv.items, 1))
    for check in inv.checks:
        if check.status in ('ERROR', 'WARN'):
            issues.append(ExtractionIssue(code=check.code, message=check.note or check.code))
        elif check.status == 'UNCHECKED':
            issues.append(ExtractionIssue(code=check.code.replace('XML_CHECK_', 'XML_UNCHECKED_'), message=check.note or check.code))
    issues.extend(extra_issues)  # observations made against stored state (duplicates) are explicit replay inputs
    record = CanonicalFinancialRecord(
        config_version=profile.version, creator=ADAPTER, stage='canonicalization', created_at=created_at, record_id=record_id, revision=1,
        tenant_id=tenant_id, taxpayer_id=taxpayer_id, taxpayer_master_revision=master.revision, source_id=source_id,
        source_format=SourceFormat.INVOICE_XML, record_type='INVOICE', document_id=document_id, parties=parties, invoice=invoice,
        currency=currency, totals=totals, items=items, item_discovery_status='COMPLETE' if items else 'UNKNOWN',
        derived=Derived(invoice_direction=derived_field(None, (), 'AMBIGUOUS')))
    record, manifest, more = rederive(record, master, profile, relations)
    issues.extend(more)
    return ExtractionArtifact(
        config_version=profile.version, creator=ADAPTER, stage='extraction', created_at=created_at, artifact_id=artifact_id,
        tenant_id=tenant_id, taxpayer_id=taxpayer_id, ingestion_id=ingestion_id, source_id=source_id, document_id=document_id,
        input_sha256=input_sha256, normalized_input_sha256=input_sha256, extractor_sha256=extractor_sha256, profile=profile,
        segmentation=Segmentation(status='SINGLE_CANDIDATE', page_groups=(), reason='Single structured XML invoice; no page layout.'),
        record=record, candidates=(), identity_map=identity, vat_groups=build_groups(items, record.item_discovery_status),
        derivation=manifest, issues=tuple(issues))


__all__ = ['XML_OCR_KEY', 'anchors', 'canonicalize_xml', 'sha']
