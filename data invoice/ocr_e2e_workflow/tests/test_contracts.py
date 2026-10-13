import pytest

from src.contracts import Detection, OCRResult


def test_contract_round_trip():
    result = OCRResult(
        schema_version="1.1",
        run_id="run",
        model_id="model",
        output_mode="boxes_and_text",
        image_id="image.jpg",
        image_width=100,
        image_height=200,
        load_time_ms=1.0,
        inference_time_ms=2.0,
        detections=[Detection([[0, 0], [10, 0], [10, 10], [0, 10]], "abc", 0.9)],
    )
    restored = OCRResult.from_dict(result.to_dict())
    assert restored.detections[0].text_raw == "abc"


def test_contract_rejects_invalid_confidence():
    result = Detection([[0, 0], [10, 0], [10, 10]], "abc", 1.5)
    with pytest.raises(ValueError):
        result.validate()

