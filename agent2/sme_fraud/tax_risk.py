"""Versioned tax-authority risk list, imported without a live portal dependency."""
import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse


SCHEMA = json.loads(Path(__file__).with_name('tax_risk_sources.schema.json').read_text(encoding='utf-8'))
FIELDS = tuple(SCHEMA['required'])
VN = timezone(timedelta(hours=7))


def tax_code(value):
    """Normalize formatting only; a branch MST never matches its parent MST."""
    if not isinstance(value, str):
        return ''
    value = re.sub(r'[\s.\-]', '', value)
    return value if re.fullmatch(r'(?:[0-9]{10}|[0-9]{13})', value) else ''


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('tax risk timestamps require an explicit timezone')
    return parsed.astimezone(VN).isoformat()


def validated(record):
    if set(FIELDS) - record.keys():
        raise ValueError(f'Incomplete tax risk schema: {sorted(set(FIELDS) - record.keys())}')
    # Only source-contract columns may reach detector evidence; unrelated ERP
    # exports can contain labels or predictions that must never reach reviewers.
    row = {field: record[field] for field in FIELDS}
    for field in FIELDS:
        if not isinstance(row[field], str) or row[field] != row[field].strip():
            raise ValueError(f'Invalid tax risk field: {field}')
        if not row[field] and field != 'effective_to':
            raise ValueError(f'Missing tax risk evidence: {field}')
    row['tax_code'] = tax_code(row['tax_code'])
    if not row['tax_code'] or row['status'] not in SCHEMA['status']:
        raise ValueError('Invalid tax risk MST/status')
    for field in ('effective_from', 'effective_to'):
        if row[field]:
            if date.fromisoformat(row[field]).isoformat() != row[field]:
                raise ValueError('Tax risk effective dates require YYYY-MM-DD')
    if row['effective_to'] and row['effective_to'] <= row['effective_from']:
        raise ValueError('Invalid tax risk effective interval')
    for field in ('published_at', 'observed_at'):
        row[field] = timestamp(row[field])
    if row['published_at'] > row['observed_at']:
        raise ValueError('Tax source cannot be observed before publication')
    url = urlparse(row['source_url'])
    if (url.scheme != 'https' or not (url.hostname or '').endswith('.gov.vn')
            or url.username or url.password or url.port not in (None, 443)):
        raise ValueError('Tax risk source must reference an HTTPS government URL')
    if not re.fullmatch(r'[0-9a-f]{64}', row['source_sha256']):
        raise ValueError('Tax risk evidence requires a source document SHA-256')
    return row


class TaxRiskHistory:
    def __init__(self, rows):
        self.records = defaultdict(list)
        versions, bindings = {}, {}
        for raw in rows:
            row = validated(raw)
            identity = row['record_id']
            binding = (row['company_id'], row['tax_code'])
            if identity in bindings and bindings[identity] != binding:
                raise ValueError('A tax risk record cannot change company/MST between revisions')
            bindings[identity] = binding
            key = identity, row['observed_at']
            if key in versions and versions[key] != row:
                raise ValueError('Conflicting tax risk revisions at one observation time')
            versions[key] = row
        for row in versions.values():
            self.records[(row['company_id'], row['tax_code'])].append(row)

    def invoice_check(self, row, vendor, now):
        if not row.get('invoice_issued_at') or not (row.get('invoice_id') or row.get('invoice_number')):
            return None
        # An invoice issuer supplied by ERP takes precedence over vendor master.
        code = tax_code(row.get('invoice_issuer_tax_code') or vendor.get('tax_code', ''))
        if not code:
            return None
        cutoff = timestamp(now)
        issued_at = timestamp(row['invoice_issued_at'])
        if issued_at > cutoff:
            return None
        issued_day = issued_at[:10]
        latest = {}
        for record in sorted(self.records.get((row['company_id'], code), []),
                             key=lambda r: (r['observed_at'], r['record_id'])):
            if record['observed_at'] <= cutoff and record['published_at'] <= cutoff:
                latest[record['record_id']] = record
        matches = [r for r in latest.values() if r['status'] == 'high_risk'
                   and r['effective_from'] <= issued_day
                   and (not r['effective_to'] or issued_day < r['effective_to'])]
        if not matches:
            return None
        return dict(evidence_status='tax_authority_list_match', issuer_tax_code=code,
                    invoice_id=row.get('invoice_id', ''), invoice_issued_at=row['invoice_issued_at'],
                    source_records=sorted(matches, key=lambda r: r['record_id']),
                    risky_at_invoice=1, requires_verification=True,
                    conclusion='MST người phát hành thuộc danh sách rủi ro tại ngày hóa đơn; cần rà soát chứng từ.')


def import_list(source, document, output, *, url, document_id, observed_at):
    """Bind normalized CSV rows to an archived original tax authority document."""
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    with source.open(encoding='utf-8-sig', newline='') as stream:
        rows = [validated(dict(r, source_url=url, source_document_id=document_id,
                               source_sha256=digest, observed_at=observed_at))
                for r in csv.DictReader(stream)]
    TaxRiskHistory(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: r[k] for k in FIELDS} for r in rows)
    return dict(records=len(rows), source_sha256=digest, output=str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-document', type=Path, required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--document-id', required=True)
    parser.add_argument('--observed-at', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(import_list(args.source, args.source_document, args.output,
                                url=args.source_url, document_id=args.document_id,
                                observed_at=args.observed_at), ensure_ascii=False))


if __name__ == '__main__':
    main()
