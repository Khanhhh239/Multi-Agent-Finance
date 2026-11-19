"""Portal-side loader for Agent 2's CSV -> rule-snapshot builder (single implementation lives in agent2/sme_fraud/csv_rule_source.py)."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / 'agent2' / 'sme_fraud' / 'csv_rule_source.py'
_spec = importlib.util.spec_from_file_location('agent2_csv_rule_source', _PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
build = _module.build
CONTRACT = _module.CONTRACT
