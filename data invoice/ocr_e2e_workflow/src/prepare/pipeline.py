from __future__ import annotations

from typing import Any

from src.prepare.build_detection_gt import build_detection_ground_truth
from src.prepare.build_field_gt import build_field_ground_truth
from src.prepare.build_splits import build_splits
from src.prepare.validate_data import validate_prepared_data


def prepare_all(config: dict[str, Any]) -> dict[str, Any]:
    split_report = build_splits(config)
    detection_report = build_detection_ground_truth(config)
    field_report = build_field_ground_truth(config)
    validation_report = validate_prepared_data(config)
    return {
        "splits": split_report,
        "detection": detection_report,
        "fields": field_report,
        "validation": validation_report,
    }

