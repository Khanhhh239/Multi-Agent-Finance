"""Deploy the registered v4 policy on already prepared, unlabelled features."""
from __future__ import annotations

import copy

import numpy as np

from .eval_v4 import CANDIDATES, POLICIES, SUPERVISED, alerts_for
from .hybrid import Collective
from .methods import empirical_rank


def policy_components(name):
    if name in CANDIDATES:
        return [name]
    for policy, _, args in POLICIES:
        if name == policy:
            return list(args[:2])
    raise ValueError(f"unknown registered v4 policy: {name}")


def serializable_model(model):
    """Remove a training-only closure from a fitted collective model."""
    model = copy.copy(model)
    if isinstance(model, Collective):
        model.base_factory = None
    return model


class PreparedV4Detector:
    """Never trains supervised components on a target company's labels.

    Inputs must already contain the existing causal features and u_* signals.
    Each serving instance is scoped to one company unless explicitly used by
    the synthetic-world evaluation harness with allow_multiple_companies=True.
    """
    def __init__(self, bundle, profile="precision", allow_multiple_companies=False):
        if bundle.get("schema_version") != 2:
            raise ValueError("requires a v4 pretrained bundle with schema_version=2")
        self.bundle = bundle
        self.name = {"precision": bundle["frozen"]["chosen"], "cold": bundle["frozen"]["cold_start"],
                     "wide": "L3"}.get(profile)
        if self.name is None:
            raise ValueError("profile must be precision, wide or cold")
        self.allow_multiple_companies = allow_multiple_companies

    def fit(self, train, valid):
        if train.empty or valid.empty:
            raise ValueError("separate non-empty history and calibration periods are required")
        self.companies = set(train.company_id.astype(str)) | set(valid.company_id.astype(str))
        if not self.allow_multiple_companies and len(self.companies) != 1:
            raise ValueError("serving history must belong to exactly one company")
        self.models, self.reference_scores = {}, {}
        for name in policy_components(self.name):
            if name in SUPERVISED:
                if name not in self.bundle["models"]:
                    raise ValueError(f"pretrained component missing: {name}")
                model = copy.deepcopy(self.bundle["models"][name])
                if isinstance(model, Collective):
                    model.set_history([train, valid])
            else:
                model = CANDIDATES[name]().fit(None, valid)
            self.models[name] = model
            self.reference_scores[name] = model.score(valid)
        return self

    def score(self, frame):
        if set(frame.company_id.astype(str)) - self.companies:
            raise ValueError("target company differs from fitted history")
        return {name: model.score(frame) for name, model in self.models.items()}

    def alerts(self, frame, budget=3):
        if budget != 3:
            raise ValueError("the registered v4 configuration was evaluated at budget=3")
        scores = self.score(frame)
        flags, fused = alerts_for(frame, scores, self.reference_scores, budget)
        if self.name in fused:
            priority_score = np.asarray(fused[self.name], dtype=float)
        else:
            first = policy_components(self.name)[0]
            priority_score = empirical_rank(self.reference_scores[first], scores[first])
        return flags[self.name], priority_score, scores
