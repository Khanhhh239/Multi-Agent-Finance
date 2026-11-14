"""Reproduce a mixed-cutoff batch without touching live state or credentials."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance_input import AccessScope
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.native_rule_demo import scenario
from sme_fraud.rule_snapshot import CONTRACT
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.snapshots import SnapshotStore


def run(output):
    source, _ = scenario('B1', True)
    known = deepcopy(source['tables']['transactions'][-1])
    known['transaction_id'] = 'HISTORY_KNOWN'
    source['tables']['transactions'].insert(0, known)
    future = source['tables']['transactions'][-1]
    for field in ('observed_at', 'posted_at', 'created_at', 'approved_at'):
        future[field] = '2025-08-13T11:00:00+07:00'
    for table, rows in source['tables'].items():
        source['coverage'][table].update(record_count=len(rows), records_sha256=digest(canonical(rows)))
    candidates = [known['transaction_id'], future['transaction_id']]
    data = dict(contract_version=CONTRACT, tenant_id=source['tenant_id'], company_id=source['company_id'],
                source=source, candidate_transaction_ids=candidates)
    scope = AccessScope(source['tenant_id'], frozenset({source['company_id']}), 'cutoff-regression', frozenset({'data.import'}))
    result = dict(case='known_and_future_candidates', expected_rows=2, source_as_of=source['as_of'],
                  future_event_at=future['posted_at'], live_state_touched=False)
    with tempfile.TemporaryDirectory(prefix='a2-cutoff-recheck-') as root:
        store = SnapshotStore(Path(root) / 'snapshots.sqlite3')
        draft = store.upload(scope, canonical(data), 'source.json', 'cutoff-check-upload')
        preview = store.preview(scope, draft['import_id'], 1)
        request = {key: preview[key] for key in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
        request.update(expected_revision=preview['revision'], acknowledge=True)
        saved = store.commit(scope, draft['import_id'], request, 'cutoff-check-save')
        result['preview_status'] = preview['status']
        try:
            analysis = analyze_snapshot(store, scope, saved['snapshot']['snapshot_id'], source['as_of'], technical=True)
            result['actual_rows'] = analysis['row_count']
            rows = {row['transaction_id']: row for row in analysis['rows']}
            future_row = rows.get(future['transaction_id'])
            result['future_unavailable'] = bool(future_row) and all(not rule['available'] for rule in future_row['rule_coverage']['rules'])
            result['status'] = 'passed' if set(rows) == set(candidates) and result['future_unavailable'] else 'failed'
        except ImportFailure as error:
            result.update(status='failed', error_code=error.code, actual_rows=None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return result['status'] == 'passed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.report.resolve()) else 1)
