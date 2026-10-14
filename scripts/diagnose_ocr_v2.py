"""PLAN_06 V2-0: immutable, local-only OCR/extraction diagnostics.

Run with the application interpreter. Labels are never copied into runtime data.
Cached OCR timings are explicitly separated from fresh bounded worker timings.
"""
import argparse
import csv
import hashlib
import json
import platform
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent3_tax_compliance'))
from benchmark_public_invoices import CASES, SCAN_CASES, DATA, STAMP, document, field_at
from src.config import Settings
from src.domain.taxpayer import TaxpayerMaster
from src.ingestion.pdf_reader import read_pdf
from src.adapters.ocr.registry import load_default_config
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.normalizer import normalize
from src.adapters.ocr.layout_merge import merge
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.extraction.service import extract, implementation_sha
from src.extraction.contracts import ExtractionProfile
from src.canonicalization.normalize import tax_values, date_values, money_values, currency_values


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nfc(value):
    return unicodedata.normalize('NFC', str(value))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def probe(path, expected):
    """Canonical-label sanity check; not a raw-transcription oracle."""
    if path.endswith('tax_id'):
        choices = tax_values(expected)
    elif path.endswith('issue_date'):
        choices = date_values(expected)
    elif path.startswith('totals.'):
        choices = money_values(expected.replace('.', ','), 'VI')
    elif path == 'currency':
        choices = currency_values(expected)
    else:
        return 'NOT_APPLICABLE'
    return 'PASS' if nfc(expected) in map(nfc, choices) else 'FAIL'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--fresh-ocr', action='store_true')
    parser.add_argument('--model-id')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.run_id):
        parser.error('run-id must be a plain directory name')
    out = ROOT / 'data invoice/ocr_extraction_v2' / args.run_id
    if out.exists():
        parser.error('Run already exists; frozen runs must not be overwritten')
    out.mkdir(parents=True)
    write_json(out / 'run_state.json', {'state': 'RUNNING', 'parent_plan': 'PLAN_06'})
    config = load_default_config()
    if args.model_id:
        if not args.fresh_ocr:
            parser.error('model comparison requires fresh OCR, not cached results')
        config = config.model_copy(update={'model_id': args.model_id, 'version': args.model_id + '-v1'})
    master = TaxpayerMaster(**STAMP, tenant_id='pilot', taxpayer_id='pilot', revision=1,
                           tax_code='0000000000', effective_from=date(2000, 1, 1),
                           provenance_reference='technical-pilot-only')
    labels = json.loads((DATA / 'labels.json').read_text(encoding='utf-8'))
    client = WorkerClient(model_id=config.model_id)
    runtime = client.inventory()
    write_json(out / 'runtime_inventory.json', runtime)
    source_files = [p for folder in ('extraction', 'canonicalization', 'domain', 'adapters/ocr')
                    for p in (ROOT / 'agent3_tax_compliance/src' / folder).rglob('*.py')]
    manifest = dict(parent_plan='PLAN_06', created_at=datetime.now(timezone.utc).isoformat(),
                    extractor_sha256=implementation_sha(), runtime_sha256=runtime['runtime_sha256'],
                    labels_sha256=sha(DATA / 'labels.json'), label_status='SELF_CHECK_NOT_INDEPENDENT',
                    source_hashes={str(p.relative_to(ROOT)): sha(p) for p in source_files},
                    cases=[], independent_holdout=[], holdout_status='PENDING_NEW_TEMPLATE_DATA')
    documents = []
    latency = []
    for case in CASES:
        folder = out / case
        folder.mkdir()
        pdf = DATA / 'cases' / (case + '.pdf')
        manifest['cases'].append(dict(case=case, input_sha256=sha(pdf), split='dev_regression',
                                      contaminated=True, previous_role=CASES[case]))
        page = read_pdf(pdf, folder, dict(source_id=case, document_id=case,
                                         input_sha256=sha(pdf)), Settings())[0]
        documents.append((case, 'native_only', document(case, page, merge(page, ()), config)))
        if case not in SCAN_CASES:
            continue
        if args.fresh_ocr:
            start = time.perf_counter()
            response = client.run_batch([request_for(page, folder / 'page-0.png', config,
                                                      runtime['runtime_sha256'])], config)[0]
            elapsed = time.perf_counter() - start
            write_json(folder / 'fresh_response.json', response.model_dump(mode='json'))
            latency.append(dict(case=case, wall_seconds=elapsed, lifecycle='NEW_WORKER_PROCESS_PER_CALL',
                                success=response.issue is None,
                                metrics=client.metrics_history[-1:] if client.metrics_history else [],
                                model_load_ms=response.result.load_time_ms if response.result else None,
                                inference_ms=response.result.inference_time_ms if response.result else None))
            if response.issue:
                print(case + ': ' + response.issue.code, flush=True)
                continue
            blocks = normalize(page, response)
            for mode, content in (('scan', blocks), ('hybrid', merge(page, blocks))):
                documents.append((case, mode, document(case, page, tuple(content), config, (response,))))
        else:
            for mode in ('scan', 'hybrid'):
                path = DATA / 'normalized' / (case + '-' + mode + '.json')
                if path.exists():
                    documents.append((case, mode, NormalizedDocumentExtraction.model_validate_json(
                        path.read_text(encoding='utf-8'))))
        print(case + ': prepared', flush=True)
    write_json(out / 'split_manifest.json', manifest)
    errors, counts, probes = [], {}, []
    for case, mode, doc in documents:
        folder = out / case
        write_json(folder / (mode + '.normalized.json'), doc.model_dump(mode='json'))
        artifact = extract(doc, 'PDF', master, ExtractionProfile(number_locale='VI'))
        write_json(folder / (mode + '.extraction.json'), artifact.model_dump(mode='json'))
        counter = Counter()
        blocks = [b for page in doc.pages for b in page.blocks]
        for path, expected in labels.get(case, {}).get('fields', {}).items():
            field = field_at(artifact.record, path) if artifact.record else None
            value = field.model_dump(mode='json')['value'] if field else None
            status = field.status if field else 'NO_RECORD'
            correct = status == 'PRESENT' and nfc(value) == nfc(expected)
            outcome = 'CORRECT' if correct else 'WRONG_PRESENT' if status == 'PRESENT' else status
            counter[outcome] += 1
            probes.append(dict(case=case, mode=mode, path=path, result=probe(path, expected)))
            if correct:
                continue
            matching = [b.block_id for b in blocks if nfc(expected) in nfc(b.text_raw)]
            candidates = [c for c in artifact.candidates if c.semantic_field == path]
            issue_codes = [i.code for i in artifact.issues if i.field_path == path]
            hypothesis = ('SOURCE_CONFLICT' if mode == 'hybrid' and status == 'AMBIGUOUS' else
                          'FIELD_UNBOUND' if matching else
                          'TEXT_MISREAD_OR_CROP' if mode == 'scan' else 'UNRESOLVED')
            errors.append(dict(case=case, mode=mode, field=path, expected=expected, observed=value,
                               status=status, outcome=outcome, hypothesis=hypothesis,
                               confidence='HEURISTIC_REQUIRES_VISUAL_ORACLE',
                               matching_blocks=matching, issues=issue_codes,
                               candidates=[c.model_dump(mode='json') for c in candidates]))
        counts[case + '/' + mode] = dict(counter)
        # Detection overlays and crops are local-only; OCR polygons retain original coordinates.
        from PIL import Image, ImageDraw
        with Image.open(folder / 'page-0.png') as image:
            overlay = image.convert('RGB')
            draw = ImageDraw.Draw(overlay)
            for index, block in enumerate(blocks):
                if block.evidence is None:
                    continue
                x0, y0, x1, y1 = block.evidence.bbox
                box = (int(x0 * image.width), int(y0 * image.height),
                       int(x1 * image.width), int(y1 * image.height))
                draw.rectangle(box, outline='red', width=2)
                draw.text((box[0], box[1]), str(index), fill='black')
                if mode == 'scan' and box[2] > box[0] and box[3] > box[1]:
                    image.crop(box).save(folder / (f'crop-{index:03d}.png'))
            overlay.save(folder / (mode + '.overlay.png'))
            overlay.close()
    write_json(out / 'errors.json', errors)
    with (out / 'error_inventory.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        columns = ['case', 'mode', 'field', 'expected', 'observed', 'status', 'outcome', 'hypothesis', 'confidence']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(errors)
    write_json(out / 'normalizer_probes.json', probes)
    baseline = dict(parent_plan='PLAN_06', run_id=args.run_id, counts=counts,
                    hypotheses=dict(Counter(e['hypothesis'] for e in errors)),
                    latency=latency, timing_source='FRESH' if args.fresh_ocr else 'CACHED_NOT_CURRENT_LATENCY',
                    warm_latency='UNAVAILABLE_NO_PERSISTENT_MODEL_WORKER',
                    normalization_probe='CANONICAL_LABEL_SANITY_ONLY_NOT_RAW_TRANSCRIPTION_ORACLE',
                    independent_accuracy='UNAVAILABLE', human_adjudication=False,
                    raw_read_oracle='PENDING_MANUAL_CROPS', layout_oracle='PENDING_CORRECTED_BLOCK_LABELS')
    write_json(out / 'baseline.json', baseline)
    write_json(out / 'run_state.json', {'state': 'COMPLETE_TECHNICAL', 'parent_plan': 'PLAN_06'})
    print(json.dumps({'out': str(out), 'hypotheses': baseline['hypotheses'], 'latency': latency}), flush=True)


if __name__ == '__main__':
    main()
