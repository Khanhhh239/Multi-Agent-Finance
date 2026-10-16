"""Rebuild curated legal excerpts from reviewed transcriptions and pinned official PDFs."""
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from datetime import date
import pymupdf

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP))
from src.explanation_v2.contracts import Corpus,Chunk
from src.explanation_v2.cli import inspect
from src.legal_registry.registry import load_registry
from src.canonicalization.derive import sha

ASSETS=APP/'configs/explanation/legal_sources'
LOCAL=APP/'data/plan12_legal_corpus'
OUT=ROOT/'docs/agent3/plans/evidence/plan12/legal_corpus_20261016'
CORPUS=APP/'configs/explanation/corpus_20261016_v1.json'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def build():
    registry=load_registry();docs={d.document_id:d for d in registry.documents}
    review=json.loads((ASSETS/'transcriptions_20261016.json').read_text(encoding='utf-8'))
    references=json.loads((ASSETS/'reference_candidates_20261016.json').read_text(encoding='utf-8'))
    refresh=json.loads((LOCAL/'source_refresh.json').read_text(encoding='utf-8'))
    if refresh['registry_version']!=registry.version or refresh['checked_on']!=review['checked_on']:
        raise ValueError('Refresh registry/date mismatch')
    if any(d['status']!='MATCHED_PINNED_PRIMARY_PDF' for d in refresh['documents']):
        raise ValueError('Official refresh incomplete; do not silently use old cache')
    chunks=[];provenance=[];reference_chunks=[]
    for section,active in ((review,True),(references,False)):
        for entry in section['provisions']:
            doc=docs[entry['document_id']]
            path=LOCAL/'sources'/(doc.document_id+'.pdf')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=doc.sha256:
                raise ValueError('Pinned source bytes differ: '+doc.document_id)
            text='\n'.join(entry['paragraphs'])
            if unicodedata.normalize('NFC',text)!=text or '\ufffd' in text:
                raise ValueError('Transcription encoding/normalization invalid')
            pages=[]
            with pymupdf.open(path) as pdf:
                for number in entry['source_pages']:
                    if not 1<=number<=len(pdf):raise ValueError('Invalid PDF page')
                    image=pdf[number-1].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).tobytes('png')
                    target=LOCAL/'review'/(doc.document_id+'-p'+str(number)+'.png')
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(image)
                    pages.append(dict(pdf_page_1based=number,image_sha256=hashlib.sha256(image).hexdigest()))
            item=dict(chunk_id=entry['chunk_id'],document_id=doc.document_id,
                      document_sha256=doc.sha256,text_sha256=hashlib.sha256(text.encode()).hexdigest(),text=text,
                      effective_from=doc.effective_from.isoformat(),effective_to=doc.effective_to.isoformat() if doc.effective_to else None,
                      provision_locator=entry['provision_locator'],source_pages=entry['source_pages'])
            for name in ('provision_from','provision_to','scope_note','required_context'):
                if name in entry:item[name]=entry[name]
            if active:
                if doc.source_status!='PDF_REVIEWED' or entry['locator'] not in doc.verified_locators:
                    raise ValueError('Runtime entry bypasses locator gate')
                item.update(locator=entry['locator'],reviewed=True)
                chunks.append(Chunk.model_validate(item))
            else:
                item.update(publication='REFERENCE_ONLY_NOT_RUNTIME',official_pdf_url=doc.pdf_url)
                reference_chunks.append(item)
            provenance.append(dict(chunk_id=entry['chunk_id'],document_id=doc.document_id,
                official_pdf_url=doc.pdf_url,document_sha256=doc.sha256,text_sha256=item['text_sha256'],
                provision_locator=entry['provision_locator'],pages=pages,runtime=active,
                review_method=review['review_method'],reviewer='Codex visual source comparison',
                independent_legal_approval=False,signature_verification='NOT_PERFORMED',
                line_reflow_only=True))
    corpus=Corpus(version='legal-excerpts-20261016-v1',registry_version=registry.version,
                  validated_through=date.fromisoformat(review['checked_on']),chunks=tuple(chunks))
    write(CORPUS,corpus.model_dump(mode='json'))
    write(ASSETS/'reference_packet_20261016.json',dict(publication='REFERENCE_ONLY_NOT_RUNTIME',
          registry_version=registry.version,checked_on=review['checked_on'],chunks=reference_chunks))
    write(OUT/'source_manifest.json',dict(**refresh,provenance=provenance,
          renderer=dict(package='PyMuPDF',version=pymupdf.VersionBind,scale=1.4,page_numbering='physical PDF, 1-based'),
          source_refresh_sha256=sha(refresh),registry_sha256=sha(registry.model_dump(mode='json'))))
    rules=json.loads((APP/'rules/registry/ruleset_v1.json').read_text(encoding='utf-8'))
    available={(c.document_id,c.locator) for c in chunks}
    coverage=[]
    for family in rules['families']:
        for version in family['versions']:
            bases=version['legal_basis']
            missing=[b for b in bases if (b['document_id'],b['locator']) not in available]
            coverage.append(dict(rule_id=version['rule_id'],rule_version=version['version'],
                effective_from=version['effective_from'],effective_to_exclusive=version['effective_to'],
                publication=version['publication'],covered_bases=[b for b in bases if b not in missing],
                missing_bases=missing,all_selected_locators_have_excerpts=not missing,
                legal_approval='PENDING',current_date_outside_version=date(2026,10,16)>=date.fromisoformat(version['effective_to'])))
    write(OUT/'rule_coverage.json',dict(checked_on=review['checked_on'],ruleset_version=rules['version'],
          notice='Locator coverage only; not legal accuracy or approval. Current rule support ends before 2026-10-15.',versions=coverage))
    manifest=dict(checked_on=review['checked_on'],corpus_version=corpus.version,
                  registry_version=registry.version,corpus_sha256=sha(corpus.model_dump(mode='json')),
                  runtime_chunks=len(chunks),runtime_documents=len({c.document_id for c in chunks}),
                  reference_only_chunks=len(reference_chunks),primary_pdfs_refreshed=len(refresh['documents']),
                  selected_rule_versions=len(coverage),versions_with_all_locators=sum(not c['missing_bases'] for c in coverage),
                  legal_accuracy='NOT_ESTIMATED',independent_legal_approval=False,
                  source_currency_search='TARGETED_PRIMARY_SOURCES_NOT_EXHAUSTIVE',
                  limitations=['No automatic legal approval','No full ND174 or ND254 appendix taxonomy',
                               'Historical PENDING_REVIEW locators remain blocked','No XML/signature verification',
                               'Existing ruleset ends 2026-10-15 exclusive; corpus does not extend rule dates'])
    write(OUT/'corpus_manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=True,indent=2))
    return corpus


if __name__=='__main__':build()
