from __future__ import annotations

from typing import Any, Sequence

from src.postprocess.text_normalizer import normalize_text


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, ref_item in enumerate(reference, 1):
        current = [row]
        for column, hyp_item in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1]


def edit_operations(reference: str, hypothesis: str) -> dict[str, int]:
    rows, columns = len(reference) + 1, len(hypothesis) + 1
    matrix = [[0] * columns for _ in range(rows)]
    operation = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        matrix[row][0], operation[row][0] = row, "delete"
    for column in range(1, columns):
        matrix[0][column], operation[0][column] = column, "insert"
    for row in range(1, rows):
        for column in range(1, columns):
            candidates = [
                (matrix[row - 1][column] + 1, "delete"),
                (matrix[row][column - 1] + 1, "insert"),
                (matrix[row - 1][column - 1] + (reference[row - 1] != hypothesis[column - 1]), "equal" if reference[row - 1] == hypothesis[column - 1] else "substitute"),
            ]
            matrix[row][column], operation[row][column] = min(candidates, key=lambda item: item[0])
    counts = {"insertions": 0, "deletions": 0, "substitutions": 0}
    row, column = len(reference), len(hypothesis)
    while row or column:
        op = operation[row][column]
        if op == "insert":
            counts["insertions"] += 1
            column -= 1
        elif op == "delete":
            counts["deletions"] += 1
            row -= 1
        else:
            if op == "substitute":
                counts["substitutions"] += 1
            row -= 1
            column -= 1
    return counts


def text_similarity(reference: str, hypothesis: str) -> float:
    denominator = max(len(reference), len(hypothesis))
    return 1.0 if denominator == 0 else 1 - edit_distance(reference, hypothesis) / denominator


def evaluate_pairs(pairs: list[tuple[str, str]], normalized: bool = True) -> dict[str, Any]:
    processed = [
        (normalize_text(reference), normalize_text(hypothesis)) if normalized else (reference.strip(), hypothesis.strip())
        for reference, hypothesis in pairs
    ]
    char_errors = sum(edit_distance(reference, hypothesis) for reference, hypothesis in processed)
    char_total = sum(len(reference) for reference, _ in processed)
    word_errors = sum(edit_distance(reference.split(), hypothesis.split()) for reference, hypothesis in processed)
    word_total = sum(len(reference.split()) for reference, _ in processed)
    exact = sum(reference == hypothesis for reference, hypothesis in processed)
    similarities = [text_similarity(reference, hypothesis) for reference, hypothesis in processed]
    operations = [edit_operations(reference, hypothesis) for reference, hypothesis in processed]
    return {
        "samples": len(processed),
        "cer_micro": char_errors / max(1, char_total),
        "wer_micro": word_errors / max(1, word_total),
        "exact_match": exact / max(1, len(processed)),
        "normalized_edit_similarity_macro": sum(similarities) / max(1, len(similarities)),
        "insertion_rate": sum(item["insertions"] for item in operations) / max(1, char_total),
        "char_errors": char_errors,
        "char_total": char_total,
        "word_errors": word_errors,
        "word_total": word_total,
    }

