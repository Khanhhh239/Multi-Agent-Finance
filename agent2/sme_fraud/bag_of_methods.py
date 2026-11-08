"""Bag of methods, chosen per company by injecting known fraud patterns into that company's own ledger features.

Why: a small company has plenty of transactions but almost no confirmed fraud labels, so no method can be chosen by
labelled accuracy. Instead (1) fit several label-free detectors on the first part of the company's training rows,
(2) clone real rows of the later part and bend their features the way a fraud pattern would (families below, three
concealment levels), (3) measure how often each detector or ensemble lifts those clones above the company's own real
rows at a fixed alert rate, (4) keep the best candidate, and (5) report an honest estimate for a pattern family the
choice never saw (nested leave-one-family-out). Hard rules, the probabilistic rules and the relationship graph are not
touched; this module only chooses and combines the ML layer, which stays in shadow.

Limits, stated in `diagnostics_`: injected patterns are known patterns written in feature space, real rows may already
hold undiscovered fraud (treated as normal), and the choice leans toward the patterns injected. Scores are on a
tail-probability ("surprise") scale: larger means more unusual. Every number produced here is a measurement on the
company's own data plus synthetic injections, never a fraud probability.
"""
from __future__ import annotations

import numpy as np
from sklearn.covariance import OAS
from sklearn.linear_model import Ridge

from .ml_estimators import matrix

SEED = 42
ALERT_RATE = .05          # share of the company's real rows allowed above the threshold (budget proxy)
MIN_ROWS = 60             # 70/30 inner split needs at least 42 fit rows and 18 validation rows
FIT_SHARE = .7
CLONES = 30               # clones per (family, level)
BASELINE = 'mean_all'
MARGIN = .02              # a candidate must beat the baseline by this much to be preferred


# ------------------------------------------------------------------ component methods (all label-free)
class RobustZ:
    """Sum of the largest robust z-scores (median/MAD with a floor), a simple probabilistic rule layer."""
    def fit(self, x):
        self.med_ = np.median(x, axis=0)
        mad = np.median(np.abs(x - self.med_), axis=0) * 1.4826
        self.scale_ = np.maximum(mad, np.maximum(.1 * x.std(axis=0), 1e-3))
        return self

    def score(self, x):
        z = np.minimum(np.abs(x - self.med_) / self.scale_, 10.)
        return np.sort(z, axis=1)[:, -5:].sum(axis=1)


class TailExceedance:
    """Dynamic-threshold analogue: columns beyond the company's own 1st/99th percentile, weighted by the excess."""
    def fit(self, x):
        self.lo_, self.hi_ = np.percentile(x, 1, axis=0), np.percentile(x, 99, axis=0)
        self.scale_ = np.maximum(x.std(axis=0), 1e-3)
        return self

    def score(self, x):
        above = np.maximum(x - self.hi_, 0) / self.scale_
        below = np.maximum(self.lo_ - x, 0) / self.scale_
        return np.log1p(above + below).sum(axis=1)


class ShrunkMahalanobis:
    """Squared Mahalanobis distance with a shrinkage covariance (joint unusualness of many features)."""
    def fit(self, x):
        self.mean_, self.std_ = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
        self.cov_ = OAS().fit((x - self.mean_) / self.std_)
        return self

    def score(self, x):
        return self.cov_.mahalanobis((x - self.mean_) / self.std_)


class MaskedField:
    """Self-supervised: predict the most variable columns from the rest; surprise is the standardised residual."""
    def __init__(self, targets=12):
        self.targets = targets

    def fit(self, x):
        self.mean_, self.std_ = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
        z = (x - self.mean_) / self.std_
        spread = np.asarray([len(np.unique(x[:, j])) for j in range(x.shape[1])])
        eligible = np.flatnonzero(spread > 5)
        self.cols_ = eligible[np.argsort(-x.std(axis=0)[eligible])][:self.targets]
        self.models_, self.scales_ = [], []
        for j in self.cols_:
            rest = np.delete(z, j, axis=1)
            model = Ridge(alpha=5.).fit(rest, z[:, j])
            residual = z[:, j] - model.predict(rest)
            self.models_.append(model)
            self.scales_.append(max(np.median(np.abs(residual)) * 1.4826, .05))
        return self

    def score(self, x):
        z = (x - self.mean_) / self.std_
        surprises = []
        for j, model, scale in zip(self.cols_, self.models_, self.scales_):
            surprises.append(np.minimum(np.abs(z[:, j] - model.predict(np.delete(z, j, axis=1))) / scale, 12.))
        if not surprises:
            return np.zeros(len(x))
        return np.sort(np.stack(surprises, axis=1), axis=1)[:, -3:].mean(axis=1)


