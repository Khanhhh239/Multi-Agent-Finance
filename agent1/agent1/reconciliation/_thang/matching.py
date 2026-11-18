"""Conservative reference rules and scored 1:1 assignment; no ground-truth access."""

from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
import re
import math
import unicodedata

from .data import allocation_errors, fingerprint


METHODS = ("exact_reference", "amount_date", "scored_global", "reference_then_global")
DEFAULT_FEE_TOLERANCE_VND = 55_000

_LEGAL_STOPWORDS = frozenset({
    "cong", "ty", "cty", "ct", "tnhh", "trach", "nhiem", "huu", "han",
    "mtv", "mot", "thanh", "vien", "cp", "co", "phan", "dntn", "doanh",
    "nghiep", "tu", "nhan", "hkd", "ho", "kinh", "tm", "thuong", "mai",
    "dv", "dich", "vu", "tmdv", "sx", "san", "xuat", "xd", "xay", "dung",
    "xnk", "nhap", "khau", "vn", "viet", "nam", "jsc", "ltd", "group",
})

_COMPACT_INV_PREFIX_RE = re.compile(
    r"(?<![a-z0-9])"
    r"(?P<prefix>hoa\s+don(?:\s+so)?|so\s+hoa\s+don|so\s+hd|hdon(?:\s+so)?|hd(?:\s+so)?|shd|sohd|hoadon|invoice(?:\s+no)?|inv(?:\s+no)?|bill(?:\s+no)?)"
    r"(?P<sep>[\s#:._-]*)"
    r"(?P<body>[a-z0-9]+(?:[-/_][a-z0-9]+)*(?:\s*(?:[,+&]|\bva\b)\s*(?:(?:hd|hdon|inv|shd|bill)\s*[-#:._]?\s*)?[a-z0-9]+(?:[-/_][a-z0-9]+)*)*)"
    r"(?![a-z0-9])"
)
_ITEM_SPLIT_RE = re.compile(r"\s*(?:[,+&]|\bva\b)\s*")
_REPEATED_PREFIX_RE = re.compile(r"^(?:hd|hdon|inv|shd|sohd|bill)[\s#:._-]*")
_DATE_LIKE_RE = re.compile(r"^(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})$")


@dataclass(frozen=True)
class Config:
    max_age_days: int = 120
    due_window_days: int = 14
    score_threshold: float = 0.72
    ambiguity_margin: float = 0.08
    fee_tolerance_vnd: int = DEFAULT_FEE_TOLERANCE_VND

    def __post_init__(self):
        if (type(self.max_age_days) is not int or type(self.due_window_days) is not int
                or self.max_age_days < 0 or self.due_window_days < 0):
            raise ValueError("date windows must be nonnegative")
        if type(self.fee_tolerance_vnd) is not int or self.fee_tolerance_vnd < 0:
            raise ValueError("fee_tolerance_vnd must be a nonnegative integer")
        if (any(type(v) not in (int, float) or not math.isfinite(v)
                for v in (self.score_threshold, self.ambiguity_margin))
                or not 0 <= self.score_threshold <= 1 or not 0 <= self.ambiguity_margin <= 1):
            raise ValueError("threshold/margin must be in [0, 1]")


def within_fee_tolerance(shortfall: int, target_minor: int, fee_tolerance_minor: int) -> bool:
    """True when 0 < shortfall <= fee_tolerance_minor and fee does not exceed 20% of target."""
    return (
        fee_tolerance_minor > 0
        and 0 < shortfall <= fee_tolerance_minor
        and shortfall * 5 <= target_minor
    )


def _fold(value) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "").casefold().replace("đ", "d"))
    return "".join(char for char in folded if not unicodedata.combining(char))


def normalize(text):
    return " ".join(re.findall(r"[a-z0-9]+", _fold(text)))


def normalize_party_name(text) -> str:
    tokens = normalize(text).split()
    core = [tok for tok in tokens if tok not in _LEGAL_STOPWORDS]
    return " ".join(core if core else tokens)


