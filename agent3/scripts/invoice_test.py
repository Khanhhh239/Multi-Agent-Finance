"""Prepare local invoice PDFs and run/review/score the existing OCR pipeline."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'agent3_tax_compliance'
sys.path.insert(0, str(APP))
import ocr_quality
from src.quality.ocr_evaluation import file_hash, local_file, seal_dataset, verify_dataset, score_record, summarize, validate_labels

WORK = ROOT / 'invoice_test'
PREPARED = WORK / 'prepared'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def page_numbers(value, count):
    if value == 'all':
        return set(range(1, count + 1))
    result = set()
    for token in value.split(','):
        match = re.fullmatch(r'(\d+)(?:-(\d+))?', token.strip())
        if not match:
            raise ValueError('Pages must look like 2,3,12-13 or all')
        first = int(match[1]); last = int(match[2] or first)
        if not 1 <= first <= last <= count:
            raise ValueError('Page number outside source PDF')
        result.update(range(first, last + 1))
    return result


def compact(text):
    value = unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
    return ''.join(char for char in value if char.isalnum() and not unicodedata.combining(char))


def verify_page(original, copied):
    import pymupdf as fitz
    from PIL import Image, ImageChops, ImageStat
    if original.rect != copied.rect or original.rotation != copied.rotation or original.get_text() != copied.get_text():
        raise ValueError('Split changed page geometry or native text')
    before = original.get_pixmap(matrix=fitz.Matrix(.75, .75), alpha=False)
    after = copied.get_pixmap(matrix=fitz.Matrix(.75, .75), alpha=False)
    if (before.width, before.height) != (after.width, after.height):
        raise ValueError('Split changed rendered dimensions')
    # Font subsetting/resource caches can change antialiasing slightly when a
    # page is rendered outside its original PDF. Retain the measured difference.
    with Image.frombytes('RGB', (before.width, before.height), before.samples) as first, Image.frombytes('RGB', (after.width, after.height), after.samples) as second:
        difference = ImageChops.difference(first, second)
        mean = max(ImageStat.Stat(difference).mean)
        histogram = difference.convert('L').histogram()
        large_difference = sum(histogram[129:]) / (before.width * before.height)
    if mean > .75 or large_difference > .001:
        raise ValueError('Split rendering differs materially; inspect before using it')
    return {'native_text_matches': True, 'geometry_matches': True,
            'render_mean_channel_difference': mean, 'large_pixel_difference_ratio': large_difference,
            'render_within_tolerance': True}


def prepare(source, target, invoice_pages, groups='', number_locale='AUTO'):
    import pymupdf as fitz
    source = local_file(ROOT, str(source))
    target = Path(target).resolve()
    if not target.is_relative_to(WORK.resolve()):
        raise ValueError('Prepared documents must stay inside invoice_test')
    digest = file_hash(source)
    with fitz.open(source) as document:
        if not document.is_pdf or document.needs_pass or document.is_repaired:
            raise ValueError('Use an unencrypted, unrepaired PDF')
        selected = page_numbers(invoice_pages, len(document))
        grouped = []; assigned = set()
        for value in filter(None, groups.split(';')):
            pages = sorted(page_numbers(value, len(document)))
            if not set(pages) <= selected or assigned.intersection(pages):
                raise ValueError('Invoice groups must be disjoint subsets of selected pages')
            assigned.update(pages); grouped.append(pages)
        grouped += [[page] for page in sorted(selected - assigned)]
        # Validate everything before creating immutable output files.
        target.mkdir(parents=True, exist_ok=False)
        (target / 'pages').mkdir(); (target / 'invoices').mkdir()
        inventory = []; pixel_checks = []
        for index, original in enumerate(document):
            number = index + 1; output = target / 'pages' / f'page_{number:03d}.pdf'
            with fitz.open() as one:
                one.insert_pdf(document, from_page=index, to_page=index)
                one.save(output, garbage=3, deflate=True)
            with fitz.open(output) as reopened:
                assert len(reopened) == 1
                check = verify_page(original, reopened[0])
                preview = original.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                preview.save(target / 'pages' / f'page_{number:03d}.png')
            text = original.get_text(); key = compact(text)
            inventory.append({'page': number, 'selected': number in selected,
                              'path': str(output.relative_to(ROOT)), 'sha256': file_hash(output),
                              'input_kind': 'pdf_text' if len(key) >= 20 else 'pdf_scan',
                              'title_hint': 'INVOICE' if any(t in key for t in ('hoadongiatrigiatang', 'hoadonbanhang', 'vatinvoice')) else 'DECLARATION' if 'tokhai' in key else 'REQUIRES_VISUAL_REVIEW'})
            pixel_checks.append({'page': number, **check})
        entries = []
        for pages in sorted(grouped):
            identifier = 'invoice-' + '-'.join(f'p{page:03d}' for page in pages)
            if len(pages) == 1:
                output = target / 'pages' / f'page_{pages[0]:03d}.pdf'
            else:
                output = target / 'invoices' / (identifier + '.pdf')
                with fitz.open() as invoice:
                    for page in pages:
                        invoice.insert_pdf(document, from_page=page - 1, to_page=page - 1)
                    invoice.save(output, garbage=3, deflate=True)
                with fitz.open(output) as reopened:
                    for index, page in enumerate(pages):
                        verify_page(document[page - 1], reopened[index])
            entries.append({'case_id': identifier, 'path': str(output.relative_to(ROOT)),
                            'input_kind': 'pdf_scan' if any(inventory[p - 1]['input_kind'] == 'pdf_scan' for p in pages) else 'pdf_text',
                            'group_id': identifier, 'source_group': 'bundle-' + digest[:16],
                            'layout_group': 'bundle-unclassified-' + digest[:16], 'split': 'dev',
                            'source_pages': pages, 'source_bundle_sha256': digest,
                            'number_locale': number_locale, 'used_for_tuning': True,
                            'labels': {'review_status': 'DRAFT', 'complete': False, 'fields': {}, 'items': []}})
        write(target / 'inventory.json', {'source': str(source.relative_to(ROOT)), 'source_sha256': digest,
                                         'page_count': len(document), 'invoice_cases': len(entries),
                                         'excluded_pages': sorted(set(range(1, len(document) + 1)) - selected),
                                         'pages': inventory, 'pixel_checks': pixel_checks,
                                         'scope': 'DEV, same source bundle; page selection is not independent field labeling'})
        write(target / 'intake.json', entries)
        # All selected cases are explicitly dev; never manufacture a holdout.
        write(target / 'manifest.json', seal_dataset(entries, ROOT))
        from invoice_test_review import write_index
        write_index(target, inventory)
    return {'pages': len(inventory), 'invoice_cases': len(entries), 'output': str(target)}


def selected_entries(manifest, pages):
    entries = manifest['entries']
    if pages == 'all':
        return entries
    if pages is None:
        return entries[:3]
    count = max(p for entry in entries for p in entry['source_pages'])
    wanted = page_numbers(pages, count)
    available = {p for entry in entries for p in entry['source_pages']}
    if not wanted <= available:
        raise ValueError('Selected page is excluded or is not an invoice; check prepared/index.html')
    return [entry for entry in entries if wanted.intersection(entry['source_pages'])]


def valid_run_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Use a plain run ID')
    return value


def run_data(run_id=None):
    if run_id is None:
        run_id = read(WORK / 'last_run.json')['run_id']
    run_id = valid_run_id(run_id)
    folder = ocr_quality.OUTPUT / run_id
    report = read(folder / 'report.json'); manifest = read(folder / 'manifest.json')
    verify_dataset(manifest, ROOT)
    return run_id, folder, report, manifest


def review(run_id=None, annotations=None, scored=None):
    run_id, folder, report, manifest = run_data(run_id)
    from invoice_test_review import write_review
    output = WORK / 'results' / run_id
    output.mkdir(parents=True, exist_ok=True)
    if annotations is None and scored is None:
        saved = sorted(output.glob('score_*.json'))
        if saved:
            scored = read(saved[-1])
            name = scored.get('labels_snapshot')
            if name and Path(name).name == name:
                annotations = read(output / name)['cases']
    write_review(output / 'review.html', folder, report, manifest, PREPARED, annotations, scored)
    print('Review: ' + str(output / 'review.html'), flush=True)
    return output


def run(args):
    inventory = read(PREPARED / 'inventory.json')
    if file_hash(local_file(ROOT, inventory['source'])) != inventory['source_sha256']:
        raise ValueError('Original bundle changed; prepare a separately versioned dataset')
    manifest = read(PREPARED / 'manifest.json'); verify_dataset(manifest, ROOT)
    entries = selected_entries(manifest, args.pages)
    run_id = valid_run_id(args.run_id or ('invoice_test_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    selection = WORK / 'selections'; selection.mkdir(exist_ok=True)
    path = selection / (run_id + '.json')
    if path.exists() or (ocr_quality.OUTPUT / run_id).exists():
        raise ValueError('Run ID already exists; use a new ID')
    write(path, seal_dataset(entries, ROOT))
    write(WORK / 'last_run.json', {'run_id': run_id})
    print(f'Run {run_id}: {len(entries)} invoices; original pages ' + ', '.join(str(e['source_pages']) for e in entries), flush=True)
    print('PDF may use native text or HYBRID; fresh OCR runs only where the production router requests it.', flush=True)
    try:
        code = ocr_quality.run(SimpleNamespace(manifest=path, split='dev', open_test=False,
                                             config=args.config, render_dpi=150, run_id=run_id,
                                             dedicated_machine=args.dedicated_machine))
    except KeyboardInterrupt:
        print('Interrupted. Partial results are not an accepted benchmark.', flush=True)
        code = 130
    finally:
        if (ocr_quality.OUTPUT / run_id / 'report.json').exists():
            review(run_id)
    return code


def score(args):
    run_id, folder, report, manifest = run_data(args.run_id)
    if report.get('run_state') != 'COMPLETED' or not report.get('dataset_validated_at_end'):
        raise ValueError('Score only a completed, hash-verified run')
    supplied = read(args.labels)
    if supplied.get('run_id') != run_id:
        raise ValueError('Labels belong to another run')
    known = {entry['case_id']: entry for entry in manifest['entries']}
    annotations = supplied.get('cases', {})
    if set(annotations) - set(known):
        raise ValueError('Labels contain unknown cases')
    from src.extraction.contracts import ExtractionArtifact
    cases = []; errors = []; reasons = Counter()
    for row in report['cases']:
        entry = known[row['case_id']]
        provided = annotations.get(row['case_id'], {'sha256': entry['sha256'], 'labels': {}})
        if provided.get('sha256') != entry['sha256']:
            raise ValueError('Label/source hash mismatch')
        labels = provided.get('labels', {}); validate_labels(labels)
        artifact_path = folder / row['case_id'] / 'extraction.json'
        artifact = ExtractionArtifact.model_validate_json(artifact_path.read_bytes()) if artifact_path.exists() else None
        record = artifact.record if artifact else None
        result = score_record(record, labels)
        cases.append({**row, 'score': result})
        normalized_path = folder / row['case_id'] / 'normalized.json'
        if record and normalized_path.exists():
            from src.adapters.ocr.protocol import NormalizedDocumentExtraction
            normalized = NormalizedDocumentExtraction.model_validate_json(normalized_path.read_bytes())
            inventory = ocr_quality.error_inventory(record, artifact, normalized, labels)
        else:
            inventory = [{**outcome, 'hypothesis': 'PIPELINE_FAILED_OR_NO_RECORD', 'oracle_required': True}
                         for outcome in result['outcomes'] if outcome['outcome'] != 'CORRECT']
        for error in inventory:
            errors.append({'case_id': row['case_id'], **error}); reasons[error['hypothesis']] += 1
    summary = summarize(cases, report.get('workload_controlled', False))
    scored = {'run_id': run_id, 'scope': 'DEV with manually supplied labels; no independent holdout claim',
              'summary': summary, 'cases': cases, 'error_hypotheses': dict(reasons),
              'priority_errors': sorted(errors, key=lambda error: (not error['critical'], error['outcome'] != 'WRONG_PRESENT', error['case_id'], error['field_path'])),
              'release_approved': False}
    output = WORK / 'results' / run_id
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    snapshot = output / ('labels_' + stamp + '.json')
    write(snapshot, supplied)
    scored['labels_snapshot'] = snapshot.name
    destination = output / ('score_' + stamp + '.json')
    write(destination, scored)
    review(run_id, annotations, scored)
    print('Score: ' + str(destination), flush=True)
    count = sum(case['score']['labeled'] for case in cases)
    correct = sum(case['score']['correct'] for case in cases)
    print(json.dumps({'labeled': count, 'correct': correct, 'exact_match': correct / count if count else None,
                      'errors': len(errors), 'label_status': summary['quality_acceptance']}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--source', type=Path, required=True)
    prep.add_argument('--invoice-pages', required=True); prep.add_argument('--invoice-groups', default='')
    prep.add_argument('--number-locale', choices=('AUTO', 'VI', 'EN'), default='AUTO')
    execute = sub.add_parser('run'); execute.add_argument('--pages'); execute.add_argument('--run-id')
    execute.add_argument('--config', type=Path); execute.add_argument('--dedicated-machine', action='store_true')
    view = sub.add_parser('report'); view.add_argument('--run-id')
    scoring = sub.add_parser('score'); scoring.add_argument('--run-id'); scoring.add_argument('--labels', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.source, PREPARED, args.invoice_pages, args.invoice_groups, args.number_locale))); return 0
    if args.command == 'run': return run(args)
    if args.command == 'report': review(args.run_id); return 0
    return score(args)


if __name__ == '__main__':
    raise SystemExit(main())