class _Wrapped:
    def __init__(self, algorithm):
        self.algorithm = algorithm

    def fit(self, x):
        from .ml_estimators import CompanyEstimator
        self.estimator_ = CompanyEstimator(self.algorithm).fit(x)
        return self

    def score(self, x):
        return self.estimator_.score(x)


METHODS = {
    'ecod': lambda: _Wrapped('ecod'), 'isolation_forest': lambda: _Wrapped('isolation_forest'),
    'lof': lambda: _Wrapped('lof'), 'autoencoder': lambda: _Wrapped('autoencoder'),
    'robust_z': RobustZ, 'tail_exceedance': TailExceedance,
    'shrunk_mahalanobis': ShrunkMahalanobis, 'masked_field': MaskedField,
}
LABELS = {'ecod': 'ECOD', 'isolation_forest': 'Isolation Forest', 'lof': 'LOF', 'autoencoder': 'Autoencoder',
          'robust_z': 'z bền vững (median/MAD)', 'tail_exceedance': 'Vượt ngưỡng phân vị 1/99',
          'shrunk_mahalanobis': 'Mahalanobis co rút', 'masked_field': 'Đoán trường bị che (tự giám sát)'}


# ------------------------------------------------------------------ injection families (feature-space clones of real rows)
def _col(names, name):
    return names.index(name) if name in names else None


class Family:
    def __init__(self, key, label, required, eligible_flag, apply):
        self.key, self.label, self.required, self.eligible_flag, self.apply = key, label, required, eligible_flag, apply

    def usable(self, names):
        return all(r in names for r in self.required)

    def mask(self, x, names):
        if self.eligible_flag is None:
            return np.ones(len(x), dtype=bool)
        columns = [_col(names, f) for f in self.eligible_flag if f in names]
        return np.any(x[:, columns] > .5, axis=1) if columns else np.zeros(len(x), dtype=bool)


def _set(x, names, name, value):
    j = _col(names, name)
    if j is not None:
        x[:, j] = value


def _add(x, names, name, value):
    j = _col(names, name)
    if j is not None:
        x[:, j] = x[:, j] + value


LEVELS = (0, 1, 2)            # 0 obvious, 1 moderate, 2 subtle (concealed)


def _amount_spike(x, n, ref, rng, level):
    d = (1.6, .9, .45)[level] * rng.uniform(.85, 1.15, len(x))
    _add(x, n, 'log_amount', d)
    j = _col(n, 'amount_limit_ratio')
    if j is not None:
        x[:, j] = np.minimum(x[:, j] * np.exp(d), 1.5)
    _add(x, n, 'log_amount_vs_history', d)
    _add(x, n, 'amount_history_z', 3 * d)


def _split_below_limit(x, n, ref, rng, level):
    lo, hi = ((.97, .995), (.93, .97), (.9, .94))[level]
    _set(x, n, 'amount_limit_ratio', rng.uniform(lo, hi, len(x)))
    _set(x, n, 'near_limit', 1.)
    k = (4, 3, 2)[level]
    for name in ('recipient_count_3d', 'creator_near_limit_30d', 'creator_count_7d'):
        _add(x, n, name, k)
    _add(x, n, 'recipient_sum_limit_3d', k * .95)


def _duplicate_payment(x, n, ref, rng, level):
    _add(x, n, 'prior_same_amount_30d', (3, 2, 1)[level])
    _set(x, n, 'cumulative_invoice_payment_ratio', (1.9, 1.4, 1.15)[level])
    _add(x, n, 'prior_invoice_payment_count', (2, 1, 1)[level])


def _self_approval(x, n, ref, rng, level):
    _set(x, n, 'self_approved', 1.)
    if level < 2:
        _set(x, n, 'self_approval_permitted', 0.)
    j = _col(n, 'approval_log_hours')
    if j is not None:
        x[:, j] = np.minimum(x[:, j], np.percentile(ref[:, j], (3, 10, 25)[level]))


