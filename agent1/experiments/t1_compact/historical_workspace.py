"""Read-only adapters for replaying frozen research, never imported by serving.

Scratch-local T1 was removed from adaptive.methods. Original measured source
stays in its immutable snapshot; only relative imports are rebound in memory
for historical benchmarks/tests. This is not the production training path.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/t1/global_local_families_20261113/source_snapshot/agent1/adaptive"
PREFIX = "agent1.adaptive._historical_"


def load(name, replacements=()):
    qualified = PREFIX + name + "_20261113"
    if qualified in sys.modules:
        return sys.modules[qualified]
    path = SOURCE / (name + ".py")
    spec = importlib.util.spec_from_file_location(qualified, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    code = path.read_text(encoding="utf-8")
    for before, after in replacements:
        code = code.replace(before, after)
    exec(compile(code, str(path), "exec"), module.__dict__)
    return module


cash_history = load("cash_history")
partial_distribution = cash_history.partial_distribution
methods = load("methods", [
    ("from .cash_history import partial_distribution", "from ._historical_cash_history_20261113 import partial_distribution"),
    ("from .explanations import explain_collections", "from ._historical_explanations_20261113 import explain_collections"),
    ("from .collections import train_policy", "from ._historical_collections_20261113 import train_policy"),
])
business = load("business_explanations", [
    ("from .methods import", "from ._historical_methods_20261113 import"),
])
explanations = load("explanations", [
    ("from .methods import", "from ._historical_methods_20261113 import"),
    ("from .business_explanations import", "from ._historical_business_explanations_20261113 import"),
])
load("collections", [
    ("from .methods import", "from ._historical_methods_20261113 import"),
])
CATALOG = methods.CATALOG
Method = methods.Method
DistributionEnsemble = methods.DistributionEnsemble
features = methods.features
available_settlements = methods.available_settlements
train = methods.train
forecast = methods.forecast
explain_collections = explanations.explain_collections
HistoryEvidence = business.HistoryEvidence
review_factors = business.review_factors
