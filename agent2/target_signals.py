"""Fit the existing label-free signals on one company's past records only."""
from __future__ import annotations

import numpy as np

from . import methods as M


class TargetSignals:
    def __init__(self, with_ae=True, with_if=True, seed=0):
        self.with_ae, self.with_if, self.seed = with_ae, with_if, seed

    def fit(self, history):
        if history.empty or history.company_id.nunique() != 1:
            raise ValueError("signal history must contain exactly one non-empty company")
        self.company_id = str(history.company_id.iloc[0])
        self.entity = M.EntityDeviation().fit(history)
        self.entity_reference = self.entity.score(history)
        if self.with_ae:
            self.ae = M.Autoencoder(name="ae", seed=self.seed).fit(history)
            self.ae_reference = self.ae.score(history)
        if self.with_if:
            self.iso = M.IForest(name="if", seed=self.seed).fit(history)
            self.if_reference = self.iso.score(history)
        return self

    def transform(self, frame):
        if set(frame.company_id.astype(str)) - {self.company_id}:
            raise ValueError("signal inputs must belong to the fitted company")
        out = frame.copy()
        for key, values in self.entity.parts(frame).items():
            out[f"u_ent_{key}"] = np.clip(values, 0, 12)
        entity = self.entity.score(frame)
        out["u_entity"] = entity
        out["u_entity_r"] = M.empirical_rank(self.entity_reference, entity)
        if self.with_ae:
            out["u_ae_r"] = M.empirical_rank(self.ae_reference, self.ae.score(frame))
        if self.with_if:
            out["u_if_r"] = M.empirical_rank(self.if_reference, self.iso.score(frame))
        return out