def resolve_counterparty(counterparty: str, reference: str, party_names: dict[str, set[str]]) -> str:
    """Resolve a unique party_id from exact or strong fuzzy counterparty match."""
    norm_cp = normalize(counterparty)
    if norm_cp:
        exact = party_names.get(norm_cp, set())
        if len(exact) == 1:
            return next(iter(exact))
    core_map: dict[str, set[str]] = {}
    for name_norm, pids in party_names.items():
        core = normalize_party_name(name_norm)
        if core:
            core_map.setdefault(core, set()).update(pids)
    cp_core = normalize_party_name(counterparty)
    if len(cp_core) >= 3:
        exact_core = core_map.get(cp_core, set())
        if len(exact_core) == 1:
            return next(iter(exact_core))
    if norm_cp:
        best_by_party: dict[str, float] = {}
        for name_norm, pids in party_names.items():
            if not name_norm or len(pids) != 1:
                continue
            pid = next(iter(pids))
            raw_sim = SequenceMatcher(None, norm_cp, name_norm, autojunk=False).ratio()
            c_name = normalize_party_name(name_norm)
            core_sim = (
                SequenceMatcher(None, cp_core, c_name, autojunk=False).ratio()
                if len(cp_core) >= 3 and len(c_name) >= 3
                else 0.0
            )
            sim = max(raw_sim, core_sim)
            if sim > best_by_party.get(pid, 0.0):
                best_by_party[pid] = sim
        ranked = sorted(best_by_party.items(), key=lambda kv: -kv[1])
        if ranked and ranked[0][1] >= 0.88 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 0.08):
            return ranked[0][0]
    norm_ref = f" {normalize(reference)} "
    if norm_ref.strip():
        memo_hits: set[str] = set()
        for core, pids in core_map.items():
            if len(core) >= 6 and len(core.split()) >= 2 and f" {core} " in norm_ref:
                memo_hits.update(pids)
        if len(memo_hits) == 1:
            return next(iter(memo_hits))
    return ""


def _iter_prefixed_refs(reference_text: str):
    folded = _fold(reference_text)
    for match in _COMPACT_INV_PREFIX_RE.finditer(folded):
        prefix = " ".join(match.group("prefix").split())
        sep = match.group("sep")
        body = match.group("body")
        first_item = True
        for part in _ITEM_SPLIT_RE.split(body):
            item = part.strip()
            if not first_item:
                item = _REPEATED_PREFIX_RE.sub("", item).strip()
            has_sep = bool(sep) or not first_item
            first_item = False
            if not item or _DATE_LIKE_RE.fullmatch(item):
                continue
            # Without separator (e.g. HD123, INV1024), require leading digit so HDBank ("HDB...") is never split.
            if not has_sep and not item[0].isdigit():
                break
            if not any(ch.isdigit() for ch in item):
                break
            yield prefix, item


def extract_invoice_refs(reference_text: str) -> list[str]:
    """Extract compact and prefixed Vietnamese/English invoice references from a bank narrative.

    Examples:
    - 'TT HD123' -> ['123']
    - 'THANH TOAN HD00123' -> ['00123', '123']
    - 'CT DEN CONG TY A HD-2026-045' -> ['2026-045']
    - 'INV1024' -> ['1024']
    """
    extracted: list[str] = []
    seen: set[str] = set()
    for _, item in _iter_prefixed_refs(reference_text):
        canonical_item = re.sub(r"[-/_]+", "-", item).strip("-")
        if canonical_item and canonical_item not in seen:
            seen.add(canonical_item)
            extracted.append(canonical_item)
        if canonical_item.isdigit():
            stripped = canonical_item.lstrip("0") or "0"
            if stripped not in seen:
                seen.add(stripped)
                extracted.append(stripped)
    return extracted


