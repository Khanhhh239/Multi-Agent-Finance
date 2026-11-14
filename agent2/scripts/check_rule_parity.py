"""Audit native adapter parity using the project's existing business fixtures.

This is a test tool, not a scoring endpoint or a fraud accuracy benchmark.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.import_files import canonical,digest
from sme_fraud.rule_audit_cases import Case
from rule_parity_support import compare_native,prepared_case

SUITES=('test_core_rule_requirements','test_rule_repairs','test_payment_evidence',
        'test_authority_and_dormancy','test_noise_policy','test_spec_policy','test_b4_evidence_timing')
EXAMPLES=('five_default','five_legacy','self_approval','installments','bank_callback_revision',
          'paid_leave','authority_matrix','batch_overpayment','batch_installment_exception')


class AuditResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.active=None;self.records=[]
    def startTest(self,test):self.active=test.id();super().startTest(test)
    def stopTest(self,test):super().stopTest(test);self.active=None
    def addSuccess(self,test):super().addSuccess(test);self.records.append(dict(testcase=test.id(),status='pass'))
    def addFailure(self,test,error):super().addFailure(test,error);self.records.append(dict(testcase=test.id(),status='fail'))
    def addError(self,test,error):super().addError(test,error);self.records.append(dict(testcase=test.id(),status='error'))
    def addSkip(self,test,reason):super().addSkip(test,reason);self.records.append(dict(testcase=test.id(),status='skip',reason=reason))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();comparisons=[]
    for name in EXAMPLES:
        case=prepared_case(name);checked,*_=compare_native(case.tables,case.config)
        comparisons.append(dict(origin='explicit_cardinality_and_exception_example',testcase=name,**checked))
    runner=unittest.TextTestRunner(verbosity=1,resultclass=AuditResult)
    original=Case.score

    def audited(case):
        # Preserve the actual business test result and its assertions. Compare
        # a separate scoped copy, using the fixture's exact resolved config.
        result=original(case)
        checked,*_=compare_native(case.tables,case.config)
        comparisons.append(dict(origin='existing_business_fixture',testcase=active[0].active if active[0] else None,**checked))
        if not all(checked['checks'].values()):
            raise AssertionError('Native adapter parity mismatch: '+str(checked))
        return result

    active=[None]
    original_make=runner._makeResult
    def make_result():
        result=original_make();active[0]=result;return result
    runner._makeResult=make_result
    with patch.object(Case,'score',audited):
        result=runner.run(unittest.defaultTestLoader.loadTestsFromNames(SUITES))
    totals=Counter()
    for checked in comparisons:
        for field in ('input_rows','output_rows','hits','operational_alerts','zero_score_rows',
                      'suppressed_hits','batch_events','batch_exceptions','batch_positive_events'):
            totals[field]+=checked['counts'][field]
    ok=(bool(comparisons) and result.wasSuccessful() and not result.skipped and
        all(all(c['checks'].values()) for c in comparisons) and totals['input_rows']==totals['output_rows'])
    report=dict(status='pass' if ok else 'fail',scope='native_adapter_same_complete_source_profile_not_full_canonical_bridge',
        not_accuracy=True,producer_sha256=digest(Path(__file__).read_bytes()),
        fixture_suites=list(SUITES),business_test_summary=dict(count=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped)),
        business_tests=result.records,comparison_runs=len(comparisons),totals=dict(totals),comparisons=comparisons,
        limitation='Counts are repeated fixture observations, not unique real transactions or fraud precision. Canonical snapshot supports E3 only; missing sources remain unavailable.')
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(report))
    print('Parity:',report['status'],'| comparisons:',len(comparisons),'| rows:',totals['input_rows'],'->',totals['output_rows'])
    print('Suppressed hits:',totals['suppressed_hits'],'| batch events:',totals['batch_events'],'| batch exceptions:',totals['batch_exceptions'])
    return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())