def _off_hours(x, n, ref, rng, level):
    hour = rng.choice([22, 23, 1, 2, 3], len(x)) if level < 2 else rng.choice([6, 20, 21], len(x))
    _set(x, n, 'created_off_hours', 1.)
    _set(x, n, 'hour_sin', np.sin(2 * np.pi * hour / 24))
    _set(x, n, 'hour_cos', np.cos(2 * np.pi * hour / 24))
    if level != 1:
        _set(x, n, 'created_weekend', 1.)
        _set(x, n, 'weekday_sin', np.sin(2 * np.pi * 6 / 7))
        _set(x, n, 'weekday_cos', np.cos(2 * np.pi * 6 / 7))


def _related_vendor(x, n, ref, rng, level):
    _set(x, n, ('employee_bank_overlap', 'employee_phone_overlap_current', 'employee_address_overlap_current')[level], 1.)
    _set(x, n, 'related_party_disclosed', 0.)
    _add(x, n, 'graph_employee_count_current', 1.)
    _add(x, n, 'linked_vendor_count_current', 1.)


def _new_vendor_large(x, n, ref, rng, level):
    for name in ('vendor_age_log_days', 'vendor_tenure_log_days'):
        j = _col(n, name)
        if j is not None:
            x[:, j] = np.minimum(x[:, j], np.percentile(ref[:, j], (0, 2, 8)[level]))
    _set(x, n, 'prior_type_history_log_count', 0.)
    _add(x, n, 'log_amount', (1.0, .6, .3)[level])


def _weak_evidence(x, n, ref, rng, level):
    _set(x, n, 'support_doc_count', (0., 1., 1.)[level])
    _set(x, n, 'goods_receipt_verified', 0.)
    _set(x, n, 'support_docs_known', 1.)
    if level == 0:
        _set(x, n, 'invoice_known', 0.)


def _payroll_without_attendance(x, n, ref, rng, level):
    _set(x, n, 'attendance_known', 1.)
    j = _col(n, 'attendance_days')
    if j is not None:
        x[:, j] = (0., np.percentile(ref[:, j], 10), np.percentile(ref[:, j], 25))[level]
    _set(x, n, 'alternative_work_evidence', 0.)
    if level == 0:
        _set(x, n, 'employee_contract_on_file', 0.)


def _advance_overdue(x, n, ref, rng, level):
    _add(x, n, 'advance_overdue_days', (120, 60, 25)[level])
    _set(x, n, 'advance_open_fraction', 1.)
    if level < 2:
        _set(x, n, 'advance_writeoff_evidence_missing', 1.)


FAMILIES = (
    Family('amount_spike', 'Số tiền vọt lên so với lịch sử', ('log_amount',), None, _amount_spike),
    Family('split_below_limit', 'Chia nhỏ sát hạn mức duyệt', ('amount_limit_ratio', 'near_limit'), None, _split_below_limit),
    Family('duplicate_payment', 'Thanh toán trùng hóa đơn', ('prior_same_amount_30d',), ('has_vendor',), _duplicate_payment),
    Family('self_approval', 'Tự lập tự duyệt, duyệt quá nhanh', ('self_approved',), None, _self_approval),
    Family('off_hours', 'Lập ngoài giờ hoặc cuối tuần', ('created_off_hours',), None, _off_hours),
    Family('related_vendor', 'Nhà cung cấp liên quan nhân viên', ('employee_bank_overlap',), ('has_vendor',), _related_vendor),
    Family('new_vendor_large', 'Nhà cung cấp mới, khoản lớn', ('vendor_age_log_days',), ('has_vendor',), _new_vendor_large),
    Family('weak_evidence', 'Thiếu chứng từ', ('support_doc_count',), ('has_vendor',), _weak_evidence),
    Family('payroll_without_attendance', 'Lương không chấm công', ('attendance_days',), ('type_payroll',), _payroll_without_attendance),
    Family('advance_overdue', 'Tạm ứng quá hạn', ('advance_overdue_days',),
           ('type_advance_issue', 'type_advance_settlement', 'type_advance_writeoff', 'type_advance_review'), _advance_overdue),
)


