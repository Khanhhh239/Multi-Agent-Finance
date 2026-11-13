"""Conservative display policy; model attribution is not a business cause.

Evidence comes from exactly the histories available to each serving member at
invoice issuance. Thresholds below are product filters, not statistical proof.
"""

import hashlib
import json

import numpy as np

from .methods import available_settlements

PROTOCOL = "t1-business-evidence-v1"
MIN_EFFECT_PP = 1.0
MIN_HISTORY_COUNT = 10


class HistoryEvidence:
    def __init__(self, history):
        self.settled = available_settlements(history)

    @staticmethod
    def summary(records):
        delays = (records.settled - records.due_date).dt.days
        # Include record dates in the digest: equal counts alone are insufficient
        # to establish that ensemble members used the same historical evidence.
        sources = sorted(
            (str(r.invoice_id), str(r.due_date), str(r.settled), str(r.available))
            for r in records.itertuples()
        )
        return {
            "count": len(records),
            "late_count": int((delays > 0).sum()),
            "on_time_count": int((delays == 0).sum()),
            "early_count": int((delays < 0).sum()),
            "prepared_median_days": float(delays.clip(-60, 180).median())
            if len(records)
            else 0.0,
            "source_hash": hashlib.sha256(
                json.dumps(sources, separators=(",", ":")).encode()
            ).hexdigest(),
        }

    def for_invoice(self, invoice, prepared):
        prior = self.settled[self.settled.available <= invoice.issue_date]
        company = self.summary(prior)
        customer = self.summary(prior[prior.customer_id == invoice.customer_id])
        n = customer["count"]
        centre = company["prepared_median_days"]
        estimate = (n * customer["prepared_median_days"] + 5 * centre) / (n + 5)
        matches = np.allclose(
            prepared[2:5], [estimate, centre, np.log1p(n)], atol=1e-10, rtol=0
        )
        if not matches:
            return None
        common = {
            "protocol": PROTOCOL,
            "asof": str(invoice.issue_date.date()),
            "scope": "settlements_available_before_invoice_issue",
        }
        return {
            "customer_delay_days": dict(common, **customer),
            "company_delay_days": dict(common, **company),
        }


def review_factors(factors, invoice, cutoff, member_evidence, checked):
    """Keep context separate and abstain when business evidence is insufficient."""
    for factor in factors:
        key = factor["feature"]
        review = {
            "protocol": PROTOCOL,
            "feature": key,
            "value": factor["value"],
            "value_unit": factor["value_unit"],
            "status": "withheld",
            "reason": "insufficient_checks",
            "min_effect_pp": MIN_EFFECT_PP,
        }
        factor["business_review"] = review
        if key in ("term_days", "customer_history_count"):
            # Contract response needs a separate validation audit. A history
            # count measures data quantity and says nothing about payment quality.
            review.update(
                status="context_only",
                reason="contract_response_not_validated"
                if key == "term_days"
                else "history_quantity_not_payment_quality",
            )
            continue
        stable = factor["stability"]
        effect = factor["contribution_pp"]
        direction_consistent = (
            factor["direction"] == "increase"
            and min(effect, stable["min_contribution_pp"]) >= MIN_EFFECT_PP
            or factor["direction"] == "decrease"
            and max(effect, stable["max_contribution_pp"]) <= -MIN_EFFECT_PP
        )
        if (
            not checked
            or factor["value"] is None
            or stable["status"] != "stable"
            or stable["reasons"]
            or not direction_consistent
        ):
            continue
        if key in ("customer_delay_days", "company_delay_days"):
            records = [e.get(key) if e else None for e in member_evidence]
            if (
                not records
                or records[0] is None
                or any(e != records[0] for e in records)
            ):
                review["reason"] = "history_not_shared_or_verified"
                continue
            if records[0]["count"] < MIN_HISTORY_COUNT:
                review["reason"] = "insufficient_history"
                continue
            review["evidence"] = records[0]
        elif key == "age_days":
            if factor["value"] != (cutoff - invoice.issue_date).days:
                continue
            review["evidence"] = {
                "protocol": PROTOCOL,
                "issue_date": str(invoice.issue_date.date()),
                "due_date": str(invoice.due_date.date()),
                "cutoff": str(cutoff.date()),
                "overdue_days": max(0, (cutoff - invoice.due_date).days),
            }
        elif key != "amount":
            continue
        # Amount can have a material model effect without evidence for a
        # statement such as "the customer cannot afford a large invoice".
        review.update(status="eligible", reason="checked_model_effect")
