"""Cash-full T1 hazards plus a separately learned partial-payment branch.

The same transition and ratio law drives exact cash expectations and repeated
receipt paths. A partial receipt never changes T1's settlement event probability.
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass

import numpy as np
import pandas as pd

VERSION = "settlement-partial-cash-v2"
LABEL_CONTRACT = "cash-calendar-full-settlement-v2"


def probabilities(distribution, rows=None):
    p = np.asarray(distribution, float)
    if (p.ndim != 2 or p.shape[1] < 2 or rows is not None and len(p) != rows
            or not np.isfinite(p).all() or (p < 0).any()
            or not np.allclose(p.sum(1), 1, atol=1e-10, rtol=0)):
        raise ValueError("Phân phối tất toán T1 không hợp lệ")
    return p


def receipt_state(frame):
    if "received_fraction" in frame:
        return frame.received_fraction.to_numpy(float) > 0
    return frame.received.to_numpy(float) > 0


def overdue(frame):
    if frame.empty:
        return np.zeros(0)
    if "age_days" in frame:
        return frame.age_days.to_numpy(float) - frame.term_days.to_numpy(float)
    clock = pd.Timestamp(frame.attrs["cutoff"])
    return ((clock - frame.issue_date).dt.days.clip(0, 730).to_numpy(float)
            - (frame.due_date - frame.issue_date).dt.days.clip(0, 365).to_numpy(float))


def bins(late, received, week):
    # All six cells include invoices that have never received cash. State is
    # updated after the first future partial receipt in both engines below.
    age = np.digitize(late + 7 * week, [1, 91])
    return age * 2 + np.asarray(received, int)


@dataclass
class PartialModel:
    probability: np.ndarray
    ratios: tuple
    weights: tuple
    fitted_through: str
    evidence: dict
    version: str = VERSION

    def __post_init__(self):
        self.probability = np.asarray(self.probability, float)
        if (self.probability.shape != (6,) or not np.isfinite(self.probability).all()
                or (self.probability < 0).any() or (self.probability > 1).any()
                or len(self.ratios) != 6 or len(self.weights) != 6):
            raise ValueError("Nhánh partial không hợp lệ")
        for values, weights in zip(self.ratios, self.weights):
            a, w = np.asarray(values, float), np.asarray(weights, float)
            if (a.ndim != 1 or not len(a) or w.shape != a.shape
                    or not np.isfinite(a).all() or not np.isfinite(w).all()
                    or (a <= 0).any() or (a >= 1).any() or (w < 0).any()
                    or not np.isclose(w.sum(), 1)):
                raise ValueError("Phân phối tỷ lệ partial không hợp lệ")

    @property
    def digest(self):
        return hashlib.sha256(pickle.dumps(self, protocol=4)).hexdigest()

    @property
    def means(self):
        return np.array([np.dot(v, w) for v, w in zip(self.ratios, self.weights)])

    def record(self):
        return dict(probability=self.probability.tolist(), ratios=[np.asarray(v).tolist() for v in self.ratios],
                    weights=[np.asarray(w).tolist() for w in self.weights], fitted_through=self.fitted_through,
                    evidence=self.evidence, version=self.version)

    @classmethod
    def from_record(cls, record):
        return cls(**dict(record, ratios=tuple(np.asarray(v) for v in record["ratios"]),
                          weights=tuple(np.asarray(w) for w in record["weights"])))


def fit_partial(frame, cutoff, *, prior, strength=30.0, half_life_days=180.0):
    """Weighted empirical incidence and ratios, shrunk to the frozen global law.

    Only fully covered, non-settling weeks are Bernoulli partial observations.
    Incomplete weeks and weeks containing cash settlement are excluded. Local
    influence uses effective sample size, capped by distinct invoice/week keys.
    """
    cutoff = pd.Timestamp(cutoff).normalize()
    if prior is not None and pd.Timestamp(prior.fitted_through) > cutoff:
        raise ValueError("Prior partial được học sau ngày chốt")
    if not np.isfinite(strength) or strength <= 0 or half_life_days <= 0:
        raise ValueError("Điều chuẩn partial không hợp lệ")
    cells = [[] for _ in range(6)]
    if not frame.empty:
        if (pd.to_datetime(frame.label_end) > cutoff).any():
            raise ValueError("Nhãn partial vượt ngày chốt")
        cash = frame[[f"cash_{w}" for w in range(1, 14)]].to_numpy(float)
        ids = frame.invoice_id.astype(str).to_numpy()
        origins = pd.to_datetime(frame.origin)
        remaining = np.ones(len(frame))
        state = receipt_state(frame)
        late = overdue(frame)
        for week in range(13):
            ends = origins + pd.Timedelta(days=7 * (week + 1))
            decay = np.exp2(-(cutoff - ends).dt.days.to_numpy(float) / half_life_days)
            dates = ends.dt.strftime("%Y-%m-%d").to_numpy()
            complete = frame.followup_days.to_numpy(float) >= 7 * (week + 1)
            no_settlement = frame.paid_days.to_numpy(float) > 7 * (week + 1)
            eligible = complete & no_settlement & (remaining > 1e-8)
            ratios = np.divide(cash[:, week], remaining, out=np.zeros(len(frame)), where=remaining > 1e-8)
            groups = bins(late, state, week)
            for i in np.flatnonzero(eligible):
                if not 0 <= ratios[i] < 1:
                    raise ValueError("Nhãn partial phải nhỏ hơn dư nợ đầu tuần")
                cells[groups[i]].append((ids[i], dates[i], ratios[i], decay[i]))
            remaining = np.maximum(0, remaining - cash[:, week])
            state |= cash[:, week] > 0
    ps, values, weights, evidence = [], [], [], []
    for group, samples in enumerate(cells):
        # De-duplicate overlapping origins representing exactly the same week.
        samples = list({(s[0], s[1]): s for s in samples}.values())
        ratios = np.array([s[2] for s in samples])
        w = np.array([s[3] for s in samples])
        n = float(w.sum() ** 2 / np.dot(w, w)) if len(w) else 0.0
        if len(w):
            w = w * n / w.sum()
        positive = ratios > 0
        # No fabricated partial behavior: an empty global cell has zero
        # incidence. Its ratio atom is unreachable until evidence is observed.
        prior_p = prior.probability[group] if prior else 0.0
        prior_values = np.asarray(prior.ratios[group] if prior else [0.5])
        prior_w = np.asarray(prior.weights[group] if prior else [1.0])
        positive_mass = float(w[positive].sum())
        ps.append((positive_mass + strength * prior_p) / (n + strength))
        v = np.r_[prior_values, ratios[positive]]
        rw = np.r_[prior_w * strength, w[positive]]
        order = np.argsort(v, kind="stable")
        v, rw = v[order], rw[order] / rw.sum()
        # Bounded weighted empirical quantiles keep tenant artifacts compact.
        if len(v) > 256:
            v = v[np.searchsorted(np.cumsum(rw), (np.arange(256) + 0.5) / 256)]
            rw = np.full(256, 1 / 256)
        values.append(v)
        weights.append(rw)
        evidence.append(dict(weeks=len(samples), effective_weeks=n, partial_weeks=int(positive.sum())))
    return PartialModel(np.asarray(ps), tuple(values), tuple(weights), str(cutoff.date()),
                        dict(cells=evidence, prior_sha256=prior.digest if prior else None,
                             prior_strength=strength, label_contract=LABEL_CONTRACT))


def expected_cash_components(distribution, frame, partial):
    """Exact cash law with auditable settlement/partial and residual components.

    All money arrays are fractions of debt at the forecast cutoff, including
    debt already reduced by real receipts/credits. State masses are unconditional
    expected debt, not conditional balances to multiply by T1 a second time.
    """
    if partial is None or partial.version != VERSION:
        raise ValueError("Cần nhánh partial đã fit để chuyển T1 thành dòng tiền")
    p = probabilities(distribution, len(frame))
    late, state = overdue(frame), receipt_state(frame)
    remaining = np.column_stack((~state, state)).astype(float)
    tail = np.flip(np.cumsum(np.flip(p, axis=1), axis=1), axis=1)
    result = np.zeros_like(p)
    settlement = np.zeros_like(p[:, :-1])
    pieces_total = np.zeros_like(settlement)
    opening = np.zeros_like(settlement)
    closing = np.zeros_like(settlement)
    hazards = np.zeros_like(settlement)
    states = np.zeros((len(p), p.shape[1] - 1, 2))
    groups = np.zeros_like(states, dtype=int)
    means = partial.means
    for week in range(p.shape[1] - 1):
        h = np.divide(p[:, week], tail[:, week], out=np.zeros(len(p)), where=tail[:, week] > 0)
        group = np.column_stack([bins(late, np.full(len(p), s), week) for s in (0, 1)])
        q, ratio = partial.probability[group], means[group]
        opening[:, week] = remaining.sum(1)
        states[:, week] = remaining
        groups[:, week] = group
        hazards[:, week] = h
        alive = remaining * (1 - h[:, None])
        pieces = alive * q * ratio
        settlement[:, week] = remaining.sum(1) * h
        pieces_total[:, week] = pieces.sum(1)
        result[:, week] = settlement[:, week] + pieces_total[:, week]
        # Zero-receipt state moves to positive state only on a partial event.
        remaining[:, 0] = alive[:, 0] * (1 - q[:, 0])
        remaining[:, 1] = alive[:, 1] - pieces[:, 1] + alive[:, 0] * q[:, 0] * (1 - ratio[:, 0])
        closing[:, week] = remaining.sum(1)
    result[:, -1] = remaining.sum(1)
    return dict(cash=result, settlement=settlement, partial=pieces_total,
                opening=opening, remaining=closing, hazard=hazards,
                state_debt=states, cells=groups)


def expected_cash(distribution, frame, partial):
    """The same exact law used by engine explanations and simulation audits."""
    return expected_cash_components(distribution, frame, partial)["cash"]


@dataclass(frozen=True)
class InvoiceCashPaths:
    invoice_id: str
    receipts: np.ndarray
    remaining: np.ndarray
    # One-based cash-full event week; horizon + 1 denotes the T1 tail.
    settlement_week: np.ndarray


def iter_cash_paths(distribution, frame, partial, amounts, rng, paths, *, shared_customer=False):
    """Yield a complete receipt/balance history per invoice, using bounded memory.

    The latent cash-full event follows T1 even on paths with earlier partials.
    Tail is a timing category, never a second write-off probability.
    """
    if partial is None or partial.version != VERSION:
        raise ValueError("Cần nhánh partial đã fit để chuyển T1 thành dòng tiền")
    if type(paths) is not int or paths < 1:
        raise ValueError("Số đường mô phỏng phải là số nguyên dương")
    p = probabilities(distribution, len(frame))
    amounts = np.asarray(amounts, float)
    if amounts.shape != (len(p),) or not np.isfinite(amounts).all() or (amounts < 0).any():
        raise ValueError("Dư nợ mô phỏng không hợp lệ")
    horizon = p.shape[1] - 1
    late, initial = overdue(frame), receipt_state(frame)
    customers = frame.customer_id.astype(str).to_numpy()
    shared = {}
    for i in range(len(p)):
        if shared_customer:
            if customers[i] not in shared:
                shared[customers[i]] = rng.random((3, paths, horizon))
            draws = shared[customers[i]]
        else:
            draws = rng.random((3, paths, horizon))
        remaining = np.full(paths, float(amounts[i]))
        received = np.full(paths, initial[i])
        receipts = np.zeros((paths, horizon))
        balances = np.zeros_like(receipts)
        settlement_week = np.full(paths, horizon + 1, dtype=int)
        for week in range(horizon):
            tail = p[i, week:].sum()
            h = p[i, week] / tail if tail > 0 else 0.0
            active = settlement_week == horizon + 1
            settled = active & (draws[0, :, week] < h)
            settlement_week[settled] = week + 1
            group = bins(late[i], received, week)
            pay = active & ~settled & (draws[1, :, week] < partial.probability[group])
            fraction = np.zeros(paths)
            fraction[settled] = 1.0
            for cell in np.unique(group[pay]):
                take = pay & (group == cell)
                indices = np.searchsorted(np.cumsum(partial.weights[cell]), draws[2, take, week])
                fraction[take] = np.asarray(partial.ratios[cell])[np.minimum(indices, len(partial.ratios[cell]) - 1)]
            cash = remaining * fraction
            receipts[:, week] = cash
            remaining -= cash
            balances[:, week] = remaining
            received |= cash > 0
        yield InvoiceCashPaths(str(frame.iloc[i].invoice_id), receipts, balances, settlement_week)


def sample_cash(distribution, frame, partial, amounts, rng, paths, *, shared_customer=False):
    """Aggregate the same per-invoice receipt paths used by acceptance audits."""
    p = probabilities(distribution, len(frame))
    result = np.zeros((paths, p.shape[1] - 1))
    for invoice in iter_cash_paths(p, frame, partial, amounts, rng, paths,
                                   shared_customer=shared_customer):
        result += invoice.receipts
    return result


def bundle_version(model, partial):
    return "bundle:" + hashlib.sha256(pickle.dumps((model, partial), protocol=4)).hexdigest()[:24]
