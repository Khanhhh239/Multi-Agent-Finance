"""Run opt-in real HE acceptance tests and preserve machine-readable outcomes."""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT.parent))
sys.path.insert(2, str(ROOT / 'tests'))


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test); self.records.append(dict(id=test.id(), status='pass'))

    def addError(self, test, err):
        super().addError(test, err); self.records.append(dict(id=test.id(), status='error'))

    def addFailure(self, test, err):
        super().addFailure(test, err); self.records.append(dict(id=test.id(), status='fail'))

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.records.append(dict(id=test.id(), status='skip', reason=reason))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--suite',action='append',help='Optional focused modules; formal full HE run omits this')
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/'tests_he'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(args.suite) if args.suite else unittest.defaultTestLoader.discover(str(ROOT / 'tests_he'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    report = dict(count=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skipped=len(result.skipped), tests=result.records)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
