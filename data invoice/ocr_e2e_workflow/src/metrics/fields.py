from __future__ import annotations

from typing import Any

from src.metrics.recognition import edit_distance, text_similarity
from src.postprocess.money_parser import money_candidates
from src.postprocess.text_normalizer import normalize_text
from src.postprocess.timestamp_parser import parse_timestamp


def canonical_ground_truth(record: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[str]] = {"SELLER": [], "ADDRESS": [], "TIMESTAMP": [], "TOTAL_COST": []}
    for field in record.get("fields", []):
        if field["label"] in grouped:
            grouped[field["label"]].append(normalize_text(field["text_raw"]))
    timestamps = [parse_timestamp(text) for text in grouped["TIMESTAMP"]]
    timestamps = [value for value in timestamps if value]
    amounts = [amount for text in grouped["TOTAL_COST"] for amount in money_candidates(text)]
    return {
        "seller": " ".join(grouped["SELLER"]).strip() or None,
        "address": " ".join(grouped["ADDRESS"]).strip() or None,
        "timestamp": timestamps[0] if timestamps else None,
        "total_cost": max(amounts) if amounts else None,
    }


def evaluate_fields(
    predictions: list[dict[str, Any]], field_ground_truth: list[dict[str, Any]], split: str
) -> dict[str, Any]:
    pred_map = {row["image_id"]: row for row in predictions}
    counters = {
        "seller": {"correct": 0, "present": 0, "actual": 0, "char_errors": 0, "char_total": 0},
        "address": {"correct": 0, "present": 0, "actual": 0, "similarity": 0.0},
        "timestamp": {"correct": 0, "present": 0, "actual": 0, "date_correct": 0},
        "total_cost": {"correct": 0, "present": 0, "actual": 0},
    }
    per_image: list[dict[str, Any]] = []
    all_four_correct = 0
    image_count = 0
    for truth_record in field_ground_truth:
        if truth_record.get("split") != split:
            continue
        image_count += 1
        truth = canonical_ground_truth(truth_record)
        prediction = pred_map.get(truth_record["image_id"], {})
        image_scores: dict[str, Any] = {"image_id": truth_record["image_id"]}
        correct_all = True
        for field_name in counters:
            expected = truth[field_name]
            predicted_field = prediction.get(field_name, {})
            predicted = predicted_field.get("value") if isinstance(predicted_field, dict) else predicted_field
            if expected is not None:
                counters[field_name]["actual"] += 1
            if expected is not None and predicted not in (None, ""):
                counters[field_name]["present"] += 1
            if field_name in ("seller", "address"):
                expected_text = normalize_text(str(expected or ""))
                predicted_text = normalize_text(str(predicted or ""))
                correct = expected_text == predicted_text and expected is not None
                similarity = text_similarity(expected_text, predicted_text)
                if field_name == "seller":
                    counters[field_name]["char_errors"] += edit_distance(expected_text, predicted_text)
                    counters[field_name]["char_total"] += len(expected_text)
                else:
                    counters[field_name]["similarity"] += similarity
                image_scores[f"{field_name}_similarity"] = similarity
            else:
                correct = expected is not None and predicted == expected
                if field_name == "timestamp" and expected and predicted:
                    if str(expected)[:10] == str(predicted)[:10]:
                        counters[field_name]["date_correct"] += 1
            if correct:
                counters[field_name]["correct"] += 1
            correct_all = correct_all and correct
            image_scores[f"{field_name}_correct"] = correct
        all_four_correct += int(correct_all)
        image_scores["all_four_correct"] = correct_all
        per_image.append(image_scores)

    result: dict[str, Any] = {"images": image_count, "per_image": per_image}
    for field_name, values in counters.items():
        metric = {
            "exact_accuracy": values["correct"] / max(1, values["actual"]),
            "recall": values["present"] / max(1, values["actual"]),
            "correct": values["correct"],
            "actual": values["actual"],
        }
        if field_name == "seller":
            metric["cer"] = values["char_errors"] / max(1, values["char_total"])
        if field_name == "address":
            metric["similarity_macro"] = values["similarity"] / max(1, values["actual"])
        if field_name == "timestamp":
            metric["date_only_accuracy"] = values["date_correct"] / max(1, values["actual"])
        result[field_name] = metric
    result["all_four_fields_accuracy"] = all_four_correct / max(1, image_count)
    return result
