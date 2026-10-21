"""BenchRec GL-bank adapter and fixed baselines. No labels enter match().

This is static allocation-key evaluation, not invoice allocation or an as-of
production backtest. Signed source amounts are already on the same orientation;
DR/CR codes are opposite on A and B and must NOT be used to flip the amounts.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
import hashlib
from itertools import combinations
import math
from pathlib import Path
import random
import re

from .data import fingerprint, read_csv_rows as csv_rows, read_json

METHODS = ("exact_amount_date", "nearest_date", "text_mutual", "bounded_group_sum")


@dataclass(frozen=True)
class Config:
    date_window_days: int = 14
    text_threshold: float = 0.65
    text_margin: float = 0.1
    group_max_size: int = 3
    group_candidate_cap: int = 12

    def __post_init__(self):
        if (any(type(v) is not int for v in (self.date_window_days, self.group_max_size, self.group_candidate_cap))
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in (self.text_threshold, self.text_margin))
                or self.date_window_days < 0 or not 0 <= self.text_threshold <= 1
                or not 0 <= self.text_margin <= 1 or not 2 <= self.group_max_size <= 3
                or not self.group_max_size <= self.group_candidate_cap <= 12):
            raise ValueError("Invalid fixed BenchRec configuration")


def verified_path(directory, filename):
    directory = Path(directory)
    manifest = read_json(directory / "source_manifest.json")
    if manifest.get("source_id") != "benchrec-kaggle-v3" or manifest.get("download_status") != "downloaded":
        raise ValueError("Expected downloaded BenchRec v3")
    entries = [item for item in manifest["files"] if item["file"] == filename]
    if len(entries) != 1:
        raise ValueError("Missing/duplicate manifest entry")
    path = directory / filename
    payload = path.read_bytes()
    if len(payload) != entries[0]["bytes"] or hashlib.sha256(payload).hexdigest() != entries[0]["sha256"]:
        raise ValueError("Raw BenchRec hash/size mismatch")
    return path


def load_features(directory, split):
    if split not in ("train", "eval"):
        raise ValueError("Unknown split")
    path = verified_path(directory, f"BenchRec_cash_v1.0_{split}.csv")
    sides, seen = {"A": [], "B": []}, {"A": set(), "B": set()}
    for raw in csv_rows(path):
        if bool(raw["A_id"]) == bool(raw["B_id"]):
            raise ValueError("Expected exactly one transaction per row")
        side = "A" if raw["A_id"] else "B"
        # Explicit allowlist: historical matching metadata, labels, row order and
        # wasPreviouslyMismatched can never reach a baseline.
        row = {"id": raw[side + "_id"], "amount": Decimal(raw[side + "_amount"]),
               "date": date.fromisoformat(raw[side + "_valueDate"]),
               "currency": raw[side + "_currencyCode"], "account": raw[side + "_account"],
               "reference": raw[side + "_transactionReferences"]}
        if not row["amount"].is_finite() or row["amount"] == 0 or not row["currency"] or not row["account"]:
            raise ValueError("Invalid amount or scope")
        if row["id"] in seen[side]:
            raise ValueError("Duplicate transaction ID")
        seen[side].add(row["id"])
        if side == "A":
            # Output dictionary only: never a similarity/blocking input.
            row["allocation"] = "_".join(raw["A_" + key] for key in
                ("currencyCode", "valueDate", "account", "transactionAttributes"))
            if row["allocation"] != raw["A_allocation"]:
                raise ValueError("Allocation formula disagrees with source")
            if any(char in row["allocation"] for char in "[],"):
                raise ValueError("Allocation key contains unsupported set delimiters")
        sides[side].append(row)
    return sides["A"], sides["B"]


def parse_allocations(value):
    """Source grammar: empty, one key, or [comma-separated keys].

    Whitespace INSIDE a key is meaningful. Keys containing set delimiters are
    unsupported; unknown well-formed keys remain labels, never null matches.
    """
    if not isinstance(value, str):
        raise ValueError("Allocation target must be a string")
    if value == "":
        return frozenset()
    if value.startswith("["):
        if not value.endswith("]"):
            raise ValueError("Unclosed allocation set")
        parts = value[1:-1].split(",")
    else:
        parts = [value]
    if (any(not part.strip() or any(c in part for c in "[],") for part in parts)
            or len(parts) != len(set(parts))):
        raise ValueError("Empty or duplicate allocation member")
    return frozenset(parts)


def load_truth(directory, split, expected_b_ids, a_keys):
    if split not in ("train", "eval"):
        raise ValueError("Unknown truth split")
    filename = f"BenchRec_cash_v1.0_{'solution' if split == 'eval' else 'train'}.csv"
    truth = {}
    for row in csv_rows(verified_path(directory, filename)):
        if not row["B_id"]:
            continue
        if row["B_id"] in truth:
            raise ValueError("Duplicate truth ID")
        truth[row["B_id"]] = parse_allocations(row["targetAllocation"])
    if set(truth) != set(expected_b_ids):
        raise ValueError("Truth must cover the entire B universe")
    unknown = sum(len(keys - a_keys) for keys in truth.values())
    # Missing A keys are retained and counted as unreachable labels, never
    # silently dropped or converted into null matches.
    return truth, {"target_keys_absent_from_A_occurrences": unknown,
                   "positive_B": sum(bool(v) for v in truth.values()),
                   "null_B": sum(not v for v in truth.values()),
                   "multi_allocation_B": sum(len(v) > 1 for v in truth.values())}


def perturb(bank, profile, seed):
    result, changed = [], Counter()
    for raw in bank:
        row = dict(raw)
        rng = random.Random(f"benchrec-v1:{seed}:{row['id']}")
        if rng.random() < profile["mask_reference"]:
            changed["masked_nonempty_reference"] += bool(row["reference"])
            row["reference"] = ""
        delta = rng.randint(-profile["date_error_days"], profile["date_error_days"])
        row["date"] += timedelta(days=delta)
        changed["shifted_date"] += delta != 0
        result.append(row)
    return result, dict(changed)


def tokens(value):
    return frozenset(re.findall(r"[a-z0-9]+", value.lower()))


def match(ledger, bank, method, config=None):
    if method not in METHODS:
        raise ValueError("Unknown BenchRec method")
    config = config or Config()
    ledger = sorted(ledger, key=lambda row: row["id"])
    bank = sorted(bank, key=lambda row: row["id"])
    if len({r["id"] for r in ledger}) != len(ledger) or len({r["id"] for r in bank}) != len(bank):
        raise ValueError("Duplicate input IDs")
    amount_index, date_index = defaultdict(list), defaultdict(list)
    for a in ledger:
        scope = (a["currency"], a["account"])
        amount_index[(*scope, a["amount"])].append(a)
        date_index[(*scope, a["date"])].append(a)
    text = {("A", a["id"]): tokens(a["reference"]) for a in ledger}
    text.update({("B", b["id"]): tokens(b["reference"]) for b in bank})
    proposals, counters = {}, Counter()
    for b in bank:
        scope = (b["currency"], b["account"])
        candidates = [a for a in amount_index[(*scope, b["amount"])]
                      if abs((a["date"] - b["date"]).days) <= config.date_window_days]
        counters["amount_candidates"] += len(candidates)
        chosen = None
        if method in ("exact_amount_date", "bounded_group_sum"):
            exact = [a for a in candidates if a["date"] == b["date"]]
            if len(exact) == 1:
                chosen = exact
        elif method == "nearest_date":
            ranked = sorted((abs((a["date"] - b["date"]).days), a["id"], a) for a in candidates)
            if ranked and (len(ranked) == 1 or ranked[0][0] < ranked[1][0]):
                chosen = [ranked[0][2]]
        else:
            ranked = []
            bt = text[("B", b["id"])]
            for a in candidates:
                at = text[("A", a["id"])]
                similarity = len(bt & at) / len(bt | at) if bt | at else 0
                proximity = 1 - abs((a["date"] - b["date"]).days) / max(1, config.date_window_days)
                ranked.append((0.7 * similarity + 0.3 * proximity, a["id"], a))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            if (ranked and ranked[0][0] >= config.text_threshold
                    and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] > config.text_margin)):
                chosen = [ranked[0][2]]
        if method == "bounded_group_sum" and chosen is None:
            # Explicit bounded 1:N, same sign and date. Larger/mixed-sign/N:M
            # groups are left for review. Overflow is never truncated to first K.
            pool = [a for a in date_index[(*scope, b["date"]) ]
                    if a["amount"] * b["amount"] > 0 and abs(a["amount"]) < abs(b["amount"])]
            if len(pool) > config.group_candidate_cap:
                counters["group_pool_overflow_B"] += 1
            else:
                found = []
                for size in range(2, min(config.group_max_size, len(pool)) + 1):
                    for group in combinations(pool, size):
                        counters["group_combinations"] += 1
                        if sum(a["amount"] for a in group) == b["amount"]:
                            found.append(group)
                            if len(found) > 1:
                                break
                    if len(found) > 1:
                        break
                if len(found) == 1:
                    chosen = found[0]
        if chosen:
            proposals[b["id"]] = chosen
    # All proposals competing for an A row abstain: no arbitrary greedy order.
    usage = Counter(a["id"] for group in proposals.values() for a in group)
    predictions = {}
    for b_id, group in proposals.items():
        if all(usage[a["id"]] == 1 for a in group):
            predictions[b_id] = {"a_ids": sorted(a["id"] for a in group),
                                 "allocations": sorted({a["allocation"] for a in group})}
        else:
            counters["conflicting_B_abstained"] += 1
    errors = invariant_errors(ledger, bank, predictions)
    if errors:
        raise ValueError(f"BenchRec invariants failed: {errors}")
    return {"predictions": predictions, "prediction_hash": fingerprint(predictions),
            "invariant_errors": errors, "diagnostics": dict(counters), "config": asdict(config)}


def invariant_errors(ledger, bank, predictions):
    aa, bb = {a["id"]: a for a in ledger}, {b["id"]: b for b in bank}
    errors, used = Counter(), set()
    for b_id, prediction in predictions.items():
        if (not isinstance(prediction, dict) or not isinstance(prediction.get("a_ids"), list)
                or not isinstance(prediction.get("allocations"), list)
                or any(not isinstance(v, str) or not v.strip()
                       for v in prediction["a_ids"] + prediction["allocations"])):
            errors["malformed_prediction"] += 1
            continue
        ids = prediction["a_ids"]
        if b_id not in bb or not ids or any(i not in aa for i in ids):
            errors["unknown_or_empty_endpoint"] += 1
            continue
        group, b = [aa[i] for i in ids], bb[b_id]
        errors["A_reused"] += len(ids) - len(set(ids)) + len(used & set(ids))
        used.update(ids)
        errors["money_not_conserved"] += sum(a["amount"] for a in group) != b["amount"]
        errors["scope_mismatch"] += any((a["currency"], a["account"]) != (b["currency"], b["account"]) for a in group)
        errors["allocation_output_mismatch"] += set(prediction["allocations"]) != {a["allocation"] for a in group}
        errors["duplicate_allocation_keys"] += len(prediction["allocations"]) != len(set(prediction["allocations"]))
    return {key: count for key, count in errors.items() if count}


def score(bank, truth, predictions):
    if len({b["id"] for b in bank}) != len(bank):
        raise ValueError("Duplicate bank IDs")
    if set(truth) != {b["id"] for b in bank} or not set(predictions) <= set(truth):
        raise ValueError("Prediction/truth universe mismatch")
    if any(not isinstance(keys, (set, frozenset)) or any(not isinstance(k, str) or not k.strip() for k in keys)
           for keys in truth.values()):
        raise ValueError("Truth values must be allocation sets")
    for prediction in predictions.values():
        keys = prediction.get("allocations") if isinstance(prediction, dict) else None
        if (not isinstance(keys, list) or not keys
                or any(not isinstance(k, str) or not k.strip() for k in keys)
                or len(keys) != len(set(keys))):
            raise ValueError("Predicted allocation set must be nonempty and unique")
    correct = exact = 0
    money = defaultdict(lambda: {"bank_absolute": Decimal(0), "auto_absolute": Decimal(0),
                                  "wrong_allocation_absolute": Decimal(0)})
    strata = defaultdict(lambda: Counter())
    for b in bank:
        expected = truth[b["id"]]
        prediction = frozenset(predictions.get(b["id"], {}).get("allocations", []))
        ok = bool(prediction) and prediction <= expected
        correct += ok
        exact += bool(prediction) and prediction == expected
        row = money[b["currency"]]
        row["bank_absolute"] += abs(b["amount"])
        if prediction:
            row["auto_absolute"] += abs(b["amount"])
            if not ok:
                row["wrong_allocation_absolute"] += abs(b["amount"])
        group = strata["null" if not expected else "multiple_keys" if len(expected) > 1 else "one_key"]
        group.update(rows=1, predicted=int(bool(prediction)), correct=int(ok))
    n, positives, predicted = len(bank), sum(bool(v) for v in truth.values()), len(predictions)
    return {"B_rows": n, "positive_B": positives, "predicted_B": predicted, "correct_B": correct,
            "precision": correct / predicted if predicted else None,
            "match_rate": correct / positives if positives else None,
            "exact_set_precision": exact / predicted if predicted else None,
            "exact_set_recall": exact / positives if positives else None,
            "auto_rate": predicted / n if n else None,
            "review_rate": (n - predicted) / n if n else None,
            "money_by_currency": {c: {k: str(v) for k, v in values.items()} for c, values in money.items()},
            "by_label_cardinality": {k: dict(v) for k, v in strata.items()}}
