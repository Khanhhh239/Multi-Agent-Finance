"""Compute adapter parity from frozen numeric data and retained native sources."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import numpy as np
from sme_fraud.method_adapters import fit_local_reference, score_batch, METHODS
from sme_fraud.rules import score_rules
from sme_fraud.entity_graph import EntityGraph
from sme_fraud.import_files import canonical, digest
from test_method_adapters import frame, native_case, FROZEN
from test_snapshot_features import scope


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    history=frame(FROZEN['train'],'2025-01-01T00:00:00+07:00','H')
    reference=frame(FROZEN['test'],'2025-02-01T00:00:00+07:00','R')
    test=frame(FROZEN['test'],'2025-03-01T00:00:00+07:00','T')
    artifacts={m:fit_local_reference(history,reference,scope(),m,selected_columns=history['contract']['columns'],
        minimum_history=5,profile_id='numerical-parity-not-quality-evaluation') for m in METHODS}
    result=score_batch(test,scope(),artifacts=artifacts)
    floats=[]
    for method in METHODS:
        expected=np.asarray(FROZEN['statistics']['RobustZ'] if method=='robust_z' else FROZEN['estimators'][method]['scores'])
        actual=np.asarray([r['methods'][method]['raw_score'] for r in result['rows']])
        delta=np.abs(actual-expected);ok=bool(np.all(delta<=1e-8+1e-6*np.abs(expected)))
        floats.append(dict(method=method,expected=expected.tolist(),observed=actual.tolist(),max_abs_error=float(delta.max()),
                           pass_=ok,reference_version=json.loads(artifacts[method].manifest)['reference_version']))
    (features,rules,graphs),case=native_case(datetime(2025,8,12,11,tzinfo=timezone(timedelta(hours=7))),trigger=True)
    baseline=score_rules(case.tables,config=case.config)
    normalized=score_batch(features,scope(),methods=(),rule_output=rules,graphs=graphs)
    scores=[r['methods']['rules']['details']['native_score'] for r in normalized['rows']]
    hits=[h for r in normalized['rows'] for h in r['methods']['rules']['details']['hits']]
    diagnostics={k:v for k,v in baseline.items() if k not in {'scores','hits'}}
    diagnostics_equal=canonical(normalized['native_rule_diagnostics']['output'])==canonical(diagnostics)
    graph_equal=[]
    for row in normalized['rows']:
        native=EntityGraph(case.tables,'C001',row['as_of'])
        data=native.to_json([native.actor('vendor',case.vendor['vendor_id'])],depth=2,max_nodes=None)
        graph_equal.append(all(row['graph'][k]==data[k] for k in ('nodes','links','findings','information_gaps')))
    report=dict(status='technical_only',not_accuracy=True,atol=1e-8,rtol=1e-6,
        numeric_fixture_sha256=digest((ROOT/'tests/fixtures/retained_parity.json').read_bytes()),
        producer_sha256=digest(Path(__file__).read_bytes()),float_methods=floats,
        discrete=dict(native_source_checksum=features['source']['checksum'],row_count=len(scores),
                      rule_scores_equal=scores==baseline['scores'],rule_hits_equal=hits==baseline['hits'],graph_rows_equal=graph_equal,
                      native_diagnostics_equal=diagnostics_equal),
        limitation='Frozen arrays may share numerical values across reference/query solely for parity; not an out-of-sample fraud quality benchmark.')
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(canonical(report))
    assert all(m['pass_'] for m in floats) and report['discrete']['rule_scores_equal'] and report['discrete']['rule_hits_equal'] and all(graph_equal) and diagnostics_equal
    print('5 numerical methods within D-13 tolerance; native scores/hits/diagnostics and 5 graph rows equal.')
    return 0


if __name__=='__main__':raise SystemExit(main())
