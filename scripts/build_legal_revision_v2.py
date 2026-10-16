"""Immutable v2 legal/catalog/model snapshots plus legacy compatibility-head files.

Calculation implementation is unchanged so previously pinned replay keeps working.
"""
import copy
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from datetime import date
import pymupdf

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP))
from src.legal_registry.registry import LegalRegistry
from src.planning.contracts import RuleSet
from src.taxonomy.service import Taxonomy
from src.explanation_v2.contracts import Corpus,Chunk
from src.canonicalization.derive import sha

REG=APP/'rules/registry';MODELS=APP/'rules/models'
ARCHIVE=REG/'versions/20261014-v1'
ASSETS=APP/'configs/explanation/legal_sources'
OUT=ROOT/'docs/agent3/plans/evidence/legal_revision_20261016_v2'
LOCAL=APP/'data/plan12_legal_corpus/sources'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


def freeze():
    pins={}
    for name,path in [('legal_registry_v1.json',REG/'legal_registry_v1.json'),('ruleset_v1.json',REG/'ruleset_v1.json'),
                      ('taxonomy_v1.json',REG/'taxonomy_v1.json'),('model_manifest_v1.json',MODELS/'manifest.json')]:
        target=ARCHIVE/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(path.read_bytes())
        pins[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    write(ARCHIVE/'byte_pins.json',pins)


def main():
    freeze()
    spec=read(ASSETS/'revision_20261016_v2.json')
    registry=read(ARCHIVE/'legal_registry_v1.json');registry.update(version='legal-registry-20261016-v2',checked_on=spec['checked_on'])
    docs={d['document_id']:d for d in registry['documents']}
    docs['ND123_2020'].update(source_status='PDF_REVIEWED',effective_to='2026-07-01',
        verified_locators=['Article10.4.pdf14','Article10.14de.pdf19'])
    docs['ND70_2025'].update(source_status='PDF_REVIEWED',effective_to='2026-07-01',
        verified_locators=['Article1.7a.pdf9','Article1.7d-dd.pdf11-12'])
    docs['TT32_2025']['effective_to']='2026-07-01'
    docs['ND174_2025'].update(source_status='PDF_REVIEWED',effective_to='2027-01-01',
        verified_locators=['Article1.1-2a.pdf1-2','Article2.1.pdf3','AppendixII.I.pdf73','AppendixII.II.pdf74-75'])
    docs['ND359_2025'].update(source_status='PDF_REVIEWED',verified_locators=['Article1.2.pdf2','Article2.1.pdf2'],relationships=[
        dict(target_id='ND181_2025',relation='AMENDS',scope='ARTICLE_4_PARAGRAPH_1B_ONLY',effective_from='2026-01-01',evidence_locator='Article1.pdf1-2'),
        dict(target_id='ND181_2025',relation='REPEALS',scope='ARTICLE_37_PARAGRAPH_3_AND_ARTICLE_39_PARAGRAPH_3',effective_from='2026-01-01',evidence_locator='Article1.2.pdf2')])
    # Source bytes are checked before source statuses are published.
    for doc in docs.values():
        if doc['source_status']=='PDF_REVIEWED':
            if hashlib.sha256((LOCAL/(doc['document_id']+'.pdf')).read_bytes()).hexdigest()!=doc['sha256']:
                raise ValueError('Government PDF differs from immutable source pin')
    LegalRegistry.model_validate(registry)
    oldcorpus=read(APP/'configs/explanation/corpus_20261016_v1.json')
    chunks=[]
    for row in oldcorpus['chunks']:
        row=copy.deepcopy(row);doc=docs[row['document_id']]
        row['effective_to']=doc.get('effective_to');chunks.append(row)
    packet=read(ASSETS/'reference_packet_20261016.json')
    locators={'REF-ND123-A10-4':'Article10.4.pdf14','REF-ND70-A1-7-a':'Article1.7a.pdf9',
              'REF-ND359-A1-2':'Article1.2.pdf2','REF-ND359-A2-1':'Article2.1.pdf2',
              'REF-ND174-A1-1-2a':'Article1.1-2a.pdf1-2','REF-ND174-A2-1':'Article2.1.pdf3'}
    for old in packet['chunks']:
        row={k:v for k,v in old.items() if k not in ('publication','official_pdf_url')}
        row.update(chunk_id=old['chunk_id'].replace('REF-','V2-'),locator=locators[old['chunk_id']],reviewed=True,required_context=True)
        row['effective_to']=docs[row['document_id']].get('effective_to')
        row['scope_note']='Trích đúng khoản/điểm ghi trong provision_locator; không phải toàn điều/văn bản. Không tự xác nhận phân loại hàng hóa hoặc đủ mọi điều kiện thuế.'
        chunks.append(row)
    for row in spec['extra_provisions']:
        doc=docs[row['document_id']];row=copy.deepcopy(row)
        text='\n'.join(row.pop('paragraphs'))
        row.update(document_sha256=doc['sha256'],text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                   effective_from=doc['effective_from'],effective_to=doc.get('effective_to'),reviewed=True)
        chunks.append(row)
    # Index every appendix page, retaining positions; never turn code/description into SKU mapping.
    annex=[]
    with pymupdf.open(LOCAL/'ND174_2025.pdf') as pdf:
        for page in range(5,78):
            raw=pdf[page-1].get_text();text=unicodedata.normalize('NFC',raw)
            annex.append(dict(pdf_page=page,annex='I' if page<=72 else 'II' if page<=75 else 'III',
                text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                words=[dict(box=list(w[:4]),text=w[4],block=w[5],line=w[6],word=w[7]) for w in pdf[page-1].get_text('words')]))
        for ident,locator,pages,start,end in (
            ('ND174-II-2025','AppendixII.I.pdf73',[73],'2025-07-01','2026-01-01'),
            ('ND174-II-2026','AppendixII.II.pdf74-75',[74,75],'2026-01-01','2027-01-01')):
            text='\n'.join(unicodedata.normalize('NFC',pdf[n-1].get_text()) for n in pages)
            chunks.append(dict(chunk_id=ident,document_id='ND174_2025',locator=locator,document_sha256=docs['ND174_2025']['sha256'],
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),text=text,effective_from='2025-07-01',effective_to='2027-01-01',
                provision_from=start,provision_to=end,source_pages=pages,provision_locator=locator,reviewed=True,required_context=True,
                scope_note='Text nguyên trang PDF, giữ tiêu đề Công báo. Áp dụng phụ lục theo đúng giai đoạn; chưa phải classification/mapping sản phẩm được duyệt. Phải xét cả ghi chú và pháp luật thuế tiêu thụ đặc biệt.'))
    write(ASSETS/'ND174_appendices_source_index_v2.json',dict(document_id='ND174_2025',document_sha256=docs['ND174_2025']['sha256'],
        official_pdf_url=docs['ND174_2025']['pdf_url'],pages=annex,extraction='NATIVE_TEXT_AND_WORD_POSITIONS',
        table_semantics_approved=False,product_mapping_approved=False,visual_review='BOUNDARIES_AND_SELECTED_PAGES_NOT_EVERY_ROW'))
    corpus=Corpus(version='legal-excerpts-20261016-v2',registry_version=registry['version'],validated_through=date(2026,10,16),
                  chunks=tuple(Chunk.model_validate(c) for c in chunks))
    rules=read(ARCHIVE/'ruleset_v1.json');rules['version']='technical-draft-ruleset-20261016-v2'
    cutoff=spec['support_to_exclusive']
    def basis(doc,locator):return dict(document_id=doc,locator=locator)
    for family in rules['families']:
        family['supported_to']=cutoff
        if family['rule_id']=='INV_CONTENT_001':
            for i,v in enumerate(family['versions']):
                v['version']=v['version'].replace('-v1','-v2')
                v['predicates'][0]['value']='VAT'
                v['legal_basis']=([basis('ND123_2020','Article10.4.pdf14'),basis('ND123_2020','Article10.14de.pdf19')]
                    + ([basis('ND70_2025','Article1.7a.pdf9'),basis('ND70_2025','Article1.7d-dd.pdf11-12')] if i==1 else [])) if i<2 else [basis('ND254_2026','Article10.pdf21')]
                if i==2:v['effective_to']=cutoff
        elif family['rule_id']=='VAT_NON_CASH_PAYMENT_001':
            before=copy.deepcopy(family['versions'][0]);after=copy.deepcopy(family['versions'][-1])
            before.update(version='payment-pre144-v2',effective_to='2026-06-20',legal_basis=[basis('ND181_2025','Article26.pdf32-34')])
            after.update(version='payment-post144-v2',effective_to=cutoff,legal_basis=[basis('ND181_2025','Article26.pdf32-34'),basis('ND144_2026','Article4.pdf3')])
            family['versions']=[before,after]
        else:
            original=family['versions'][0];family['versions']=[]
            for year,start,end,locator in [('2025','2025-07-01','2026-01-01','AppendixII.I.pdf73'),('2026','2026-01-01',cutoff,'AppendixII.II.pdf74-75')]:
                v=copy.deepcopy(original);v.update(version='vat-'+year+'-v2',effective_from=start,effective_to=end,
                    legal_basis=[basis('ND174_2025','Article1.1-2a.pdf1-2'),basis('ND174_2025',locator)])
                v['predicates'][0]['value']='VAT'
                v['predicates']+= [dict(requirement=dict(path=p),value=value) for p,value in (
                    ('context.vat_method','DEDUCTION'),('item.vat_treatment','TAXABLE_RATE'),('item.vat_category','REDUCTION_CANDIDATE'))]
                family['versions'].append(v)
    RuleSet.model_validate(rules)
    taxonomy=read(ARCHIVE/'taxonomy_v1.json');taxonomy['version']='vat-taxonomy-draft-v2'
    # Classification approval remains a separate gate. Source indexing is not classification.
    for category in taxonomy['categories']:
        category['legal_basis']=[basis('ND174_2025','APPENDIX_CLASSIFICATION_NOT_APPROVED')]
    Taxonomy.model_validate(taxonomy)
    package=read(ARCHIVE/'model_manifest_v1.json');originals=package['models'];models=[]
    for family in rules['families']:
        for rule in family['versions']:
            prefix='content' if rule['family']=='INVOICE_CONTENT' else 'payment' if rule['family']=='PAYMENT_EVIDENCE' else 'vat'
            original=next(m for m in originals if m['rule_version'].startswith(prefix))
            model=copy.deepcopy(original)
            model.update(model_id=rule['rule_id']+'.'+rule['version'],rule_version=rule['version'],
                         effective_from=rule['effective_from'],effective_to=rule['effective_to'],legal_basis=rule['legal_basis'])
            models.append(model)
    package.update(version='technical-draft-20261016-v2',models=models)
    # Immutable named snapshots + compatibility heads read by existing pinned loaders.
    for name,value,head in [('legal_registry_20261016_v2.json',registry,REG/'legal_registry_v1.json'),
                            ('ruleset_20261016_v2.json',rules,REG/'ruleset_v1.json'),
                            ('taxonomy_20261016_v2.json',taxonomy,REG/'taxonomy_v1.json')]:
        write(REG/name,value);write(head,value)
    write(MODELS/'manifest_20261016_v2.json',package);write(MODELS/'manifest.json',package)
    write(APP/'configs/explanation/corpus_20261016_v2.json',corpus.model_dump(mode='json'))
    available={(c.document_id,c.locator) for c in corpus.chunks}
    coverage=[dict(rule_id=v['rule_id'],version=v['version'],publication=v['publication'],from_date=v['effective_from'],
        to_exclusive=v['effective_to'],missing_bases=[b for b in v['legal_basis'] if (b['document_id'],b['locator']) not in available])
        for f in rules['families'] for v in f['versions']]
    write(OUT/'release_manifest.json',dict(checked_on=spec['checked_on'],support_to_exclusive=cutoff,
        support_policy=spec['support_policy'],legal_registry_version=registry['version'],ruleset_version=rules['version'],
        package_version=package['version'],taxonomy_version=taxonomy['version'],corpus_version=corpus.version,
        corpus_sha256=sha(corpus.model_dump(mode='json')),coverage=coverage,model_count=len(models),
        indexed_annex_pages=len(annex),taxonomy_mapping_count=len(taxonomy['mappings']),source_review_not_legal_approval=True,
        archive_byte_pins=read(ARCHIVE/'byte_pins.json'),mvp_scope=spec['mvp_scope']))
    print(json.dumps(dict(ruleset=rules['version'],models=len(models),corpus_chunks=len(chunks),missing_bases=sum(len(c['missing_bases']) for c in coverage)),ensure_ascii=True))


if __name__=='__main__':main()
