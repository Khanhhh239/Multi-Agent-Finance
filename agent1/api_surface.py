"""Bề mặt công khai ổn định cho lớp dịch vụ; không chứa I/O hay tham số bí mật."""
from .models.features import SnapshotBuilder, add_labels
from .models.t1 import HazardGBM, pmf_from_hazard, quantiles_from_hazard
from .models.t6_cash import simulate, ACI, collection_kernel
from .models.t10 import what_if, rank_collections, scenario_library
from .models.t9_recon import Reconciler
from .models.reconciliation_pipeline import build_bank_labels


def predict_hazard(model, snapshot):
    return model.hazards(snapshot)


__all__ = ['SnapshotBuilder', 'add_labels', 'HazardGBM', 'predict_hazard', 'pmf_from_hazard',
           'quantiles_from_hazard', 'simulate', 'ACI', 'collection_kernel', 'what_if',
           'rank_collections', 'scenario_library', 'Reconciler', 'build_bank_labels']
