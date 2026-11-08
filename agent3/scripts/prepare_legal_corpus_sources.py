"""Refresh government PDFs into a local cache, comparing against immutable registry hashes."""
import argparse
import concurrent.futures
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
OUT=APP/'data/plan12_legal_corpus'


def download(doc):
    url=doc.get('pdf_url')
    if not url:return dict(document_id=doc['document_id'],status='NO_PRIMARY_PDF_URL')
    target=OUT/'sources'/(doc['document_id']+'.pdf')
    result=dict(document_id=doc['document_id'],url=url,expected_sha256=doc['sha256'],
                checked_at=datetime.now(timezone.utc).isoformat())
    try:
        initial=urlparse(url);host=initial.hostname or ''
        if initial.scheme!='https' or not (host=='chinhphu.vn' or host.endswith('.chinhphu.vn')):
            raise ValueError('Primary HTTPS government PDF required')
        request=Request(url,headers={'User-Agent':'Agent3-LegalCorpus/1.0'})
        with urlopen(request,timeout=30) as response:
            final=response.url;host=urlparse(final).hostname or ''
            if urlparse(final).scheme!='https' or not (host=='chinhphu.vn' or host.endswith('.chinhphu.vn')):
                raise ValueError('Redirect outside government source')
            raw=response.read(30*1024*1024+1)
            if len(raw)>30*1024*1024 or not raw.startswith(b'%PDF'):
                raise ValueError('Not a bounded PDF')
        digest=hashlib.sha256(raw).hexdigest()
        result.update(final_url=final,sha256=digest,bytes=len(raw))
        if digest!=doc['sha256']:
            result['status']='HASH_MISMATCH_QUARANTINED'
            target=target.with_name(doc['document_id']+'.quarantine.pdf')
        else:result['status']='MATCHED_PINNED_PRIMARY_PDF'
        target.write_bytes(raw)
    except Exception as exc:
        result.update(status='DOWNLOAD_FAILED',error_type=type(exc).__name__)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    OUT.joinpath('sources').mkdir(parents=True,exist_ok=True)
    registry=json.loads((APP/'rules/registry/legal_registry_v1.json').read_text(encoding='utf-8'))
    docs=[d for d in registry['documents'] if d.get('pdf_url')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(download,docs))
    report=dict(checked_on=datetime.now(timezone(timedelta(hours=7))).date().isoformat(),registry_version=registry['version'],documents=results)
    path=OUT/'source_refresh.json';path.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if all(r['status']=='MATCHED_PINNED_PRIMARY_PDF' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
