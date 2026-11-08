"""Publish aggregate PLAN_06 evidence; keep invoice values/crops in ignored data."""
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent3_tax_compliance'))
from src.domain.taxpayer import TaxpayerMaster
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile

LOCAL = ROOT / 'data invoice/ocr_extraction_v2'
PUBLIC = ROOT / 'docs/agent3/plans/evidence/ocr_extraction_v2'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def outcome(record, path, expected):
    for part in path.split('.'):
        record = record.get(part) if record else None
    if not record:
        return 'NO_RECORD'
    if record['status'] != 'PRESENT':
        return record['status']
    actual = unicodedata.normalize('NFC', str(record['value']))
    return 'CORRECT' if actual == unicodedata.normalize('NFC', expected) else 'WRONG_PRESENT'


def main():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    replay = LOCAL / 'plan06_v23_binding_replay_01'
    if replay.exists():
        raise SystemExit('Frozen replay already exists')
    replay.mkdir()
    labels = read(ROOT / 'data invoice/real_invoice_pilot_v1/labels.json')
    rows, differences, hashes = [], [], {}
    for phase in ('plan06_v20_frozen_01', 'plan06_v21_split_full_01'):
        folder = LOCAL / phase
        baseline = read(folder / 'baseline.json')
        hashes[phase] = hashlib.sha256((folder / 'baseline.json').read_bytes()).hexdigest()
        for key, counts in baseline['counts'].items():
            case, mode = key.split('/')
            rows.append(dict(phase=phase, case=case, mode=mode, counts=counts,
                             group='training_unverified' if case.startswith('accounting_training') else 'public_pilot_dev'))
        if phase != 'plan06_v20_frozen_01':
            continue
        for path in sorted(folder.glob('*/*.normalized.json')):
            doc = NormalizedDocumentExtraction.model_validate_json(path.read_text(encoding='utf-8'))
            case = path.parent.name
            mode = path.name.split('.')[0]
            master = TaxpayerMaster(config_version='v2-diagnostic', creator='v2-diagnostic', stage='benchmark',
                tenant_id=doc.tenant_id, taxpayer_id=doc.taxpayer_id, revision=doc.taxpayer_master_revision,
                tax_code='0000000000', effective_from=date(2000, 1, 1), provenance_reference='technical-only')
            artifact = extract(doc, 'PDF', master, ExtractionProfile(number_locale='VI'))
            (replay / (case + '-' + mode + '.json')).write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
            before = read(path.with_name(mode + '.extraction.json'))
            after = artifact.model_dump(mode='json')
            counts = Counter()
            for field, expected in labels[case]['fields'].items():
                first = outcome(before['record'], field, expected)
                last = outcome(after['record'], field, expected)
                counts[last] += 1
                if first != last:
                    differences.append(dict(case=case, mode=mode, field=field, before=first, after=last))
            rows.append(dict(phase='binding_replay_same_frozen_inputs', case=case, mode=mode,
                             counts=dict(counts), group='training_unverified' if case.startswith('accounting_training') else 'public_pilot_dev'))
    aggregates = []
    for phase, mode, group in sorted({(r['phase'], r['mode'], r['group']) for r in rows}):
        selected = [r for r in rows if (r['phase'], r['mode'], r['group']) == (phase, mode, group)]
        counts = Counter()
        for row in selected:
            counts.update(row['counts'])
        aggregates.append(dict(phase=phase, mode=mode, group=group, documents=len(selected), counts=dict(counts)))
    charset = read(LOCAL / 'charset_preflight_decoder_03/result.json')
    probes = read(LOCAL / 'plan06_v20_frozen_01/normalizer_probes.json')
    report = dict(parent_plan='PLAN_06', status='IN_PROGRESS_TECHNICAL_SELF_CHECK',
                  label_status='SELF_CHECK_NOT_INDEPENDENT', hashes=hashes, aggregates=aggregates,
                  binding_changes=differences, charset=dict(status=charset['status'],
                    missing_count=len(charset['missing']), model=charset['model_name'], artifact_hashes=charset['artifact_hashes']),
                  normalizer_sanity=dict(Counter(p['result'] for p in probes)),
                  crop_width_ablation=read(LOCAL / 'plan06_v21_width_01/results.json')['rows'],
                  crop_split_ablation=read(LOCAL / 'plan06_v21_split_01/results.json')['rows'],
                  fresh_latency={phase: read(LOCAL / phase / 'baseline.json')['latency'] for phase in hashes},
                  remaining=['independent holdout labels', 'full read/layout oracles', 'batch warm baseline',
                             'UI self acceptance', 'statistical gates', 'V2-4 and V2-5'])
    # Predictions in crop experiment are public-source values: omit them from Git evidence.
    for row in report['crop_width_ablation'] + report['crop_split_ablation']:
        row.pop('prediction', None)
    (PUBLIC / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(aggregates=aggregates, binding_changes=differences,
                         charset=report['charset']), ensure_ascii=True, indent=2), flush=True)


if __name__ == '__main__':
    main()
