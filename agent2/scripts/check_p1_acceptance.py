"""P1 acceptance recheck. Exit 2 reports an OPEN native finding; never hide it."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.import_files import canonical
from p1_recheck_support import SCENARIOS,run_case


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for name in SCENARIOS:
        summary,evidence=run_case(name);summaries.append(summary)
        (output/(name+'.json')).write_bytes(canonical(dict(summary=summary,evidence=evidence)))
        print(name,'| canonical:',summary['canonical_status'],summary['canonical_points'],
              '| native:',summary['native_points'],'|',summary['classification'])
    findings=[f for s in summaries for f in s['findings']]
    report=dict(kind='P1_recheck_synthetic_not_accuracy',scenarios=summaries,scenario_count=len(summaries),
        canonical_assertions_pass=all(s['canonical_assertions_pass'] for s in summaries),
        shared_domain_parity_cases=sum(s['classification']=='shared_domain_parity' for s in summaries),
        unresolved_findings=findings,whole_engine_approved=False,native_acceptance_pass=not findings,
        resolved_findings=[f for s in summaries for f in s.get('resolved_findings',[])],
        acceptance_scope='P1_header_time_guard_and_shared_domain_only_not_full_pipeline',
        legacy_representation_limit_cases=[s['scenario'] for s in summaries if s['classification']=='legacy_representation_limit'],
        exit_code=2 if findings else 0,score_runtime_changed=True,model_fit_performed=False,queue_written=False)
    (output/'summary.json').write_bytes(canonical(report))
    print('OPEN native findings:',len(findings));return report['exit_code']


if __name__=='__main__':raise SystemExit(main())
