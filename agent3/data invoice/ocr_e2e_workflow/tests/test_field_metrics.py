from src.metrics.fields import evaluate_fields


def _prediction(image_id: str, total: int | None) -> dict:
    empty = {"value": None}
    return {
        "image_id": image_id,
        "seller": empty,
        "address": empty,
        "timestamp": empty,
        "total_cost": {"value": total},
    }


def test_field_recall_does_not_exceed_one_when_unlabeled_image_has_prediction():
    truth = [
        {
            "image_id": "labeled.jpg",
            "split": "test",
            "fields": [{"label": "TOTAL_COST", "text_raw": "10.000"}],
        },
        {"image_id": "unlabeled.jpg", "split": "test", "fields": []},
    ]
    predictions = [
        _prediction("labeled.jpg", 10_000),
        _prediction("unlabeled.jpg", 99_000),
    ]

    metrics = evaluate_fields(predictions, truth, "test")

    assert metrics["total_cost"]["recall"] == 1.0
    assert metrics["total_cost"]["exact_accuracy"] == 1.0
