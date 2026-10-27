"""Select document/invoice contents available at a transaction's scoring cutoff.

Undated final scalar values are not evidence of availability. A dated scalar
snapshot is a fallback; known typed revisions take precedence, including clears.
"""
from collections import defaultdict

from .temporal_evidence import bank_token


AMOUNTS = ('invoice_gross_vnd', 'invoice_net_vnd', 'invoice_vat_vnd', 'linked_input_vat_vnd')


class FeatureEvidence:
    def __init__(self, documents, employee_history):
        self.staff = employee_history
        bindings, versions = {}, {}
        for record in documents:
            key = record['company_id'], record['record_id']
            if not record['record_id']:
                raise ValueError('Empty feature document record_id')
            binding = (record['vendor_id'], record['transaction_id'], record['document_type'],
                       bank_token(record.get('invoice_number')), record.get('invoice_id', ''))
            if key in bindings and bindings[key] != binding:
                raise ValueError(f'Feature evidence binding changed: {key}')
            bindings[key] = binding
            version = key, record['observed_at']
            if version in versions and versions[version] != record:
                raise ValueError(f'Conflicting feature evidence revision: {version}')
            versions[version] = record
        self.rows = sorted(versions.values(), key=lambda r: (r['observed_at'], r['company_id'], r['record_id']))
        self.index = 0
        self.known = defaultdict(dict)

    def advance(self, now):
        while self.index < len(self.rows) and self.rows[self.index]['observed_at'] <= now:
            record = self.rows[self.index]
            self.known[(record['company_id'], record['transaction_id'])][record['record_id']] = record
            self.index += 1

    def verified_receipt(self, record, row, now):
        verified = record.get('verified_at', '')
        verifier = self.staff.employee_at(record.get('verifier_id'), verified)
        return bool(record['document_type'] in {'goods_receipt', 'service_acceptance'}
                    and record['status'] == 'verified' and record.get('evidence_id')
                    and verified and verified <= record['observed_at'] <= now
                    and verifier and verifier['company_id'] == row['company_id']
                    and record['verifier_id'] != row['creator_id'])

    @staticmethod
    def invoice_matches(record, row):
        matched = False
        for field in ('invoice_number', 'invoice_id'):
            if record.get(field):
                left = bank_token(record[field]) if field == 'invoice_number' else record[field]
                right = bank_token(row.get(field)) if field == 'invoice_number' else row.get(field)
                if not right or left != right:
                    return False
                matched = True
        return matched

    def snapshot(self, row, now):
        result = dict(support_doc_count=0, goods_receipt_verified=0, support_docs_known=0,
                      evidence_on_file=0, invoice_known=0, invoice_components_known=0,
                      linked_input_vat_known=0, invoice_issued_at='', invoice_number='')
        result.update({name: 0 for name in AMOUNTS})
        observed = row.get('support_docs_observed_at', '')
        if observed and observed <= now:
            receipt_verified = row.get('goods_receipt_verified_at', observed)
            result.update(support_doc_count=int(row['support_doc_count']), support_docs_known=1,
                          goods_receipt_verified=int(bool(int(row['goods_receipt_verified']) and receipt_verified
                                                         and receipt_verified <= now)),
                          evidence_on_file=int(row.get('evidence_on_file', int(row['support_doc_count']) > 0)))
        records = [r for r in self.known.get((row['company_id'], row['transaction_id']), {}).values()
                   if r['vendor_id'] == row['vendor_id']]
        if records:
            active = [r for r in records if r.get('evidence_id') and r['status'] not in {'revoked', 'rejected'}]
            result.update(support_docs_known=1, support_doc_count=len(active), evidence_on_file=int(bool(active)),
                          goods_receipt_verified=int(any(self.verified_receipt(r, row, now) for r in active)))

        invoices = [r for r in records if r['document_type'] == 'invoice']
        if invoices:
            candidates = [r for r in invoices if r.get('evidence_id') and r['status'] not in {'revoked', 'rejected'}
                          and self.invoice_matches(r, row)
                          and r.get('invoice_issued_at') and r['invoice_issued_at'] <= now
                          and r.get('invoice_gross_vnd', '') != '']
            signatures = {tuple(r.get(k, '') for k in ('invoice_issued_at', *AMOUNTS)) for r in candidates}
            if len(signatures) > 1:
                raise ValueError('Conflicting available invoice amounts for transaction ' + row['transaction_id'])
            invoice = min(candidates, key=lambda r: r['record_id']) if candidates else None
        else:
            observed = row.get('invoice_observed_at', '')
            invoice = row if (observed and observed <= now and row.get('invoice_issued_at')
                              and row['invoice_issued_at'] <= now
                              and (row.get('invoice_id') or row.get('invoice_number'))) else None
        if invoice is not None:
            result.update(invoice_known=1, invoice_issued_at=invoice['invoice_issued_at'],
                          invoice_number=bank_token(invoice.get('invoice_number')),
                          invoice_components_known=int(all(invoice.get(k, '') != '' for k in ('invoice_net_vnd', 'invoice_vat_vnd'))),
                          linked_input_vat_known=int(invoice.get('linked_input_vat_vnd', '') != ''))
            result.update({name: int(invoice[name]) if invoice.get(name, '') != '' else 0 for name in AMOUNTS})
        return result
