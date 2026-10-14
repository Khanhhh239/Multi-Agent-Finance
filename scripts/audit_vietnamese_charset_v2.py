"""Preflight the actual local exported recognizer dictionary, never mutate it."""
import hashlib
import argparse
import json
import string
import unicodedata
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'data invoice/ocr_e2e_workflow/artifacts/models/ppocrv6_medium/recognition'


def main():
    import re
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.run_id):
        parser.error('plain run-id required')
    OUT = ROOT / 'data invoice/ocr_extraction_v2' / args.run_id
    if OUT.exists():
        raise SystemExit('Frozen audit already exists')
    OUT.mkdir(parents=True)
    payload = yaml.safe_load((MODEL / 'inference.yml').read_text(encoding='utf-8'))
    characters = payload.get('PostProcess', {}).get('character_dict')
    if not isinstance(characters, list):
        raise ValueError('Export does not embed a dictionary; manual artifact check needed')
    alphabet = set(string.ascii_letters + string.digits + '-/.,:%() ' + 'đĐ')
    for vowel in 'aăâeêioôơuưyAĂÂEÊIOÔƠUƯY':
        for tone in ('', '\u0300', '\u0301', '\u0303', '\u0309', '\u0323'):
            alphabet.update(unicodedata.normalize('NFC', vowel + tone))
    # Use the actual installed decoder: it appends space outside exported dict.
    from paddlex.inference.models.text_recognition.processors import CTCLabelDecode
    decoder = CTCLabelDecode(character_list=characters)
    missing = sorted(alphabet - set(''.join(decoder.character)))
    result = dict(parent_plan='PLAN_06', model_name=payload['Global']['model_name'],
                  artifact_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in MODEL.glob('inference.*')},
                  required_characters=len(alphabet), dictionary_entries=len(characters),
                  missing=missing, missing_codepoints=[f'U+{ord(c):04X}' for c in missing],
                  decoder='Installed CTCLabelDecode (includes implicit space)',
                  status='PASS_STATIC_ONLY' if not missing else 'FAIL_CHARSET',
                  caveat='Static dictionary coverage only; recognition/NFD input still require crop tests.')
    (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
