from src.metrics.geometry import match_polygons, polygon_iou
from src.metrics.recognition import edit_distance, evaluate_pairs


BOX = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_polygon_iou_identical_and_disjoint():
    assert polygon_iou(BOX, BOX) == 1.0
    assert polygon_iou(BOX, [[20, 20], [30, 20], [30, 30], [20, 30]]) == 0.0


def test_matching_is_one_to_one():
    matches = match_polygons([BOX, BOX], [BOX], 0.5)
    assert len(matches) == 1


def test_known_edit_distance_and_metrics():
    assert edit_distance("kitten", "sitting") == 3
    result = evaluate_pairs([("150.000đ", "150.000đ"), ("abc", "adc")])
    assert result["exact_match"] == 0.5
    assert result["char_errors"] == 1

