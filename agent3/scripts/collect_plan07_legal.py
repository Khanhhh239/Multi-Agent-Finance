"""Collect bounded official legal PDFs locally and pin bytes; never approve rules."""
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'agent3_tax_compliance/data/plan07/legal'
SOURCES={
 'ND123_2020':('2022-07-01','https://vanban.chinhphu.vn/default.aspx?docid=201365&pageid=27160'),
 'TT78_2021':('2022-07-01','https://vanban.chinhphu.vn/?classid=1&docid=204200&pageid=27160'),
 'ND70_2025':('2025-06-01','https://vanban.chinhphu.vn/?docid=213179&pageid=27160'),
 'TT32_2025':('2025-06-01','https://chinhphu.vn/?classid=1&docid=213855&pageid=27160'),
 'ND181_2025':('2025-07-01','https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/181nd.signed.pdf'),
 'ND174_2025':('2025-07-01','https://congbao.chinhphu.vn/tai-ve-van-ban-so-174-2025-nd-cp-45374-57334?format=pdf'),
 'ND359_2025':('2026-01-01','https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-359-2025-nd-cp-468511.htm'),
 'ND144_2026':('2026-06-20','https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/144-ndcp.signed.pdf'),
 'ND254_2026':('2026-07-01','https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf'),
 'TT91_2026':('2026-07-01','https://vanban.chinhphu.vn/?docid=219006&pageid=27160'),
 'L108_2025':('2026-07-01','https://chinhphu.vn/?classid=1&docid=216541&pageid=27160'),
}


def fetch(url):
    host=urllib.parse.urlparse(url).hostname or ''
    if not (host=='chinhphu.vn' or host.endswith('.chinhphu.vn') or host=='g7.cdnchinhphu.vn'):
        raise ValueError('Only official government hosts allowed')
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(request,timeout=30) as response:
        data=response.read(24*1024*1024+1)
    if len(data)>24*1024*1024:raise ValueError('Oversized legal source')
    return data


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    previous={r['document_id']:r for r in json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))} if (DEST/'manifest.json').exists() else {}
    rows=[]
    for name,(effective,url) in SOURCES.items():
        row=dict(document_id=name,effective_from=effective,official_url=url,
                 signature_status='NOT_VERIFIED',approval='PENDING_LEGAL_REVIEW')
        target=DEST/(name+'.pdf')
        if previous.get(name,{}).get('pdf_url'):row['pdf_url']=previous[name]['pdf_url']
        try:
            if target.exists():raw=target.read_bytes()
            else:
                raw=fetch(url)
                if not raw.startswith(b'%PDF-'):
                    html=raw.decode('utf-8',errors='replace')
                    links=re.findall(r'(?:href|src)=[\"\']([^\"\']+\.pdf(?:\?[^\"\']*)?)[\"\']',html,re.I)
                    links=[urllib.parse.urljoin(url,x.replace('&amp;','&')) for x in links]
                    if not links:raise ValueError('Official PDF link unavailable')
                    row['pdf_url']=links[0];raw=fetch(links[0])
                if not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF')
                target.write_bytes(raw)
            row.update(status='DOWNLOADED',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        except Exception as exc:row.update(status='UNAVAILABLE',error=type(exc).__name__)
        rows.append(row)
        (DEST/'manifest.json').write_bytes(json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8'))
        print(json.dumps(row,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
