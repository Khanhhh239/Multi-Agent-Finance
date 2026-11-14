"""Compare canonical P1 with retained native rules on their shared positive domain."""
import argparse
from datetime import datetime,timedelta
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.import_files import canonical
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules
from test_p1_evaluation import payments,evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    specs=[('first_only',[11_000_000],[0]),('exact',[4_000_000,6_000_000],[0,1]),
        ('one_vnd',[4_000_000,6_000_001],[0,1]),('two_vnd',[4_000_000,6_000_002],[0,1]),
        ('mixed_channels',[4_000_000,7_000_000],[0,1]),('45_day_history',[4_000_000,7_000_000],[0,45]),
        ('concurrent_only',[6_000_000,6_000_000],[0,0]),('prior_and_concurrent',[4_000_000,4_000_000,4_000_000],[0,1,1])]
    report=[]
    for name,amounts,days in specs:
        case=Case();rows=[];canonical_rows=[]
        for index,(amount,day) in enumerate(zip(amounts,days)):
            channel='bank' if name=='mixed_channels' and index else 'cash'
            rows.append(case.pay(case.at+timedelta(days=day),amount,invoice_number='0000123',invoice_gross_vnd=10_000_000,
                payment_channel=channel,credit_account='111' if channel=='cash' else '112',
                recipient_account='' if channel=='cash' else case.vendor['bank_account']))
            at=(datetime.fromisoformat('2026-09-01T09:00:00+07:00')+timedelta(days=day)).isoformat()
            canonical_rows.append((f'T{index}',amount,at,dict(payment_channel=channel)))
        data=payments(canonical_rows);case.score();native=score_rules(case.tables,features=case.features)
        checks=[];group_checks={}
        for index,row in enumerate(rows):
            hits=[h for h in native['hits'] if h['rule_id']=='P1' and h['transaction_id']==row['transaction_id'] and h['points']>0]
            expected=hits[0]['points'] if hits else 0;actual=evaluate(data,f'T{index}')
            assert actual['score']==expected and actual['matched']==bool(hits),(name,index,actual,expected)
            if hits:assert actual['details']['invoice_checks'][0]['cumulative_paid_vnd']==hits[0]['evidence']['cumulative_paid_vnd']
            checks.append(dict(transaction_id=f'T{index}',native_score=expected,canonical_score=actual['score'],matched=actual['matched']))
            for group in actual['details']['simultaneous_checks']:
                if group['matched']:group_checks[group['group_id']]=group
        expected_groups=[g for g in native['batch_events'] if g['rule_id']=='P1' and g['signal']]
        expected_totals=sorted((g['points'],g['evidence']['cumulative_paid_vnd'],g['evidence']['excess_vnd']) for g in expected_groups)
        actual_totals=sorted((g['points'],g['cumulative_paid_vnd'],g['excess_vnd']) for g in group_checks.values())
        assert expected_totals==actual_totals,(name,expected_totals,actual_totals)
        report.append(dict(scenario=name,input_rows=len(rows),output_rows=len(checks),row_checks=checks,
            native_group_totals=expected_totals,canonical_group_totals=actual_totals,pass_all=True))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(canonical(dict(kind='positive_single_invoice_native_parity_not_accuracy',scenarios=report,
        comparison_cases=len(report),row_comparisons=sum(len(r['row_checks']) for r in report),all_pass=True,
        signed_domain_native_supported=False,queue_written=False)))
    print(len(report),'native/canonical scenarios match; signed extension is validated separately.');return 0


if __name__=='__main__':raise SystemExit(main())
