from pathlib import Path

from src.evaluator import filter_ground_truth
from src.prepare.build_detection_gt import parse_detection_file, transform_point


def test_detection_polygons_are_scaled_to_canonical_image(tmp_path: Path):
    label = tmp_path / "receipt.tsv"
    label.write_text(
        "0,10,20,30,20,30,40,10,40,Tổng tiền,TOTAL_COST\n",
        encoding="utf-8",
    )

    boxes, errors = parse_detection_file(label, 100, 100, 200, 300)

    assert errors == []
    assert boxes[0]["polygon"] == [
        [20.0, 60.0],
        [60.0, 60.0],
        [60.0, 120.0],
        [20.0, 120.0],
    ]
    assert boxes[0]["transcript"] == "Tổng tiền"
    assert boxes[0]["label"] == "TOTAL_COST"


def test_ground_truth_is_limited_to_the_run_manifest():
    rows = [
        {"image_id": "a.jpg", "split": "test"},
        {"image_id": "b.jpg", "split": "test"},
        {"image_id": "a.jpg", "split": "dev"},
    ]

    assert filter_ground_truth(rows, "test", {"a.jpg"}) == [rows[0]]


def test_detection_point_is_rotated_to_match_canonical_image():
    assert transform_point(10, 20, 100, 50, 200, 100, 270) == [80.0, 90.0]
