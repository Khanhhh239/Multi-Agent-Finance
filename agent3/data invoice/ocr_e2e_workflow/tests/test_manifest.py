from pathlib import Path

from src.prepare.build_splits import parse_recognition_labels
from src.utils import crop_to_source_name


def test_crop_to_source_name_only_removes_final_numeric_suffix():
    assert crop_to_source_name("mcocr_public_abc_12.jpg") == "mcocr_public_abc.jpg"


def test_recognition_parser_preserves_spaces_and_tabs_after_first_separator(tmp_path: Path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "receipt_0.jpg").write_bytes(b"placeholder")
    labels = tmp_path / "labels.txt"
    labels.write_text("receipt_0.jpg\tTổng tiền  150.000đ\n", encoding="utf-8")
    records = parse_recognition_labels(labels, image_dir)
    assert records[0]["text_raw"] == "Tổng tiền  150.000đ"
    assert records[0]["source_image_id"] == "receipt.jpg"

