"""Native unittest runner with real per-test JSON and seven catalog ID mappings."""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]


class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.records={}
    def record(self,test,status):
        name=test.id();id=name
        prefix='test_r1_acceptance.R1AcceptanceTests.test_R1_'
        if name.startswith(prefix):id='R1-'+name[len(prefix):]
        priority={'pass':0,'skip':1,'fail':2}
        if id not in self.records or priority[status]>priority[self.records[id]['status']]:
            self.records[id]=dict(id=id,status=status,testcase=name)
    def addSuccess(self,test):super().addSuccess(test);self.record(test,'pass')
    def addFailure(self,test,error):super().addFailure(test,error);self.record(test,'fail')
    def addError(self,test,error):super().addError(test,error);self.record(test,'fail')
    def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'skip')
    def addExpectedFailure(self,test,error):super().addExpectedFailure(test,error);self.record(test,'fail')
    def addUnexpectedSuccess(self,test):super().addUnexpectedSuccess(test);self.record(test,'fail')
    def addSubTest(self,test,subtest,error):
        super().addSubTest(test,subtest,error)
        if error is not None:self.record(test,'fail')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',required=True)
    parser.add_argument('--suite',action='append',help='Optional focused native runner check; formal R1 command omits this')
    args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromNames(args.suite) if args.suite else unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    report=Path(args.report);report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(dict(tests=list(result.records.values()),count=result.testsRun,
        skipped=len(result.skipped),failures=len(result.failures),errors=len(result.errors)),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() and len(result.records)==result.testsRun and all(t['status']=='pass' for t in result.records.values()) else 1


if __name__=='__main__':raise SystemExit(main())
