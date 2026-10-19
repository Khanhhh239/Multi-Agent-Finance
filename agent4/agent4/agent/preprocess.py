"""Metadata-only hints; financial arithmetic belongs exclusively to the engine.

Experimental: công thức chưa được kế toán duyệt (G0.7 mở).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from agent4.engine import periods as P
from agent4.engine.metrics import REGISTRY
from .untrusted import clean_text, wrap_untrusted

_CONFIG = json.loads((Path(__file__).parent / "data" / "preprocess_patterns.yml").read_text(encoding="utf-8"))
_PATTERNS = {key: [re.compile(pattern, re.I) for pattern in values] for key, values in _CONFIG.items()}


@dataclass(frozen=True)
class PeriodHit:
    text: str
    period: P.Period


@dataclass(frozen=True)
class EntityHit:
    kind: str
    text: str
    codes: list[str]


@dataclass
class Hints:
    periods: list[PeriodHit] = field(default_factory=list)
    compare: str | None = None
    entities: list[EntityHit] = field(default_factory=list)
    view_hint: str | None = None
    cues: set[str] = field(default_factory=set)
    normalized: str = ""
    no_accent: str = ""
    group_by: str | None = None
    params: dict = field(default_factory=dict)
    inherited: dict = field(default_factory=dict)
    metric_hint: str | None = None
    action_hint: str | None = None

    def data(self) -> dict:
        """Prompt-safe projection: no unwrapped names or inherited free text."""
        def safe(value: Any):
            if isinstance(value, str):
                return wrap_untrusted(value, "hints")
            if isinstance(value, dict):
                return {key: safe(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [safe(item) for item in value]
            return value

        return {
            "periods": [{"text": wrap_untrusted(hit.text, "question.period"),
                         "period": hit.period.as_dict()} for hit in self.periods],
            "compare": self.compare,
            "entities": [{"kind": hit.kind, "text": wrap_untrusted(hit.text, "entity"),
                          "codes": list(hit.codes)} for hit in self.entities],
            "view_hint": self.view_hint, "cues": sorted(self.cues),
            "group_by": self.group_by, "params": dict(self.params),
            "metric_hint": self.metric_hint, "action_hint": self.action_hint,
            "inherited": safe(self.inherited),
        }


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", P.strip_accents(str(text).lower())).strip()


_STOP = {"cong", "ty", "tnhh", "co", "phan", "cp", "mtv", "tap", "doan", "chi", "nhanh", "phong"}


def _pools(engine):
    partners = getattr(engine, "partners", {})
    yield "customer", {code: row["name"] for code, row in partners.items() if row["type"] == "CUSTOMER"}
    yield "vendor", {code: row["name"] for code, row in partners.items() if row["type"] == "VENDOR"}
    for kind, attr in (("branch", "branches"), ("department", "departments"),
                       ("cost_category", "cost_categories"), ("product_line", "product_lines"),
                       ("item", "items"), ("salesperson", "employees")):
        yield kind, getattr(engine, attr, {})


def _entities(question: str, engine) -> list[EntityHit]:
    words = _words(question)
    padded = f" {words} "
    grouped: dict[tuple[str, str], list[str]] = {}
    context = {"customer": r"khach(?: hang)?", "vendor": r"nha cung cap|ncc",
               "branch": r"chi nhanh", "department": r"phong(?: ban)?|bo phan", "item": r"mat hang",
               "salesperson": r"nhan vien"}
    for kind, pool in _pools(engine):
        for code, raw_name in pool.items():
            name = _words(raw_name)
            short = " ".join(word for word in name.split() if word not in _STOP)
            code_text = _words(code)
            # Match codes against the original Unicode text: accent folding
            # would turn "còn" into product-line code CON. Short codes also
            # need literal capitals or explicit dimension context.
            has_context = kind in context and bool(re.search(context[kind], words))
            code_pattern = rf"(?<!\w){re.escape(str(code))}(?!\w)"
            exact_code = re.search(code_pattern, question) or (
                (len(str(code)) > 3 or has_context) and re.search(code_pattern, question, re.I)
            )
            aliases = [name]
            if len(short.split()) >= 2 and (kind != "department" or has_context):
                aliases.append(short)
            if kind == "branch":
                aliases.append(re.sub(r"^(?:chi nhanh |tru so )?(?:tp |thanh pho )?", "", name))
            if kind in context and re.search(context[kind], words):
                if kind in ("customer", "vendor") and len(short.split()) >= 2:
                    aliases.extend([" ".join(short.split()[-2:]), " ".join(short.split()[-3:])])
                elif kind == "department" and short:
                    aliases.append(short)
            # Codes are whole tokens; a single common name-word is never enough.
            matched = code_text if exact_code else next(
                (alias for alias in aliases if alias and f" {alias} " in padded), None
            )
            if not matched and kind in context and re.search(context[kind], words):
                tokens = words.split()
                target = short if len(short.split()) >= 2 else name
                size = len(target.split())
                if size >= 2:
                    spans = [" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]
                    near = [(SequenceMatcher(None, target, span).ratio(), span) for span in spans]
                    score, best = max(near, default=(0, ""))
                    # One near spelling error; never fuzzy-match arbitrary prompt text.
                    if score >= 0.92 and abs(len(target) - len(best)) <= 2:
                        matched = best
            if matched:
                grouped.setdefault((kind, matched), []).append(str(code))
    return [EntityHit(kind, text, sorted(set(codes))) for (kind, text), codes in grouped.items()]


def _state_value(state, name):
    return state.get(name) if isinstance(state, dict) else getattr(state, name, None)


def explicit_metric(question: str) -> str | None:
    """Unique explicit registry phrase, excluding nested shorter aliases.

    Multiple independent metric mentions remain unresolved. No scores, ledger
    values or formulas enter this lexical consistency check.
    """
    words = _words(question)
    hits = set()
    for metric, definition in REGISTRY.items():
        for phrase in (definition.label, *definition.synonyms):
            phrase = _words(phrase)
            if len(phrase.split()) < 2:
                continue
            for match in re.finditer(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', words):
                hits.add((match.start(), match.end(), metric))
    maximal = {metric for start, end, metric in hits if not any(
        left <= start and right >= end and (left < start or right > end)
        for left, right, _ in hits)}
    return next(iter(maximal)) if len(maximal) == 1 else None


def analyze(question: str, engine, state=None, as_of=None) -> Hints:
    if not isinstance(question, str):
        raise TypeError("Câu hỏi phải là văn bản.")
    normalized = re.sub(r"\s+", " ", clean_text(unicodedata.normalize("NFC", question))).strip()
    plain = P.strip_accents(normalized.lower())
    cutoff = as_of or engine.as_of
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    hints = Hints(normalized=normalized, no_accent=plain)
    hints.metric_hint = explicit_metric(normalized)
    hints.periods = [PeriodHit(text, period) for text, period in P.extract_periods(normalized, cutoff)]
    hints.compare = P.detect_comparison(normalized)
    if not hints.compare and re.search(r"\bso (?:voi )?(?:thang|quy|ky|tuan) truoc\b", plain):
        hints.compare = "previous_period"
    hints.entities = _entities(normalized, engine)
    if any(len(hit.codes) > 1 for hit in hints.entities):
        hints.cues.add("needs_clarification")
    tax_signal=any(pattern.search(plain) for pattern in _PATTERNS["tax"]) or (
        hints.metric_hint and REGISTRY[hints.metric_hint].default_view=='tax')
    if tax_signal:
        explicit_mgmt=re.search(r'\b(?:theo|khung|so|goc nhin)\s*(?:khung\s*)?(?:quan tri|dieu hanh)\b',plain)
        hints.view_hint = 'mgmt' if explicit_mgmt else 'tax'
    for cue in ("unsafe_action", "out_of_scope", "jailbreak"):
        if any(pattern.search(plain) for pattern in _PATTERNS[cue]):
            hints.cues.add(cue)
    if re.search(r"\bloi nhuan\b", plain) and not hints.metric_hint and not re.search(
        r"loi nhuan (?:gop|rong|thuan|truoc thue|sau thue)|thu nhap chiu thue", plain
    ):
        hints.cues.add("needs_clarification")
    for dimension in ("salesperson", "customer", "vendor", "branch", "department", "product_line", "cost_category", "item", "account", "month", "quarter", "year"):
        if any(pattern.search(plain) for pattern in _PATTERNS["group_" + dimension]):
            hints.group_by = dimension
            break
    if match := re.search(r"(?:qua han|cham tra) (?:tren |hon )?(\d+) ngay", plain):
        hints.params["min_days"] = int(match.group(1))
    if re.search(r'\b(?:cong thuc|cach tinh|nguon so lieu|but toan)\b', plain):
        hints.action_hint = 'explain_metric'
    elif hints.group_by:
        hints.action_hint = 'query_metric'
    if match := re.search(r"(?:trong )?(\d+) ngay (?:toi|sap toi|ke tiep|tiep theo)", plain):
        hints.params["days"] = int(match.group(1))
    if re.search(r"ngay (?:bao co|thu ngan hang)|theo ngay ngan hang", plain):
        hints.params["date_basis"] = "bank"
    elif re.search(r"theo ngay (?:thu tien|phieu thu)", plain):
        hints.params["date_basis"] = "receipt"
    # Inheritance is only a hint. Explicit parameters always override state.
    if state is not None and re.search(r"^(?:con|vay|the)\b|\b(?:thang do|quy do|cung ky do|khach ay)\b", plain):
        for source, target in (("last_metric", "metric"), ("last_period", "period"),
                               ("last_filters", "filters"), ("last_group_by", "group_by"),
                               ("last_view", "view")):
            value = _state_value(state, source)
            if value is not None and not (target == "period" and hints.periods) and not (
                target == "group_by" and hints.group_by
            ) and not (target == "view" and hints.view_hint):
                hints.inherited[target] = value
    return hints