def make_injections(x_val, x_ref, names, rng):
    """Clones of real validation rows bent by each usable family and level. Returns (matrix, family index, level)."""
    blocks, fam, lev, skipped, used = [], [], [], [], []
    for index, family in enumerate(FAMILIES):
        if not family.usable(names):
            skipped.append((family.key, 'thiếu cột đặc trưng'))
            continue
        eligible = np.flatnonzero(family.mask(x_val, names))
        if len(eligible) < 5:
            skipped.append((family.key, f'chỉ {len(eligible)} dòng phù hợp để tiêm'))
            continue
        used.append(index)
        for level in LEVELS:
            clone = x_val[rng.choice(eligible, CLONES, replace=True)].copy()
            family.apply(clone, names, x_ref, rng, level)
            blocks.append(clone)
            fam.extend([index] * CLONES)
            lev.extend([level] * CLONES)
    if not blocks:
        raise ValueError('Không tiêm được họ gian lận nào: ma trận thiếu các cột đặc trưng cần thiết.')
    return np.vstack(blocks), np.asarray(fam), np.asarray(lev), skipped, used


# ------------------------------------------------------------------ surprise scale and combination
class Reference:
    """Tail-probability scale of one method from out-of-sample real validation scores."""
    def __init__(self, scores):
        self.sorted_ = np.sort(np.asarray(scores, dtype=float))
        self.n_ = len(self.sorted_)
        median = np.median(self.sorted_)
        self.top_ = self.sorted_[-1]
        self.span_ = max(np.percentile(self.sorted_, 99) - median, 1e-9)

    def surprise(self, scores):
        s = np.asarray(scores, dtype=float)
        tail = 1 - np.searchsorted(self.sorted_, s, side='right') / self.n_
        base = -np.log(np.maximum(tail, 1 / (self.n_ + 1)))
        return base + np.log1p(np.maximum(s - self.top_, 0) / self.span_)


def combine(surprises, members, kind):
    stack = np.stack([surprises[m] for m in members], axis=0)
    return stack.max(axis=0) if kind == 'max' else stack.mean(axis=0)


def family_recall(real, injected, fam, used, rate):
    threshold = np.quantile(real, 1 - rate, method='higher')
    return np.asarray([float((injected[fam == f] > threshold).mean()) for f in used])


def candidates(single_j, names):
    ranked = sorted(names, key=lambda m: -single_j[m])
    top = tuple(ranked[:3])
    out = {m: ((m,), 'mean') for m in names}
    out.update({'mean_all': (tuple(names), 'mean'), 'max_all': (tuple(names), 'max'),
                'mean_top3': (top, 'mean'), 'max_top3': (top, 'max')})
    return out


def objective(recalls, subset):
    """Mean recall over the chosen families plus the mean of the two weakest: rewards breadth, punishes blind spots."""
    values = recalls[subset]
    return float(.5 * values.mean() + .5 * np.sort(values)[:2].mean())


