"""Fetch explicitly listed public invoice PDFs, with size limits and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone
import urllib.request
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCES=(
 ('unity','https://vimda.moh.gov.vn/documents/10182/62377011/upload_00004358_1734408046846.pdf?fileId=62390182&version=1.0'),
 ('imall','https://vimda.moh.gov.vn/documents/10182/50949818/upload_00015326_1704528822612.pdf?fileId=50958461&version=1.0'),
 ('micro_precision','https://vimda.moh.gov.vn/documents/10182/64159384/upload_00006298_1738858155355.pdf?fileId=64192534&version=1.0'),
 ('khang_vu','https://vimda.moh.gov.vn/documents/10182/64159384/upload_00006493_1738858911435.pdf?fileId=64192910&version=1.0'),
)


def download(url,path):
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request,timeout=45) as response:
            return response.read(15*1024*1024+1),response.url,'python-verified-tls'
    except urllib.error.URLError:
        # Python's CA bundle can differ from the Windows trust store. Curl's
        # Schannel backend still verifies TLS; never use insecure/cert bypass.
        curl=shutil.which('curl.exe')
        if not curl:raise
        result=subprocess.run([curl,'--location','--fail','--silent','--show-error','--max-time','45',
            '--max-filesize','15728640','--output',str(path),'--write-out','%{url_effective}',url],
            capture_output=True,text=True,timeout=55)
        if result.returncode:raise ValueError('Verified HTTPS download failed: '+result.stderr.strip()[:200])
        return path.read_bytes(),result.stdout.strip(),'windows-verified-tls'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'invoice_test'):raise ValueError('Downloads must stay inside ignored invoice_test')
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for name,url in SOURCES:
        record={'case_source':name,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
        try:
            raw,final_url,transport=download(url,out/(name+'.part'))
            record.update(final_url=final_url,transport=transport)
            if len(raw)>15*1024*1024 or not raw.startswith(b'%PDF'):raise ValueError('Not a bounded PDF')
            path=out/(name+'.pdf');path.write_bytes(raw)
            record.update(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),state='DOWNLOADED')
        except Exception as error:
            record.update(state='FAILED',error_type=type(error).__name__,reason=str(getattr(error,'reason',error))[:300])
        rows.append(record)
        (out/'sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(name,record['state'],record.get('reason',''),flush=True)
    return int(any(r['state']!='DOWNLOADED' for r in rows))


if __name__=='__main__':raise SystemExit(main())