def reference_lookup_keys(reference_text: str) -> tuple[list[str], set[str]]:
    """Return (normalized_words, prefix_qualified_keys) for fast exact + compact ref lookup."""
    words = normalize(reference_text).split()
    prefixed_keys: set[str] = set()
    for prefix, item in _iter_prefixed_refs(reference_text):
        norm_item = normalize(item)
        if not norm_item:
            continue
        prefixed_keys.add(norm_item)
        canon_prefix = "inv" if prefix.startswith("inv") else ("bill" if prefix.startswith("bill") else "hd")
        prefixed_keys.add(f"{canon_prefix} {norm_item}")
        prefixed_keys.add(f"{canon_prefix}{norm_item.replace(' ', '')}")
        if norm_item.isdigit():
            stripped = norm_item.lstrip("0") or "0"
            prefixed_keys.add(stripped)
    return words, prefixed_keys


def index_invoice_number(invoice_number: str) -> tuple[str, set[str]]:
    """Return (exact_normalized_key, prefix_qualified_alias_keys) for an invoice number."""
    exact = normalize(invoice_number)
    aliases: set[str] = set()
    if not exact:
        return "", aliases
    if exact.isdigit():
        aliases.add(exact.lstrip("0") or "0")
    parts = exact.split()
    if len(parts) >= 2 and parts[0] in {"hd", "hdon", "shd", "sohd", "inv", "invoice", "bill"}:
        canon = "inv" if parts[0] in {"inv", "invoice"} else ("bill" if parts[0] == "bill" else "hd")
        rest = " ".join(parts[1:])
        aliases.add(f"{canon} {rest}")
        aliases.add(f"{canon}{rest.replace(' ', '')}")
    return exact, aliases


def references(bank, invoice):
    # Token boundaries prevent INV-1 matching INV-10 while supporting compact forms like HD123 / INV1024.
    exact, aliases = index_invoice_number(invoice["invoice_id"])
    if not exact:
        return False
    words, prefixed_keys = reference_lookup_keys(bank["reference"])
    joined = f" {' '.join(words)} "
    if f" {exact} " in joined:
        return True
    return exact in prefixed_keys or bool(aliases & prefixed_keys)


def eligible(bank, invoice, config):
    age = (date.fromisoformat(bank["booked_on"])
           - date.fromisoformat(invoice["issued_on"])).days
    return (bank["tenant_id"] == invoice["tenant_id"]
            and bank["currency"] == invoice["currency"]
            and (not bank["customer_id"] or bank["customer_id"] == invoice["customer_id"])
            and 0 <= age <= config.max_age_days)


def score(bank, invoice, config):
    if references(bank, invoice):
        return 1.0
    bank_name, invoice_name = normalize(bank["counterparty"]), normalize(invoice["customer_name"])
    bank_core, invoice_core = normalize_party_name(bank["counterparty"]), normalize_party_name(invoice["customer_name"])
    raw_name = (SequenceMatcher(None, bank_name, invoice_name, autojunk=False).ratio()
                if bank_name and invoice_name else 0.0)
    core_name = (SequenceMatcher(None, bank_core, invoice_core, autojunk=False).ratio()
                 if bank_core and invoice_core else 0.0)
    name = max(raw_name, core_name)
    if not bank_name and invoice_core and len(invoice_core) >= 4:
        memo_norm = f" {normalize(bank.get('reference', ''))} "
        if f" {invoice_core} " in memo_norm:
            name = max(name, 0.85)
    identity = 1.0 if bank["customer_id"] else name
    lag = abs((date.fromisoformat(bank["booked_on"])
               - date.fromisoformat(invoice["due_on"])).days)
    proximity = max(0.0, 1 - lag / max(1, config.due_window_days))
    return round(0.65 * identity + 0.25 * name + 0.10 * proximity, 8)


