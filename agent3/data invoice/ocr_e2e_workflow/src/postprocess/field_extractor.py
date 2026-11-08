from __future__ import annotations

import re
from typing import Any

from src.postprocess.money_parser import money_candidates
from src.postprocess.reading_order import sort_detections
from src.postprocess.text_normalizer import accent_insensitive, normalize_text
from src.postprocess.timestamp_parser import parse_timestamp
from src.utils import load_yaml


def _lines(result: dict[str, Any]) -> list[dict[str, Any]]:
    detections = sort_detections(result.get("detections", []))
    if detections:
        return [
            {
                "id": detection.get("source_id") or str(index),
                "text": normalize_text(detection.get("text_raw", "")),
                "confidence": detection.get("confidence"),
                "polygon": detection.get("polygon"),
            }
            for index, detection in enumerate(detections)
            if normalize_text(detection.get("text_raw", ""))
        ]
    return [
        {"id": f"line:{index}", "text": normalize_text(line), "confidence": None, "polygon": None}
        for index, line in enumerate((result.get("document_text_raw") or "").splitlines())
        if normalize_text(line)
    ]


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    haystack = accent_insensitive(text)
    return any(accent_insensitive(keyword) in haystack for keyword in keywords)


def _field(value: Any, confidence: float, evidence: list[str], raw: str | None = None) -> dict[str, Any]:
    return {"value": value, "confidence": round(max(0.0, min(1.0, confidence)), 4), "evidence_ids": evidence, "raw": raw}


def extract_fields(result: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = config or load_yaml("configs/field_extraction.yaml")
    lines = _lines(result)
    seller = _field(None, 0.0, [])
    address = _field(None, 0.0, [])
    timestamp = _field(None, 0.0, [])
    total = _field(None, 0.0, [])

    for index, line in enumerate(lines):
        text = line["text"]
        confidence = float(line["confidence"] if line["confidence"] is not None else 0.5)
        if seller["value"] is None and (_contains_keyword(text, settings["seller_keywords"]) or index < 2):
            if not re.search(r"\d{1,3}(?:[., ]\d{3})+", text):
                seller = _field(text, confidence * (0.9 if index < 2 else 0.8), [line["id"]], text)
        if address["value"] is None and _contains_keyword(text, settings["address_keywords"]):
            value = re.sub(r"^(?:địa\s*chỉ|đ\s*/?\s*c)\s*[:.-]?\s*", "", text, flags=re.I)
            if len(value) < 5 and index + 1 < len(lines):
                value = f"{value} {lines[index + 1]['text']}".strip()
                evidence = [line["id"], lines[index + 1]["id"]]
            else:
                evidence = [line["id"]]
            address = _field(value, confidence * 0.9, evidence, text)
        parsed_time = parse_timestamp(text)
        if parsed_time and (timestamp["value"] is None or _contains_keyword(text, settings["timestamp_keywords"])):
            timestamp = _field(parsed_time, confidence * 0.95, [line["id"]], text)

    total_candidates: list[tuple[float, int, dict[str, Any]]] = []
    for index, line in enumerate(lines):
        context = " ".join(item["text"] for item in lines[max(0, index - 1) : min(len(lines), index + 2)])
        keyword = _contains_keyword(context, settings["total_keywords"])
        for amount in money_candidates(line["text"]):
            score = (3.0 if keyword else 0.0) + index / max(1, len(lines)) + min(amount / 10_000_000, 1.0)
            total_candidates.append((score, amount, line))
    if total_candidates:
        _, amount, line = max(total_candidates, key=lambda item: item[0])
        base_confidence = float(line["confidence"] if line["confidence"] is not None else 0.5)
        total = _field(amount, base_confidence, [line["id"]], line["text"])
        total["currency"] = "VND"

    fields = {"seller": seller, "address": address, "timestamp": timestamp, "total_cost": total}
    missing = [name for name, field in fields.items() if field["value"] in (None, "")]
    threshold = float(settings.get("confidence_review_threshold", 0.65))
    requires_review = bool(missing) or any(
        field["value"] not in (None, "") and field["confidence"] < threshold for field in fields.values()
    )
    return {
        "image_id": result["image_id"],
        **fields,
        "missing_fields": missing,
        "requires_review": requires_review,
        "source_model_id": result.get("model_id"),
        "source_run_id": result.get("run_id"),
    }

