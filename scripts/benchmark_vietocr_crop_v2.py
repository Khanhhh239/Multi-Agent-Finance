"""Controlled read oracle on one visually checked crop; benchmark interpreter only.

Independent model instances per width; no runtime config/default changes.
"""
import argparse
import hashlib
import json
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / 'data invoice/ocr_e2e_workflow'
sys.path.insert(0, str(WORKFLOW))


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (x != y)))
        previous = current
    return previous[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--crop', required=True, type=Path)
    parser.add_argument('--label', required=True, type=Path)
    parser.add_argument('--split-lines', action='store_true')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.run_id):
        parser.error('plain run-id required')
    out = ROOT / 'data invoice/ocr_extraction_v2' / args.run_id
    if out.exists():
        parser.error('Frozen run exists')
    out.mkdir(parents=True)
    from PIL import Image
    from src.adapters.vietocr_adapter import PPOCRV6VietOCRAdapter
    from src.utils import load_yaml
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor
    expected = unicodedata.normalize('NFC', args.label.read_text(encoding='utf-8').strip())
    profile = json.loads((ROOT / 'agent3_tax_compliance/configs/ocr/engines/ppocrv6_vietocr.json').read_text())
    config = dict(profile['adapter_config'], recognition_only=True, model_id='vietocr-crop-oracle')
    adapter = PPOCRV6VietOCRAdapter(config, args.run_id)
    rows = []
    with Image.open(args.crop) as source:
        image = source.convert('RGB')
    from src.adapters.recognition_crops import line_segments
    for width in ((512,) if args.split_lines else (512, 768, 1024)):
        merged = load_yaml(WORKFLOW / 'artifacts/models/vietocr/config/base.yml')
        merged.update(load_yaml(WORKFLOW / 'artifacts/models/vietocr/config/vgg-transformer.yml'))
        merged['dataset']['image_max_width'] = width
        merged['weights'] = str(WORKFLOW / 'artifacts/models/vietocr/transformerocr.pth')
        merged['cnn']['pretrained'] = False
        merged['device'] = 'cpu'
        merged['predictor']['beamsearch'] = False
        adapter.recognizer = Predictor(Cfg(merged))
        start = time.perf_counter()
        parts = line_segments(image) if args.split_lines else [(image.copy(), (0, image.width))]
        try:
            texts = [adapter.recognizer.predict(part) for part, _ in parts]
            actual = ' '.join(text.strip() for text in texts)
        finally:
            for part, _ in parts:
                part.close()
        edits = distance(expected, unicodedata.normalize('NFC', actual))
        row = dict(width=width, split_lines=args.split_lines, spans=[span for _, span in parts], prediction=actual, edits=edits, characters=len(expected),
                   cer=edits / max(1, len(expected)), exact_match=actual == expected,
                   inference_seconds=time.perf_counter() - start)
        rows.append(row)
        (out / 'results.json').write_text(json.dumps(dict(parent_plan='PLAN_06',
            label_status='AGENT_VISUAL_SELF_CHECK', crop_sha256=hashlib.sha256(args.crop.read_bytes()).hexdigest(),
            expected=expected, rows=rows), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=True), flush=True)
    image.close()


if __name__ == '__main__':
    main()
