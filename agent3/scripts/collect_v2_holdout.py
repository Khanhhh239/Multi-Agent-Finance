"""Stage new public sources without extracting text or tuning on their content.

Provider/template is a search hint, not verified ground truth. Raw files stay local.
"""
import hashlib
import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'bkav_calibration': 'https://imda.moh.gov.vn/documents/10182/64159384/upload_00006298_1738858155355.pdf?fileId=64192534&version=1.0',
    'bkav_2021': 'https://vimda.moh.gov.vn/documents/10182/18068938/upload_00094301_1610012997130.pdf?fileId=18077451&version=1.0',
    'minvoice_public_filing': 'https://www.hhtip.hanoi.gov.vn/media/thong-bao-tuyen-dung/2025_08/bao-cao-cap-lai-gpmt-parker-2-298.pdf',
}


def main():
    import re
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.run_id):
        parser.error('plain run-id required')
    DEST = ROOT / 'data invoice/ocr_extraction_v2' / args.run_id
    if DEST.exists():
        raise SystemExit('Frozen collection already exists; do not overwrite')
    DEST.mkdir(parents=True)
    rows = []
    for name, url in SOURCES.items():
        row = dict(case=name, url=url, split='HOLDOUT_CANDIDATE_NOT_VALIDATED',
                   template_status='UNVERIFIED', labels_status='PENDING',
                   data_rights='PUBLICLY_RETRIEVABLE_NOT_A_REDISTRIBUTION_LICENSE',
                   source_text_extracted=False)
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(48 * 1024 * 1024 + 1)
            if len(raw) > 48 * 1024 * 1024 or not raw.startswith(b'%PDF-'):
                raise ValueError('Not a bounded PDF')
            (DEST / (name + '.pdf')).write_bytes(raw)
            row.update(status='STAGED_UNOPENED', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        except Exception as exc:
            row.update(status='UNAVAILABLE', error=type(exc).__name__)
        rows.append(row)
        (DEST / 'manifest.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
