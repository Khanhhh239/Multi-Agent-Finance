"""Controlled synthetic cases. Assumptions are tests, not measured business rates."""

from collections import Counter
from datetime import date, timedelta
import random

__version__ = "0.1.0"  # Frozen historical generator contract
from t0.data import fingerprint


PROFILES = ("clean", "noisy", "stress")


def generate(seed=101, blocks=8, profile="noisy"):
    if profile not in PROFILES or blocks < 1:
        raise ValueError("invalid profile or blocks")
    rng = random.Random(seed)
    invoices, bank, truth = [], [], []
    base = date(2025, 1, 1)
    cutoff = "2025-06-30"

    def identifier(prefix):
        return f"SYNTH-{prefix}-{rng.getrandbits(64):016X}"

    def invoice(customer, name, amount, start, tenant="SYNTH-TENANT-A", currency="VND"):
        issued = (base + timedelta(days=start)).isoformat()
        row = {"tenant_id": tenant, "invoice_id": identifier("I"), "version": 1,
               "customer_id": customer, "customer_name": name, "currency": currency,
               "amount_minor": amount, "issued_on": issued,
               "due_on": (base + timedelta(days=start + 30)).isoformat(),
               "effective_on": issued, "available_on": issued}
        invoices.append(row)
        return row

    def receipt(inv, amount=None, ref=True, lag=0, name=None, known=True):
        booked = (date.fromisoformat(inv["due_on"]) + timedelta(days=lag)).isoformat()
        row = {"tenant_id": inv["tenant_id"], "transaction_id": identifier("B"), "version": 1,
               "customer_id": inv["customer_id"] if known else "", "currency": inv["currency"],
               "amount_minor": amount if amount is not None else inv["amount_minor"],
               "booked_on": booked, "effective_on": booked, "available_on": booked,
               "counterparty": name if name is not None else inv["customer_name"],
               "reference": "TT " + inv["invoice_id"] if ref else "Thanh toan cong no"}
        bank.append(row)
        return row

    def label(tx, inv, amount=None, scenario="single"):
        truth.append({"tenant_id": tx["tenant_id"], "transaction_id": tx["transaction_id"],
                      "invoice_id": inv["invoice_id"], "currency": inv["currency"],
                      "amount_minor": amount if amount is not None else tx["amount_minor"],
                      "payment_on": tx["booked_on"], "scenario": scenario})

    for _ in range(blocks):
        bank_start = len(bank)
        customer = identifier("C")
        name = "Cong ty " + rng.choice(("An Phat", "Minh Tam", "Binh Minh", "Thanh Cong"))
        start = rng.randint(0, 75)
        # Common amount distribution across scenarios; no scenario encoded in IDs.
        amount = lambda: rng.randint(10, 200) * 100_000
        for case in ("single", "missing_reference", "typo", "partial", "group", "ambiguous"):
            inv = invoice(customer, name, amount(), start)
            if case == "partial":
                first = inv["amount_minor"] // 2
                for part, lag in ((first, 0), (inv["amount_minor"] - first, 9)):
                    label(receipt(inv, part, lag=lag), inv, scenario=case)
            elif case == "group":
                other = invoice(customer, name, amount(), start)
                tx = receipt(inv, inv["amount_minor"] + other["amount_minor"])
                tx["reference"] += " + " + other["invoice_id"]
                label(tx, inv, inv["amount_minor"], case)
                label(tx, other, other["amount_minor"], case)
            elif case == "ambiguous":
                invoice(customer, name, inv["amount_minor"], start)
                tx = receipt(inv, ref=(profile == "clean"))
                label(tx, inv, scenario=case)
            else:
                ref = profile == "clean" or case == "single"
                tx = receipt(inv, ref=ref, known=case != "typo" or profile == "clean",
                             name=name if profile == "clean" or case != "typo" else name[:-3] + "XYZ",
                             lag=rng.randint(-2, 7))
                label(tx, inv, scenario=case)
        unpaid = invoice(customer, name, amount(), start)
        # Bank-only receipt: customer absent from ERP; exhaustive truth has no link.
        unknown = dict(unpaid, customer_id=identifier("C"), customer_name="Unknown payer")
        receipt(unknown, ref=False)

        if profile != "clean":
            # Late-arriving invoice: bank visible now, invoice becomes known later.
            late = invoice(customer, name, amount(), start)
            late["available_on"] = "2025-07-10"
            tx = receipt(late)
            # No truth link in this as-of universe; evaluator also filters endpoints.
            label(tx, late, scenario="late_arrival")
            # Revised amount must replace the prior version only after availability.
            revision = dict(unpaid, version=2, amount_minor=unpaid["amount_minor"] + 500,
                            effective_on=unpaid["issued_on"], available_on="2025-07-15")
            invoices.append(revision)
            invoices.append(dict(inv))  # identical re-delivery
        if profile == "stress":
            for tx in bank[bank_start:]:
                if rng.random() < 0.45:
                    tx["reference"] = "CK cong no"
                    tx["customer_id"] = ""
                    tx["counterparty"] = tx["counterparty"].replace("Cong ty ", "CT ")
                    tx["booked_on"] = (date.fromisoformat(tx["booked_on"])
                                       + timedelta(days=20)).isoformat()
                    tx["effective_on"] = tx["available_on"] = tx["booked_on"]
                    for row in truth:
                        if row["transaction_id"] == tx["transaction_id"]:
                            row["payment_on"] = tx["booked_on"]
            # Invalid receipt must be quarantined, never turned into cash-in.
            bank.append(dict(tx, transaction_id=identifier("B"), amount_minor=-100))
        if profile != "clean":
            bank.append(dict(tx))  # byte-identical delivery even after stress mutations
    # Additional scoped positives exercise separate tenant/currency totals.
    for tenant, currency in (("SYNTH-TENANT-B", "VND"), ("SYNTH-TENANT-A", "USD")):
        decoy = invoice(identifier("C"), "Cong ty An Phat", 100_000, 0, tenant, currency)
        label(receipt(decoy), decoy, scenario="scope")
    rng.shuffle(invoices)
    rng.shuffle(bank)
    manifest = {"kind": "synthetic", "generator_version": __version__, "seed": seed,
                "blocks": blocks, "profile": profile, "cutoff": cutoff,
                "truth_exhaustive": True, "truth_scope": "visible endpoints at cutoff",
                "scenario_counts": dict(Counter(r["scenario"] for r in truth)),
                "assumption": "Controlled cases, not representative SME frequencies",
                "content_hashes": {"invoices": fingerprint(invoices), "bank": fingerprint(bank),
                                   "truth": fingerprint(truth)}}
    return invoices, bank, truth, manifest

