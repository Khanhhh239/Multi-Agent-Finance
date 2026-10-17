"""Inspect declared series/receivables at an explicit cutoff without fake entries."""
import argparse
from pathlib import Path

from .evidence_policy import EvidencePolicy
from .generate import parse, stamp, TZ
from .rules import load_inputs
from .run_rule_repairs import write_jsonl


def inspect_sources(tables, as_of, overdue_days=60):
    if parse(as_of).tzinfo is None:
        raise ValueError('Source cutoff requires timezone')
    now = stamp(parse(as_of).astimezone(TZ))
    staff = {}
    for row in sorted(tables['employees'],key=lambda r:r['recorded_at']):
        if row['recorded_at']<=now:
            staff[row['employee_id']] = row
    policy = EvidencePolicy(tables,dict(receivable_overdue_days=overdue_days))
    for company in tables['companies']:
        policy.snapshot(company['company_id'],staff,now)
    return policy.findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--as-of',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f'Refusing to overwrite {args.output}')
    tables,_,_ = load_inputs(args.data)
    findings = inspect_sources(tables,args.as_of)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_jsonl(args.output,findings)
    print(f'{len(findings)} source findings; no transaction score or ML')


if __name__=='__main__':
    main()
