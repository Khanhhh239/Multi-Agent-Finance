"""Research-backed capability cases with latent payment intent, then observation noise.

Equal scenario counts and noise levels are experimental controls, not SME rates.
Truth is produced from the business event ledger, never by any matching method.
Credit notes, fees and refunds remain typed events, not invented cash receipts.
"""

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import random

from .data import fingerprint

SCENARIO_SOURCES = {
    "single": ["ERP-PAYMENT"], "partial": ["ERP-PAYMENT"],
    "group": ["ERP-PAYMENT", "SSMP", "RMIT"],
    "overpayment": ["ERP-PAYMENT"], "fee_net": ["ERP-BANK", "ACCA"],
    "credit_note": ["ERP-PAYMENT"], "ambiguous": ["RMIT", "DITTO"],
    "unpaid": ["ERP-PAYMENT"], "bank_only": ["ERP-PAYMENT", "ERP-BANK"],
    "refund": ["ERP-BANK"], "late_arrival": ["ERP-BANK"],
    "future_revision": ["ERP-BANK"], "scope": ["ERP-PAYMENT", "ERP-BANK"]}


def generate(seed, blocks, profile_name, profile):
    if blocks < 1:
        raise ValueError("blocks must be positive")
    rng = random.Random(seed)
    invoices, bank, truth, events = [], [], [], []
    cutoff = "2025-06-30"
    base = date(2025, 1, 1)

    def identifier(prefix):
        return f"SYNTH-{prefix}-{rng.getrandbits(96):024x}"

    def invoice(customer, name, amount, start, scenario, tenant="SYNTH-A", currency="VND"):
        issued = base + timedelta(days=start)
        row = {"tenant_id": tenant, "invoice_id": identifier("I"), "version": 1,
               "customer_id": customer, "customer_name": name, "currency": currency,
               "amount_minor": amount, "issued_on": issued.isoformat(),
               "due_on": (issued + timedelta(days=30)).isoformat(),
               "effective_on": issued.isoformat(), "available_on": issued.isoformat()}
        invoices.append(row)
        events.append({"type": "invoice", "invoice_id": row["invoice_id"], "scenario": scenario})
        return row

    def receipt(targets, amounts, scenario, total=None, refs=True):
        inv = targets[0]
        booked = inv["due_on"]
        row = {"tenant_id": inv["tenant_id"], "transaction_id": identifier("B"), "version": 1,
               "customer_id": inv["customer_id"], "counterparty": inv["customer_name"],
               "currency": inv["currency"], "amount_minor": sum(amounts) if total is None else total,
               "booked_on": booked, "effective_on": booked, "available_on": booked,
               "reference": "TT " + " + ".join(i["invoice_id"] for i in targets) if refs else "Thanh toan"}
        bank.append(row)
        # These explicit instructions exist before text corruption and are not
        # inferred from reference/amount similarity or from a matcher output.
        events.append({"type": "payment_intent", "transaction_id": row["transaction_id"],
                       "invoice_ids": [i["invoice_id"] for i in targets], "amounts": amounts,
                       "scenario": scenario})
        for i, amount in zip(targets, amounts):
            if amount:
                truth.append({"tenant_id": i["tenant_id"], "transaction_id": row["transaction_id"],
                              "invoice_id": i["invoice_id"], "currency": i["currency"],
                              "amount_minor": amount, "payment_on": booked, "scenario": scenario})
        return row

    for _ in range(blocks):
        customer, name = identifier("C"), rng.choice(("Cong ty An Phat", "Cong ty Minh Tam", "Cong ty Binh Minh"))
        start = rng.randint(0, 70)
        amount = lambda: rng.randint(20, 500) * 100_000
        inv = invoice(customer, name, amount(), start, "single")
        receipt([inv], [inv["amount_minor"]], "single")
        inv = invoice(customer, name, amount(), start, "partial")
        first = inv["amount_minor"] // 3
        receipt([inv], [first], "partial")
        receipt([inv], [inv["amount_minor"] - first], "partial")
        pair = [invoice(customer, name, amount(), start, "group") for _ in range(2)]
        receipt(pair, [i["amount_minor"] for i in pair], "group")
        inv = invoice(customer, name, amount(), start, "overpayment")
        receipt([inv], [inv["amount_minor"]], "overpayment", total=inv["amount_minor"] + 100_000)
        inv = invoice(customer, name, amount(), start, "fee_net")
        receipt([inv], [inv["amount_minor"] - 200], "fee_net")
        events.append({"type": "fee_adjustment", "invoice_id": inv["invoice_id"], "amount_minor": 200,
                       "cash_in": False, "implemented_in_matcher": False})
        inv = invoice(customer, name, amount(), start, "credit_note")
        receipt([inv], [inv["amount_minor"] - 100_000], "credit_note")
        events.append({"type": "credit_note", "invoice_id": inv["invoice_id"], "amount_minor": 100_000,
                       "cash_in": False, "implemented_in_matcher": False})
        inv = invoice(customer, name, amount(), start, "ambiguous")
        invoice(customer, name, inv["amount_minor"], start, "ambiguous")
        receipt([inv], [inv["amount_minor"]], "ambiguous", refs=False)
        inv = invoice(customer, name, amount(), start, "unpaid")
        unknown = dict(inv, customer_id=identifier("C"), customer_name="Nguoi chuyen chua xac dinh")
        receipt([unknown], [0], "bank_only", total=inv["amount_minor"], refs=False)
        refund = receipt([inv], [0], "refund", total=-100_000, refs=False)
        events.append({"type": "refund", "transaction_id": refund["transaction_id"],
                       "implemented_in_matcher": False, "expected": "quarantine_positive_receipts_only"})
        late = invoice(customer, name, amount(), start, "late_arrival")
        late["available_on"] = "2025-07-10"
        receipt([late], [late["amount_minor"]], "late_arrival")
        invoices.append(dict(inv, version=2, amount_minor=inv["amount_minor"] + 500,
                             available_on="2025-07-15"))
        events.append({"type": "future_revision", "invoice_id": inv["invoice_id"], "scenario": "future_revision"})
    for tenant, currency in (("SYNTH-B", "VND"), ("SYNTH-A", "USD")):
        inv = invoice(identifier("C"), "Cong ty An Phat", amount(), 0, "scope", tenant, currency)
        receipt([inv], [inv["amount_minor"]], "scope")

    latent_hash = fingerprint({"events": events, "truth": truth})
    observed_i, observed_b = deepcopy(invoices), deepcopy(bank)
    changes = Counter()
    # Observation process depends on a separate RNG per transaction. The same
    # latent world is shared across all profiles for a paired comparison.
    for row in observed_b:
        noise = random.Random(f"invoice-research-v1:{seed}:{row['transaction_id']}")
        if noise.random() < profile["mask_reference"]:
            row["reference"] = "Thanh toan cong no"
            row["customer_id"] = ""
            changes["masked_reference_and_identity"] += 1
        if noise.random() < profile["typo_probability"]:
            row["counterparty"] = row["counterparty"][:-2] + "xy"
            changes["name_typo"] += 1
        delta = noise.randint(-profile["date_error_days"], profile["date_error_days"])
        booked = (date.fromisoformat(row["booked_on"]) + timedelta(days=delta)).isoformat()
        row["booked_on"] = row["effective_on"] = row["available_on"] = booked
        # This is a settlement-timing change, not a false measurement of a
        # historical payment date: the bank-booked date defines this contract's
        # cash date. Link/amount intent remains unchanged and independent.
        for label in truth:
            if label["transaction_id"] == row["transaction_id"]:
                label["payment_on"] = booked
        changes["date_errors"] += delta != 0
    if profile_name != "clean":
        observed_i.append(dict(observed_i[0]))
        observed_b.append(dict(observed_b[0]))
        changes["duplicate_deliveries"] += 2
    manifest = {"kind": "research_synthetic", "generator": "latent-intent-v1", "seed": seed,
                "blocks": blocks, "profile": profile_name, "noise": profile, "cutoff": cutoff,
                "truth_exhaustive": True, "truth_scope": "visible valid positive endpoints at cutoff",
                "latent_world_hash": latent_hash, "scenario_sources": SCENARIO_SOURCES,
                "scenario_counts": dict(Counter(r["scenario"] for r in truth)),
                "noise_counts": dict(changes),
                "unsupported_event_counts": dict(Counter(e["type"] for e in events if e.get("implemented_in_matcher") is False)),
                "limitations": ["Balanced capability cases, not measured SME prevalence",
                    "Truth independent of algorithms, not independently reviewed SME annotations",
                    "Fee/credit/refund accounting not implemented; positive cash edges scored separately"],
                "content_hashes": {"invoices": fingerprint(observed_i), "bank": fingerprint(observed_b),
                                   "truth": fingerprint(truth)}}
    return observed_i, observed_b, truth, manifest
