"""Check local recognizer vocabularies without downloading models or invoices."""
import hashlib
import json
import unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MODELS=ROOT/'data invoice/ocr_e2e_workflow/artifacts/models'


def main():
    viet=MODELS/'vietocr/config/base.yml';paddle=MODELS/'ppocrv6_medium/recognition/inference.yml'
    vocab=next(line for line in viet.read_text(encoding='utf-8').splitlines() if line.startswith('vocab:'))
    required={c for c in unicodedata.normalize('NFC',vocab) if c.isalpha() and ord(c)>127}
    text=paddle.read_text(encoding='utf-8').split('  character_dict:',1)[1]
    characters=set(unicodedata.normalize('NFC',text))
    missing=sorted(required-characters)
    report={'scope':'Local character dictionary coverage, not learned recognition accuracy',
        'required_vietnamese_letters':len(required),'missing_count':len(missing),'missing':missing,
        'configs_sha256':{p.relative_to(MODELS).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (viet,paddle)},
        'production_accuracy_approved':False}
    out=ROOT/'agent3_tax_compliance/data/ocr_coverage_v1/charset_audit.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