class BagOfMethods:
    """Fit, select by injection, expose `score(x)` on the tail-probability scale."""
    def __init__(self, alert_rate=ALERT_RATE):
        self.alert_rate = alert_rate

    def fit(self, x, columns):
        x = matrix(x)
        names = list(columns or [])
        if len(names) != x.shape[1]:
            raise ValueError('Túi phương pháp cần tên cột khớp ma trận để biết tiêm vào đặc trưng nào.')
        if len(x) < MIN_ROWS:
            raise ValueError(f'Túi phương pháp cần ít nhất {MIN_ROWS} dòng train (có {len(x)}); chọn kỳ train dài hơn.')
        rng = np.random.default_rng(SEED)
        cut = int(len(x) * FIT_SHARE)
        x_fit, x_val = x[:cut], x[cut:]
        injected, fam, lev, skipped, used = make_injections(x_val, x_fit, names, rng)
        self.models_, raw_real, raw_inj, failed = {}, {}, {}, []
        for key, factory in METHODS.items():
            try:
                model = factory().fit(x_fit)
                r, i = np.asarray(model.score(x_val), float), np.asarray(model.score(injected), float)
                if not (np.isfinite(r).all() and np.isfinite(i).all()):
                    raise ValueError('điểm không hữu hạn')
            except Exception as error:      # a method that cannot fit on this data is dropped, not fatal
                failed.append((key, str(error)[:120]))
                continue
            self.models_[key], raw_real[key], raw_inj[key] = model, r, i
        if len(self.models_) < 3:
            raise ValueError('Quá ít phương pháp huấn luyện được trên dữ liệu này để so sánh.')
        self.refs_ = {m: Reference(raw_real[m]) for m in self.models_}
        s_real = {m: self.refs_[m].surprise(raw_real[m]) for m in self.models_}
        s_inj = {m: self.refs_[m].surprise(raw_inj[m]) for m in self.models_}
        names_ok = list(self.models_)
        all_fams = np.arange(len(used))

        def evaluate(subset):
            """Per-candidate per-family recall on `subset` rows of `used` (single-method J decides the top-3 members)."""
            single = {}
            for m in names_ok:
                rec = family_recall(s_real[m], s_inj[m], fam, used, self.alert_rate)
                single[m] = objective(rec, subset)
            table = {}
            for key, (members, kind) in candidates(single, names_ok).items():
                table[key] = (members, kind, family_recall(combine(s_real, members, kind), combine(s_inj, members, kind),
                                                            fam, used, self.alert_rate))
            return table

        table = evaluate(all_fams)
        scores = {k: objective(v[2], all_fams) for k, v in table.items()}
        best = max(scores, key=lambda k: (scores[k], k == BASELINE))
        chosen = best if scores[best] - scores[BASELINE] >= MARGIN else BASELINE
        # nested leave-one-family-out: pick on the other families, test on the one held out (members re-derived per fold)
        held = []
        for f in range(len(used)):
            rest = np.asarray([g for g in all_fams if g != f])
            fold = evaluate(rest)
            fold_scores = {k: objective(v[2], rest) for k, v in fold.items()}
            fold_best = max(fold_scores, key=lambda k: (fold_scores[k], k == BASELINE))
            pick = fold_best if fold_scores[fold_best] - fold_scores[BASELINE] >= MARGIN else BASELINE
            held.append(float(fold[pick][2][f]))
        self.members_, self.kind_ = table[chosen][0], table[chosen][1]
        self.chosen_ = chosen
        per_family = {FAMILIES[u].key: float(r) for u, r in zip(used, table[chosen][2])}
        by_level = {int(l): float(np.mean((combine(s_inj, self.members_, self.kind_)[lev == l]
                                           > np.quantile(combine(s_real, self.members_, self.kind_), 1 - self.alert_rate,
                                                         method='higher')))) for l in LEVELS}
        rows = len(x)
        self.diagnostics_ = dict(
            kind='bag_of_methods_injection', alert_rate=self.alert_rate, fit_rows=int(cut), validation_rows=int(len(x) - cut),
            reliability='thấp' if rows < 300 else 'trung bình' if rows < 1500 else 'khá',
            chosen=chosen, chosen_members=list(self.members_), chosen_kind=self.kind_,
            chosen_objective=scores[chosen], baseline=BASELINE, baseline_objective=scores[BASELINE],
            candidate_objectives={k: round(v, 4) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])},
            recall_by_family=per_family, recall_by_level=by_level,
            recall_baseline_mean=float(table[BASELINE][2].mean()), recall_chosen_mean=float(table[chosen][2].mean()),
            held_out_family_recall_estimate=float(np.mean(held)), held_out_family_recall_min=float(np.min(held)),
            families_used=[FAMILIES[u].key for u in used], families_skipped=skipped, methods_failed=failed,
            family_labels={FAMILIES[u].key: FAMILIES[u].label for u in used},
            methods=[dict(id=m, label=LABELS[m]) for m in names_ok],
            limits=['Mẫu gian lận là mẫu đã biết, viết trong không gian đặc trưng, không phải gian lận thật chưa phát hiện.',
                    'Sổ thật có thể đã chứa gian lận chưa bị phát hiện và được coi là bình thường.',
                    'Lựa chọn thiên về loại mẫu được tiêm; ước lượng họ chưa thấy là số lấy từ giữ-lại-một-họ.',
                    'Điểm là mức bất thường theo xác suất đuôi, không phải xác suất gian lận.'])
        return self

    def score(self, x):
        x = matrix(x)
        surprises = {m: self.refs_[m].surprise(self.models_[m].score(x)) for m in self.members_}
        out = combine(surprises, self.members_, self.kind_)
        if not np.isfinite(out).all():
            raise ValueError('Túi phương pháp trả về điểm không hợp lệ.')
        return out
