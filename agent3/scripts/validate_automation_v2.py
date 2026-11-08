"""Current automation/guide regression, separate from prior evidence snapshots."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('automation_regression',ROOT/'scripts/validate_automation_v1.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.OUT=ROOT/'docs/agent3/plans/evidence/automation_20261019_v2'
if __name__=='__main__':raise SystemExit(runner.main(checked_on='2026-10-19'))