def maximum_weight_assignment(weights):
    """Hungarian assignment with one dummy unmatched column per bank row.

    Forbidden edges are negative; dummy edges have zero weight. Returns real,
    positive edges only. Deterministic when rows/columns have stable ordering.
    """
    n = len(weights)
    m_real = len(weights[0]) if n else 0
    if any(len(row) != m_real for row in weights):
        raise ValueError("ragged weight matrix")
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for row in weights for value in row):
        raise ValueError("assignment weights must be finite numbers")
    if not n or not m_real:
        return []
    costs = [[-v for v in row] + [0.0] * n for row in weights]
    m = m_real + n
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0, used, minimum = 0, [False] * (m + 1), [float("inf")] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    current = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return [(p[j] - 1, j - 1) for j in range(1, m_real + 1)
            if p[j] and weights[p[j] - 1][j - 1] > 0]


def reconcile(invoices, bank, method="reference_then_global", config=None):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    config = config or Config()
    invoices = sorted(invoices, key=lambda r: (r["tenant_id"], r["invoice_id"]))
    bank = sorted(bank, key=lambda r: (r["booked_on"], r["tenant_id"], r["transaction_id"]))
    remaining = {(r["tenant_id"], r["invoice_id"]): r["amount_minor"] for r in invoices}
    allocations, used, candidate_edges = [], set(), set()

    def add(b, i, amount, confidence, reason, fee_minor=0):
        allocations.append({"tenant_id": b["tenant_id"], "transaction_id": b["transaction_id"],
                            "invoice_id": i["invoice_id"], "currency": b["currency"],
                            "amount_minor": amount, "fee_minor": fee_minor, "payment_on": b["booked_on"],
                            "score": confidence, "reason": reason})
        remaining[(i["tenant_id"], i["invoice_id"])] -= amount

    if method in ("exact_reference", "reference_then_global"):
        for bi, b in enumerate(bank):
            fee_tol = config.fee_tolerance_vnd if b["currency"] == "VND" else 0
            candidates = [i for i in invoices if eligible(b, i, config)
                          and remaining[(i["tenant_id"], i["invoice_id"])] > 0 and references(b, i)]
            for i in candidates:
                candidate_edges.add((b["tenant_id"], b["transaction_id"], i["invoice_id"]))
            # Repeated invoice numbers belonging to several buyers are ambiguous.
            if len({normalize(i["invoice_id"]) for i in candidates}) != len(candidates):
                continue
            if len({i["customer_id"] for i in candidates}) > 1:
                continue
            balances = [remaining[(i["tenant_id"], i["invoice_id"])] for i in candidates]
            amount = b["amount_minor"]
            if len(candidates) == 1:
                fee_gap = balances[0] - amount
                fee_ok = within_fee_tolerance(fee_gap, balances[0], fee_tol)
                if (method == "exact_reference" and (amount == balances[0] or fee_ok)) or (
                        method == "reference_then_global" and amount <= balances[0]):
                    add(b, candidates[0], amount, 1.0, "reference", fee_minor=fee_gap if fee_ok else 0)
                    used.add(bi)
            elif method == "reference_then_global" and candidates and all(v > 0 for v in balances):
                total_bal = sum(balances)
                fee_gap = total_bal - amount
                if total_bal == amount:
                    for i, balance in zip(candidates, balances):
                        add(b, i, balance, 1.0, "reference_group")
                    used.add(bi)
                elif within_fee_tolerance(fee_gap, total_bal, fee_tol) and balances[-1] > fee_gap:
                    for i, balance in zip(candidates[:-1], balances[:-1]):
                        add(b, i, balance, 1.0, "reference_group", fee_minor=0)
                    add(b, candidates[-1], balances[-1] - fee_gap, 1.0, "reference_group", fee_minor=fee_gap)
                    used.add(bi)

    if method != "exact_reference":
        pending = [(j, b) for j, b in enumerate(bank) if j not in used]
        open_invoices = [i for i in invoices if remaining[(i["tenant_id"], i["invoice_id"])] > 0]
        weights = []
        for _, b in pending:
            fee_tol = config.fee_tolerance_vnd if b["currency"] == "VND" else 0
            known_references = {i["invoice_id"] for i in open_invoices
                                if eligible(b, i, config) and references(b, i)}
            row = []
            for i in open_invoices:
                bal = remaining[(i["tenant_id"], i["invoice_id"])]
                full_amount = bal == b["amount_minor"]
                fee_ok = within_fee_tolerance(bal - b["amount_minor"], bal, fee_tol)
                due_gap = abs((date.fromisoformat(b["booked_on"])
                               - date.fromisoformat(i["due_on"])).days)
                is_eligible = eligible(b, i, config)
                s = score(b, i, config) if is_eligible else -1.0
                # Populate fuzzy candidate_edges even when exact amount misses (partial payment / fee deduction).
                if is_eligible and (full_amount or fee_ok or i["invoice_id"] in known_references
                                    or (method != "amount_date" and s >= config.score_threshold)):
                    candidate_edges.add((b["tenant_id"], b["transaction_id"], i["invoice_id"]))
                valid = is_eligible and (full_amount or (fee_ok and (i["invoice_id"] in known_references or s >= config.score_threshold)))
                if known_references:
                    valid = valid and i["invoice_id"] in known_references
                if method == "amount_date" and not known_references:
                    valid = valid and due_gap <= config.due_window_days
                row.append((1.0 if (method == "amount_date" or i["invoice_id"] in known_references) else s)
                           if valid else -1.0)
            weights.append(row)
        # Abstain when a bank row or an invoice has nearly tied alternatives.
        # Score thresholds are engineering defaults, not calibrated probabilities.
        safe = [[-1.0] * len(open_invoices) for _ in pending]
        threshold = 0.5 if method == "amount_date" else config.score_threshold
        for bi, row in enumerate(weights):
            for ii, weight in enumerate(row):
                if weight < threshold:
                    continue
                alternatives = [v for j, v in enumerate(row) if j != ii and v >= threshold]
                alternatives += [r[ii] for j, r in enumerate(weights) if j != bi and r[ii] >= threshold]
                if alternatives and weight - max(alternatives) <= config.ambiguity_margin:
                    continue
                safe[bi][ii] = weight
        for bi, ii in maximum_weight_assignment(safe):
            original, b = pending[bi]
            i = open_invoices[ii]
            bal = remaining[(i["tenant_id"], i["invoice_id"])]
            fee_tol = config.fee_tolerance_vnd if b["currency"] == "VND" else 0
            fee_gap = bal - b["amount_minor"]
            fee_minor = fee_gap if within_fee_tolerance(fee_gap, bal, fee_tol) else 0
            add(b, i, b["amount_minor"], safe[bi][ii], method, fee_minor=fee_minor)
            used.add(original)

    errors = allocation_errors(invoices, bank, allocations)
    if errors:
        raise ValueError(f"allocation invariant failure: {errors}")
    allocations.sort(key=lambda a: (a["tenant_id"], a["transaction_id"], a["invoice_id"]))
    fees_by_tx = {}
    for a in allocations:
        key = (a["tenant_id"], a["transaction_id"])
        fees_by_tx[key] = fees_by_tx.get(key, 0) + a.get("fee_minor", 0)
    statuses = [{"tenant_id": b["tenant_id"], "transaction_id": b["transaction_id"],
                 "fee_minor": fees_by_tx.get((b["tenant_id"], b["transaction_id"]), 0),
                 "status": "auto" if j in used else (
                     "review" if any(e[:2] == (b["tenant_id"], b["transaction_id"]) for e in candidate_edges)
                     else "unmatched")}
                for j, b in enumerate(bank)]
    return {"method": method, "config": asdict(config), "allocations": allocations,
            "decisions": statuses, "candidate_edges": sorted(candidate_edges),
            "allocation_hash": fingerprint(allocations), "invariant_errors": errors}
