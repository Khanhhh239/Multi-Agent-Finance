"""Fixed configurations declared before fitting and fresh outcome inspection."""
from __future__ import annotations

from copy import deepcopy
import json

from agent1.paths import SYNTH
from .sidecars import OBSERVATION_DESIGN


def episode(family, start, severity, peak=8, recovery=14, rise=3, industries=()):
    return dict(family=family, start=start, severity=severity, rise_weeks=rise,
                peak_weeks=peak, recovery_weeks=recovery, industries=list(industries), regions=[],
                reference_event="practical_20261105_predeclared_synthetic_assumption")


def protocol():
    original = json.loads((SYNTH / "v4_shortpay_4shock_20261028_train_000/config.json").read_text(encoding="utf-8"))
    base = {**original, "n_firms": 20, "write_xml": 0}
    augment = [
        [episode("credit", "2019-05-06", 1.4), episode("demand", "2020-03-02", 1.0),
         episode("credit", "2021-07-12", 1.2, peak=10), episode("supply", "2022-05-02", .9)],
        [episode("price", "2019-08-05", 1.2), episode("credit", "2020-01-06", .6),
         episode("demand", "2020-06-08", 1.4, peak=12), episode("credit", "2022-01-17", 1.5, peak=12, recovery=20)],
    ]
    fresh = [
        [episode("credit", "2024-05-13", .75, peak=5, recovery=12),
         episode("demand", "2024-06-10", .8, industries=("services", "food_processing"))],
        [episode("credit", "2024-08-12", 1.35, rise=2, peak=10, recovery=16),
         episode("demand", "2024-09-16", 1., industries=("textile_clothing", "wholesale"))],
        [episode("supply", "2024-04-08", 1.25, peak=10, recovery=18, industries=("food_processing", "wholesale")),
         episode("price", "2024-05-06", .9), episode("credit", "2024-10-14", .6)],
        [episode("credit", "2024-06-17", 1.1, rise=4, peak=12, recovery=20),
         episode("demand", "2024-07-15", 1.4, peak=10, recovery=18)],
    ]
    aug_configs = [{**deepcopy(base), "name": f"practical_v6_20261105_aug_supported_{i:03d}", "seed": 261105101 + i,
                    "start": "2019-01-01", "tail": ("atradius", "coface")[i],
                    "shock_schedule": schedule} for i, schedule in enumerate(augment)]
    fresh_configs = [{**deepcopy(base), "name": f"practical_v6_20261105_fresh_{i:03d}", "seed": 261105201 + i,
                      "tail": ("atradius", "uk", "coface", "atradius")[i],
                      "late_scale": (1., 1.1, .95, 1.15)[i], "shock_schedule": schedule}
                     for i, schedule in enumerate(fresh)]
    return {
        "version": "t1_v6_practical_20261105", "observation_design": OBSERVATION_DESIGN,
        "evidence": "synthetic incremental-feature study, conditional on legacy v6 baseline inputs; not SME validation",
        "source_fit": "exact 200000 cached v6 fit rows, original row order",
        "selection": "first eligible 2024 invoice anchors at the 8 reserved companies per source World; never fit companies",
        "selection_aggregation": "equal World mean, not pooled invoice count",
        "eligibility": "joint and writeoff Brier365 both below v6; Paid Brier28/91 <= 1.02 * v6 in every source World",
        "tie_break": "joint Brier365; then fewer additional features; then arm name; fallback v6",
        "calibration": "identity for every arm", "rounds": 160,
        "horizons_days": [28, 91, 365], "horizon_weeks": 53,
        "support_trigger": {"features": ["c_tenure_days", "c_n_hist", "f_n_hist"], "max_outside_train_range_fraction": .1},
        "augmentation": "separate experiment; baseline and the primary-selected feature set each get the same 2 new source Worlds, max50000 snapshots per World",
        "augmentation_final_selection": "same source eligibility against original v6, including augmented baseline as a candidate",
        "acceptance": {"max_paid_ece": .05, "max_abs_writeoff_gap365": .03, "max_short_paid_brier_ratio": 1.02},
        "bootstrap": {"replicates": 400, "unit": "company within World; no CI claim over unseen economies"},
        "industry_missing_sensitivity": "after selection freeze, mask all industry; report only, no reselection",
        "eval_first_cutoff": "2024-07-01", "eval_last_cutoff": "2024-12-16", "eval_stride_days": 28,
        "eval_label_end": "2025-12-31", "fresh_generation": "only after final source selection freeze",
        "augment_worlds": aug_configs, "fresh_worlds": fresh_configs,
        "prohibited": ["test_000 selection or training", "simulated macro features", "future ledger allocations",
                       "future feature refresh in hazard weeks", "overwrite old artifacts", "fresh-based reselection"],
    }
