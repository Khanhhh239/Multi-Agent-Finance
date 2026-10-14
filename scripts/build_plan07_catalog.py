"""Build PLAN_07 metadata from downloaded source hashes, never legal approval."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'agent3_tax_compliance/data/plan07/legal'
OUT=ROOT/'agent3_tax_compliance/rules/registry'


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def main():
    sources=json.loads((LOCAL/'manifest.json').read_text(encoding='utf-8'))
    documents=[]
    reviewed={'ND254_2026':['Article10.pdf21','Article43.pdf46','Article44.pdf46'],
              'ND181_2025':['Article26.pdf32-34'],'ND144_2026':['Article1.pdf1','Article4.pdf3','Article6.pdf3'],
              'TT91_2026':['Article25.pdf32']}
    for source in sources:
        item={k:source[k] for k in ('document_id','official_url','effective_from','signature_status')}
        item.update(pdf_url=source.get('pdf_url',source['official_url']) if source['status']=='DOWNLOADED' else None,
            sha256=source.get('sha256'),source_status='PDF_REVIEWED' if source['document_id'] in reviewed else 'PDF_DOWNLOADED' if source['status']=='DOWNLOADED' else 'UNAVAILABLE',
            verified_locators=reviewed.get(source['document_id'],[]),relationships=[],
            transitional_policy='MANUAL_REVIEW_REQUIRED_FOR_TRANSITIONAL_OR_EXCEPTION_CASES')
        documents.append(item)
    documents.append(dict(document_id='ND41_2022',official_url='https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf',
        effective_from='2022-06-20',sha256=None,source_status='REFERENCED_ONLY',verified_locators=[],relationships=[],
        transitional_policy='ONLY_ARTICLE_1_REPEAL_REFERENCED_IN_ND254_ARTICLE43'))
    for item in documents:
        if item['document_id']=='ND254_2026':
            item['relationships']=[dict(target_id=target,relation='SUPERSEDES',scope=scope,
                effective_from='2026-07-01',evidence_locator='Article43.pdf46') for target,scope in (
                ('ND123_2020','WHOLE_DOCUMENT'),('ND70_2025','WHOLE_DOCUMENT'),('ND41_2022','ARTICLE_1_ONLY'))]
        if item['document_id']=='ND144_2026':
            item['relationships']=[dict(target_id='ND181_2025',relation='AMENDS',scope='ARTICLE_4_PARTIAL_NOT_A_GLOBAL_REPLACEMENT',
                effective_from='2026-06-20',evidence_locator='Article1.pdf1'),
                dict(target_id='ND181_2025',relation='AMENDS',scope='ARTICLE_26_PARAGRAPH_2_G_DEFERRED_PAYMENT',
                effective_from='2026-06-20',evidence_locator='Article4.pdf3')]
        if item['document_id']=='TT91_2026':
            item['relationships']=[dict(target_id='TT32_2025',relation='SUPERSEDES',scope='WHOLE_DOCUMENT',
                effective_from='2026-07-01',evidence_locator='Article25.pdf32')]
    write(OUT/'legal_registry_v1.json',dict(version='legal-registry-20261014-v1',checked_on='2026-10-14',documents=documents))

    def requirement(path):return dict(path=path)
    def predicate(path,value):return dict(requirement=requirement(path),value=value)
    families=[]
    content=[]
    for version,start,end,bases in (
        ('content-2022-v1','2022-07-01','2025-06-01',[('ND123_2020','Article10.PENDING_REVIEW')]),
        ('content-2025-v1','2025-06-01','2026-07-01',[('ND123_2020','Article10.PENDING_REVIEW'),('ND70_2025','Article1.PENDING_REVIEW')]),
        ('content-2026-v1','2026-07-01','2026-10-15',[('ND254_2026','Article10.pdf21')])):
        content.append(dict(rule_id='INV_CONTENT_001',version=version,family='INVOICE_CONTENT',effective_from=start,effective_to=end,
            date_field='invoice.issue_date',unit_type='RECORD',publication='DRAFT',
            predicates=[predicate('context.invoice_kind','VAT')],required_fields=[],
            required_observations=[dict(field_path='parties.seller.tax_id',fidelity_policy='complete-content-v1')],
            legal_basis=[dict(document_id=d,locator=l) for d,l in bases]))
    families.append(dict(rule_id='INV_CONTENT_001',supported_from='2022-07-01',supported_to='2026-10-15',versions=content))
    cash=[]
    for version,start,end,bases in (
        ('payment-2025-v1','2025-07-01','2026-01-01',[('ND181_2025','Article26.pdf32-34')]),
        ('payment-2026a-v1','2026-01-01','2026-06-20',[('ND181_2025','Article26.pdf32-34'),('ND359_2025','AMENDMENT_SCOPE_PENDING')]),
        ('payment-2026b-v1','2026-06-20','2026-10-15',[('ND181_2025','Article26.pdf32-34'),('ND359_2025','AMENDMENT_SCOPE_PENDING'),('ND144_2026','Article4.pdf3')])):
        cash.append(dict(rule_id='VAT_NON_CASH_PAYMENT_001',version=version,family='PAYMENT_EVIDENCE',effective_from=start,effective_to=end,
            date_field='invoice.issue_date',unit_type='RECORD',publication='DRAFT',non_cash_policy='non-cash-scope-v1',inclusive_threshold='5000000',
            predicates=[predicate('derived.invoice_direction','INPUT'),predicate('context.vat_method','DEDUCTION'),
                        predicate('context.claim_input_vat',True),predicate('context.payment_case','STANDARD')],
            required_fields=[],legal_basis=[dict(document_id=d,locator=l) for d,l in bases]))
    families.append(dict(rule_id='VAT_NON_CASH_PAYMENT_001',supported_from='2025-07-01',supported_to='2026-10-15',versions=cash))
    families.append(dict(rule_id='VAT_RATE_001',supported_from='2025-07-01',supported_to='2026-10-15',versions=[dict(
        rule_id='VAT_RATE_001',version='vat-2025-2026-v1',family='VAT_RATE',effective_from='2025-07-01',effective_to='2026-10-15',
        date_field='invoice.issue_date',unit_type='ITEM',publication='DRAFT',
        legal_basis=[dict(document_id='ND174_2025',locator='Article1_APPENDICES_PENDING_REVIEW')],
        predicates=[predicate('context.invoice_kind','VAT')],required_fields=[requirement('item.vat_treatment'),requirement('item.vat_rate'),requirement('item.vat_category')])]))
    write(OUT/'ruleset_v1.json',dict(version='technical-draft-ruleset-20261014-v1',families=families))
    write(OUT/'taxonomy_v1.json',dict(version='vat-taxonomy-draft-v1',effective_from='2025-07-01',effective_to='2027-01-01',
        categories=[dict(category_id=identifier,description=description,
                        legal_basis=[dict(document_id='ND174_2025',locator='Article1_APPENDICES_PENDING_REVIEW')])
                    for identifier,description in (('REDUCTION_CANDIDATE','Needs independent goods/services classification and exception review'),
                                                   ('REDUCTION_EXCLUDED','Needs verified annex classification; never derive from printed rate'))],mappings=[]))
    for name,formats,supported,unsupported in (
        ('pdf_ocr_v1',['PDF','IMAGE'],['INVOICE_CONTENT','VAT_RATE'],['PAYMENT_EVIDENCE']),
        ('invoice_xml_v1',['INVOICE_XML'],['INVOICE_CONTENT','VAT_RATE'],['PAYMENT_EVIDENCE']),
        ('bank_v1',['BANK_STATEMENT'],['PAYMENT_EVIDENCE'],['INVOICE_CONTENT','VAT_RATE'])):
        adapter,version={'pdf_ocr_v1':('OCRDocumentAdapter','ocr-layout-v1'),
                         'invoice_xml_v1':('InvoiceXMLAdapter','proposed-xml-v1'),
                         'bank_v1':('BankStatementAdapter','proposed-bank-v1')}[name]
        write(OUT/'capability_profiles'/(name+'.json'),dict(profile_id=name,version='1.0.0',adapter_id=adapter,
            adapter_version=version,source_formats=formats,supported_families=supported,
            unsupported_families=unsupported,absence_fidelity_policies=[]))
    print('Built draft source/rule/taxonomy registry. No rules approved for production.')


if __name__=='__main__':main()
