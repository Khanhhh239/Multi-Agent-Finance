"""Download bounded public evidence PDFs locally; no invoice data enters fixtures."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data invoice/real_invoice_pilot_v1'
SOURCES = {
    'charity_2023': 'https://hpcmn-bucket.s3.ap-southeast-1.amazonaws.com/Chung_Tu_T12_2023_5e840a3a6b.pdf',
    'misa_kimthanh': 'https://imda.moh.gov.vn/documents/10182/60780527/upload_00012440_1731552552535.pdf?fileId=60786824&version=1.0',
    'misa_asiatech': 'https://imda.moh.gov.vn/documents/10182/62377011/upload_00004237_1734407528873.pdf?fileId=62389470&version=1.0',
    'thanh_an': 'https://imda.moh.gov.vn/documents/10182/62377011/upload_00004322_1734407951030.pdf?fileId=62390118&version=1.0',
    'viettel_adjustment': 'https://congdongketoan.vn/attachments/k24taa18525-pdf.21737/',
    'cyber_construction': 'https://xaydungdaitruongphuc.com/upload/file/hsnl-2024-7320-1767.pdf',
    'software_kct': 'https://file.hstatic.net/1000139524/file/20230516667_0fffb8d703ca4bd886d3971797539a44.pdf',
    'misa_public_filing': 'https://shtp.hochiminhcity.gov.vn/Portals/0/Uploads/2026/1/20260128133037046.pdf',
    'accounting_training': 'https://hocketoanthuchanh.com/wp-content/uploads/2024/12/HDDT-BCT-DOANH-NGHIEP-Q2.25-CHUAN.pdf',
}


def main():
    import pymupdf
    DEST.mkdir(parents=True, exist_ok=True)
    manifest=[]
    for name,url in SOURCES.items():
        row=dict(source_id=name,url=url)
        path=DEST/(name+'.pdf')
        try:
            if not path.exists():
                request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
                with urllib.request.urlopen(request, timeout=35) as response:
                    data=response.read(64*1024*1024+1)
                if len(data)>64*1024*1024 or not data.startswith(b'%PDF-'):
                    raise ValueError('Not a PDF or larger than 64 MiB')
                path.write_bytes(data)
            row.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
            with pymupdf.open(path) as pdf:
                row['pages']=len(pdf)
                # Charity collection also contains medical documents: select
                # only the two telecom invoices, never medical pages.
                indices=range(min(2,len(pdf))) if name=='charity_2023' else range(len(pdf))
                row['page_inventory']=[]
                for i in indices:
                    text=pdf[i].get_text()
                    invoice=('HÓA ĐƠN' in text.upper() or 'HOÁ ĐƠN' in text.upper())
                    row['page_inventory'].append(dict(page=i+1,characters=len(text),invoice_keyword=invoice))
                    if invoice:
                        folder=DEST/'cases';folder.mkdir(exist_ok=True)
                        case=name+'-p'+str(i+1)
                        with pymupdf.open() as single:
                            single.insert_pdf(pdf,from_page=i,to_page=i)
                            target=folder/(case+'.pdf')
                            if not target.exists(): single.save(target)
                        (folder/(case+'.txt')).write_text(text,encoding='utf-8')
                        pdf[i].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(folder/(case+'.png'))
            row['status']='DOWNLOADED'
        except Exception as error:
            row.update(status='UNAVAILABLE',error=type(error).__name__)
        manifest.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='page_inventory'}),flush=True)
        (DEST/'sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__': main()
