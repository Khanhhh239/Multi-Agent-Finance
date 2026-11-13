"""Landmark hazard adapters and a frozen convex pool for compact T1 serving."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from .compact_t1 import HORIZON, CompactT1, sha256


def write_metadata(directory, metadata):
    path = Path(directory) / "metadata.json"
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


class CompactHazard(CompactT1):
    """Use the shared landmark-to-week distribution with a fitted classifier."""

    def __init__(self, estimator, name, active=None, metadata=None):
        super().__init__(estimator, active, metadata)
        self.name = self.variant = name

    def predict_hazard(self, rows):
        if self.name == "lightgbm":
            return self.booster.booster_.predict(rows, num_threads=1)
        return self.booster.predict_proba(rows)[:, 1]

    def save(self, directory, metadata):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.booster, directory / "model.joblib", compress=3)
        self.metadata = dict(
            metadata,
            compact_kind="classifier",
            name=self.name,
            schema=self.feature_schema,
            features=list(self.feature_names),
            active=list(self.active),
            max_horizon_weeks=HORIZON,
            model_sha256=sha256(directory / "model.joblib"),
        )
        write_metadata(directory, self.metadata)


class CompactRule(CompactT1):
    """Contract-date, recent-delay and empirical age-stratified hazard baselines."""

    def __init__(self, name, hazard, metadata=None):
        active = {"due": (1, 2), "customer": (1, 2, 5), "survival": (2,)}[name]
        super().__init__(None, active, metadata)
        self.name = self.variant = name
        self.hazard = np.asarray(hazard, float)
        if self.hazard.shape != (5, HORIZON) or not np.isfinite(self.hazard).all():
            raise ValueError("Invalid empirical landmark hazards")

    def predict_hazard(self, rows):
        age_column = 0 if self.name == "survival" else 1
        age = rows[:, age_column]
        bucket = np.minimum(np.maximum(age, 0).astype(int) // 30, 4)
        week = rows[:, -1].astype(int)
        empirical = self.hazard[bucket, week - 1]
        if self.name == "survival":
            return empirical
        delay = rows[:, 2] if self.name == "customer" else 0.0
        remaining = rows[:, 0] + delay - age
        target = np.maximum(1, np.ceil(remaining / 7))
        scheduled = (week == target).astype(float)
        return np.where(remaining > 0, scheduled, empirical)

    def save(self, directory, metadata):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.metadata = dict(
            metadata,
            compact_kind="rule",
            name=self.name,
            schema=self.feature_schema,
            features=list(self.feature_names),
            active=list(self.active),
            max_horizon_weeks=HORIZON,
            hazard=self.hazard.tolist(),
        )
        write_metadata(directory, self.metadata)


class CompactEnsemble(CompactT1):
    """Pool full probability distributions through the normal serving interface."""

    name = variant = "compact_ensemble"

    def __init__(self, members, weights, metadata=None):
        self.members = tuple(members)
        self.weights = np.asarray(weights, float)
        if not 1 <= len(self.members) <= 3 or self.weights.shape != (
            len(self.members),
        ):
            raise ValueError("Compact ensemble requires one to three members")
        if (
            not np.isfinite(self.weights).all()
            or (self.weights <= 0).any()
            or not np.isclose(self.weights.sum(), 1.0, atol=1e-12, rtol=0)
        ):
            raise ValueError("Invalid compact ensemble weights")
        if any(
            not isinstance(model, CompactT1)
            or model.feature_schema != self.feature_schema
            or model.feature_names != self.feature_names
            for model in self.members
        ):
            raise ValueError("Incompatible compact ensemble member")
        active = sorted({column for model in self.members for column in model.active})
        super().__init__(None, active, metadata)

    def distribution_from_features(self, x, ages=None, horizon=13):
        return sum(
            weight * model.distribution_from_features(x, ages, horizon)
            for weight, model in zip(self.weights, self.members)
        )

    def save(self, directory, metadata):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        entries = []
        for position, model in enumerate(self.members):
            name = f"member_{position}"
            model.save(directory / name, {"candidate": model.variant})
            entries.append(
                {
                    "directory": name,
                    "name": model.variant,
                    "metadata_sha256": sha256(directory / name / "metadata.json"),
                }
            )
        self.metadata = dict(
            metadata,
            compact_kind="ensemble",
            name=self.name,
            schema=self.feature_schema,
            features=list(self.feature_names),
            active=list(self.active),
            max_horizon_weeks=HORIZON,
            members=entries,
            weights=self.weights.tolist(),
            calibration={"method": "identity"},
        )
        write_metadata(directory, self.metadata)


def load_compact_model(directory, metadata, model_classes=None):
    """Load locally generated, hash-verified members and their frozen weights."""
    directory = Path(directory)
    model_classes = model_classes or {
        "classifier": CompactHazard,
        "rule": CompactRule,
        "ensemble": CompactEnsemble,
    }
    active = metadata["active"]
    if (
        not active
        or len(set(active)) != len(active)
        or any(
            type(i) is not int or not 0 <= i < len(metadata["features"]) for i in active
        )
    ):
        raise ValueError("Invalid compact feature mask")
    kind = metadata["compact_kind"]
    if kind == "classifier":
        if sha256(directory / "model.joblib") != metadata["model_sha256"]:
            raise ValueError("Compact classifier hash mismatch")
        estimator = joblib.load(directory / "model.joblib")
        if estimator.n_features_in_ != len(active) + 1:
            raise ValueError("Compact estimator/schema dimension mismatch")
        return model_classes[kind](estimator, metadata["name"], active, metadata)
    if kind == "rule":
        model = model_classes[kind](metadata["name"], metadata["hazard"], metadata)
    elif kind == "ensemble":
        if metadata.get("calibration") != {"method": "identity"}:
            raise ValueError("Unknown compact probability calibration")
        members = []
        for position, entry in enumerate(metadata["members"]):
            if entry["directory"] != f"member_{position}":
                raise ValueError("Invalid compact member directory")
            path = directory / entry["directory"]
            if sha256(path / "metadata.json") != entry["metadata_sha256"]:
                raise ValueError("Compact member metadata hash mismatch")
            member = CompactT1.load(path)
            if member.variant != entry["name"]:
                raise ValueError("Compact member name mismatch")
            members.append(member)
        model = model_classes[kind](members, metadata["weights"], metadata)
    else:
        raise ValueError("Unknown compact artifact kind")
    if list(model.active) != active:
        raise ValueError("Compact artifact feature mask mismatch")
    return model
