"""Document journal: declared-text baseline and explicit policy/facts engine.

Uses supplied text, not PDFs/OCR execution. Unsupported documents stay explicit;
expected entries and balance sheets are opened by the evaluator only.
"""

from collections import Counter
from decimal import Decimal
from pathlib import Path
import re

from .adapters import minor, verified_source
from .data import fingerprint, iso_date, prepare_experiment_output, read_jsonl, write_json
from . import journal_policy
from .journal_policy import observed_identity


def declared_amount(content, label):
    values = re.findall(r"(?m)^" + re.escape(label) + r":\s*\$?([0-9][0-9,]*\.[0-9]{2})\s*$", content)
    return minor(values[0].replace(",", ""), "USD") if len(values) == 1 else None


def activity_arithmetic(doc):
    """Check declared movements only, without inferring a tax rate or schedule."""
    if doc.get("metadata", {}).get("currency_code") != "USD":
        return None
    content = doc["ocr_text"]
    if re.search(r"(?i)\b(exchange rate|foreign currency|withholding)\b", content):
        return None
    if doc["doc_type"] == "loan_statement":
        values = [declared_amount(content, name) for name in
                  ("Opening Principal", "Draw Amount", "Principal Paid", "Interest Paid", "Ending Principal")]
        if any(v is None for v in values):
            return None
        opening, draw, principal, interest, ending = values
        return "loan_principal_mismatch" if opening + draw - principal != ending else False
    if doc["doc_type"] == "payroll_summary":
        values = [declared_amount(content, name) for name in ("Gross Pay", "Employer Tax", "Cash Outflow")]
        if any(v is None for v in values):
            return None
        gross, tax, cash = values
        return "payroll_cash_mismatch" if gross + tax != cash else False
    return None


def detect_inconsistency(documents, policy=None, cutoff=None):
    """Observed USD declared arithmetic/identity checks, with explicit abstention.

    Unknown document policies are not evidence that a whole packet is consistent.
    No expected fields, validation metadata or benchmark scenario labels are read.
    """
    findings, ids, numbered, unsupported, supported = [], {}, {}, 0, 0
    dependency_totals, carrying_totals, credit_taxes, credit_net = Counter(), Counter(), Counter(), Counter()
    for doc in sorted(documents, key=lambda d: (d["doc_id"], observed_identity(d))):
        identifier, content = doc["doc_id"], doc["ocr_text"]
        identity = observed_identity(doc)
        if identifier in ids and ids[identifier] != identity:
            findings.append({"doc_id": identifier, "code": "conflicting_document_id"})
        elif identifier in ids:
            continue
        ids[identifier] = identity
        if doc["role"] not in ("posting_doc", "support_doc"):
            continue
        if "accounting_facts" in doc:
            if policy is None or cutoff is None:
                unsupported += 1
                continue
            try:
                journal_policy.validate_policy(policy, cutoff)
            except (KeyError, TypeError, ValueError):
                unsupported += 1
                continue
            try:
                journal_policy.postings(doc, policy, documents, cutoff)
                facts = doc["accounting_facts"]
                if "reference_doc_id" in facts:
                    family = "credit" if doc["doc_type"].endswith("credit_note") else "settlement"
                    group = (facts["reference_doc_id"], family)
                    dependency_totals[group] += facts.get("amount_minor", facts.get("total_minor", 0))
                    source = next(d for d in documents if d["doc_id"] == facts["reference_doc_id"])
                    if dependency_totals[group] > source["accounting_facts"]["total_minor"]:
                        findings.append({"doc_id": identifier, "related_doc_id": source["doc_id"], "code": "dependency_total_overflow"})
                    if family == "credit":
                        credit_taxes[group] += facts["tax_minor"]
                        credit_net[group] += facts["subtotal_minor"] - facts.get("discount_minor", 0)
                        original = source["accounting_facts"]
                        if (credit_taxes[group] > original["tax_minor"]
                                or credit_net[group] > original["subtotal_minor"] - original.get("discount_minor", 0)):
                            findings.append({"doc_id": identifier, "related_doc_id": source["doc_id"], "code": "dependency_total_overflow"})
                    if family == "settlement":
                        carrying_totals[group] += facts["carrying_functional_minor"]
                        source_amount = source["accounting_facts"]["total_minor"]
                        if carrying_totals[group] > journal_policy.carrying_value(source, source_amount, policy["functional_currency"]):
                            findings.append({"doc_id": identifier, "related_doc_id": source["doc_id"], "code": "dependency_total_overflow"})
                supported += 1
            except journal_policy.UnsupportedPolicy:
                unsupported += 1
            except (KeyError, TypeError, ValueError) as exc:
                findings.append({"doc_id": identifier, "code": "structured_policy_violation", "reason": str(exc)})
            continue
        if doc["doc_type"] in ("loan_statement", "payroll_summary"):
            check = activity_arithmetic(doc)
            if check is None:
                unsupported += 1
            else:
                supported += 1
                if check:
                    findings.append({"doc_id": identifier, "code": check})
            continue
        if doc["doc_type"] == "bank_statement" and doc.get("metadata", {}).get("currency_code") == "USD":
            opening = re.findall(r"(?m)^Opening Balance:\s*\$(-?[0-9,]+\.[0-9]{2})\s*$", content)
            closing = re.findall(r"(?m)^Closing Balance:\s*\$(-?[0-9,]+\.[0-9]{2})\s*$", content)
            moves = re.findall(r"\| Amount \$(-?[0-9,]+\.[0-9]{2})\s*\|", content)
            if len(opening) == len(closing) == 1 and moves:
                supported += 1
                closing_value = minor(opening[0].replace(",", ""), "USD") + sum(minor(v.replace(",", ""), "USD") for v in moves)
                if closing_value != minor(closing[0].replace(",", ""), "USD"):
                    findings.append({"doc_id": identifier, "code": "bank_closing_mismatch"})
                rows = re.findall(r"\| Amount \$(-?[0-9,]+\.[0-9]{2})\s*\| Running Balance \$(-?[0-9,]+\.[0-9]{2})", content)
                if len(rows) == len(moves):
                    running = minor(opening[0].replace(",", ""), "USD")
                    for amount, balance in rows:
                        running += minor(amount.replace(",", ""), "USD")
                        if running != minor(balance.replace(",", ""), "USD"):
                            findings.append({"doc_id": identifier, "code": "bank_running_balance_mismatch"})
                            break
            else:
                unsupported += 1
            continue
        if (doc["doc_type"] not in ("customer_invoice", "vendor_invoice", "expense_receipt")
                or doc.get("metadata", {}).get("currency_code") != "USD"
                or re.search(r"(?i)\b(discount|exchange rate|foreign currency)\b", content)):
            unsupported += 1
            continue
        totals = re.findall(r"(?m)^Total:\s*\$([0-9,]+\.[0-9]{2})\s*$", content)
        lines = re.findall(r"(?m)^\s*-\s+.+\| Amount \$([0-9,]+\.[0-9]{2})\s*$", content)
        if len(totals) != 1 or not lines:
            unsupported += 1
            continue
        total = minor(totals[0].replace(",", ""), "USD")
        supported += 1
        subtotal = re.findall(r"(?m)^Subtotal:\s*\$([0-9,]+\.[0-9]{2})\s*$", content)
        tax = re.findall(r"(?m)^Tax Amount:\s*\$([0-9,]+\.[0-9]{2})\s*$", content)
        line_target = total
        if subtotal or tax or re.search(r"(?i)\btax\b", content):
            if len(subtotal) != 1 or len(tax) != 1:
                unsupported += 1
                continue
            line_target = minor(subtotal[0].replace(",", ""), "USD")
            if line_target + minor(tax[0].replace(",", ""), "USD") != total:
                findings.append({"doc_id": identifier, "code": "subtotal_tax_total_mismatch"})
        if sum(minor(v.replace(",", ""), "USD") for v in lines) != line_target:
            findings.append({"doc_id": identifier, "code": "line_total_mismatch"})
        number = re.findall(r"(?m)^Invoice Number:\s*(\S+)\s*$", content)
        if len(number) == 1:
            metadata = doc.get("metadata", {})
            key = (doc["doc_type"], metadata.get("issuer_name"), metadata.get("counterparty_name"), number[0])
            prior = numbered.setdefault(key, [])
            for old_total, old_id in prior:
                if all(key[1:3]) and old_total != total:
                    findings.append({"doc_id": identifier, "related_doc_id": old_id, "code": "conflicting_invoice_total"})
            prior.append((total, identifier))
    return {"inconsistent": True if findings else None if unsupported or not supported else False,
            "findings": findings, "unsupported_posting_documents": unsupported,
            "scope": "Declared USD invoice/bank/loan/payroll arithmetic/identity and explicit structured accounting policy/dependencies; no tax-law or broad accounting consistency claim"}


def inconsistency_metrics(records, predictions):
    if len(records) != len(predictions) or any(r["record_id"] != p["record_id"] for r, p in zip(records, predictions)):
        raise ValueError("inconsistency predictions must cover records exactly in order")
    counts = Counter(tp=0, fp=0, tn=0, fn=0, unknown_positive=0, unknown_negative=0)
    for r, p in zip(records, predictions):
        expected = r.get("expected_inconsistency")
        if type(expected) is not bool:
            raise ValueError("inconsistency evaluation requires independent boolean labels")
        observed = p["inconsistency"]["inconsistent"]
        if observed is None:
            counts["unknown_positive" if expected else "unknown_negative"] += 1
        else:
            counts[("t" if observed == expected else "f") + ("p" if observed else "n")] += 1
    positives = counts["tp"] + counts["fn"] + counts["unknown_positive"]
    predicted_positive = counts["tp"] + counts["fp"]
    evaluated = sum(counts[k] for k in ("tp", "fp", "tn", "fn"))
    return {**counts, "precision": counts["tp"] / predicted_positive if predicted_positive else None,
            "recall_full_pool": counts["tp"] / positives if positives else None,
            "decision_coverage": evaluated / len(records) if records else None,
            "records": len(records)}


def document_entry(doc, industry, allowed_accounts):
    kind, content = doc["doc_type"], doc["ocr_text"]
    if kind not in ("customer_invoice", "vendor_invoice", "supplier_invoice", "utilities_statement", "expense_receipt"):
        return None, "unsupported_document_type"
    currency = doc.get("metadata", {}).get("currency_code")
    if currency != "USD" or re.search(r"(?i)\b(tax|exchange rate|foreign currency)\b", content):
        return None, "tax_or_fx_or_currency_unsupported"
    totals = re.findall(r"(?m)^Total:\s*\$([0-9,]+\.[0-9]{2})\s*$", content)
    if len(totals) != 1:
        return None, "unrecognized_total"
    amount = minor(totals[0].replace(",", ""), currency)
    if amount <= 0:
        return None, "nonpositive_total"
    if kind == "customer_invoice":
        if industry != "professional_services":
            return None, "revenue_policy_unsupported"
        debit, credit = "Accounts Receivable", "Service Revenue"
    elif kind in ("vendor_invoice", "supplier_invoice"):
        labels = re.findall(r"(?m)^Expense (?:Label|Category):\s*(.+)$", content)
        if len(labels) != 1 or labels[0].strip() not in allowed_accounts:
            return None, "unrecognized_expense_account"
        debit, credit = labels[0].strip(), "Accounts Payable"
    elif kind == "utilities_statement":
        if "Utilities Expense" not in allowed_accounts or "Accounts Payable" not in allowed_accounts:
            return None, "missing_utilities_accounts"
        debit, credit = "Utilities Expense", "Accounts Payable"
    else:
        expense = [a for a in allowed_accounts if a.endswith(" Expense") and a in content]
        if len(expense) != 1:
            return None, "ambiguous_expense_account"
        debit, credit = expense[0], "Cash"
    if debit == credit or debit not in allowed_accounts or credit not in allowed_accounts:
        return None, "missing_or_identical_posting_accounts"
    iso_date(doc["date"])
    return {"doc_refs": [doc["doc_id"]], "debit_account": debit, "credit_account": credit,
            "amount_minor": amount, "posting_date": doc["date"]}, None


def document_entries(doc, industry, allowed_accounts):
    if doc["doc_type"] not in ("loan_statement", "payroll_summary"):
        entry, reason = document_entry(doc, industry, allowed_accounts)
        return [entry] if entry else None, reason
    if activity_arithmetic(doc) is not False:
        return None, "unsupported_or_inconsistent_declared_activity"
    iso_date(doc["date"])
    specs = (("Draw Amount", "Cash", "Loans Payable"),
             ("Principal Paid", "Loans Payable", "Cash"),
             ("Interest Paid", "Interest Expense", "Cash")) if doc["doc_type"] == "loan_statement" else (
             ("Gross Pay", "Salaries Expense", "Cash"), ("Employer Tax", "Payroll Tax Expense", "Cash"))
    entries = []
    for label, debit, credit in specs:
        amount = declared_amount(doc["ocr_text"], label)
        if amount:
            if debit not in allowed_accounts or credit not in allowed_accounts:
                return None, "declared_activity_account_not_allowed"
            entries.append({"doc_refs": [doc["doc_id"]], "debit_account": debit, "credit_account": credit,
                            "amount_minor": amount, "posting_date": doc["date"]})
    return entries, None


def predict(record):
    entries, decisions, postings = [], [], []
    documents, cutoff = [], record.get("cutoff")
    for doc in record["documents"]:
        if cutoff is not None:
            iso_date(cutoff)
            if "available_on" not in doc:
                decisions.append({"doc_id": doc["doc_id"], "status": "unsupported", "reason": "missing_document_availability"})
                continue
            iso_date(doc["available_on"]); iso_date(doc["date"])
            if doc["available_on"] > cutoff or doc["date"] > cutoff:
                decisions.append({"doc_id": doc["doc_id"], "status": "not_visible"})
                continue
        documents.append(doc)
    policy = record.get("accounting_policy")
    documents.sort(key=lambda d: (d["date"] or "", d["doc_id"], observed_identity(d)))
    inconsistency = detect_inconsistency(documents, policy, cutoff)
    if inconsistency["inconsistent"] is False and any(d.get("reason") == "missing_document_availability" for d in decisions):
        inconsistency["inconsistent"] = None
    blocked = {f["doc_id"] for f in inconsistency["findings"]}
    blocked.update(f["related_doc_id"] for f in inconsistency["findings"]
                   if f["code"] == "conflicting_invoice_total")
    # Overflow invalidates the whole competing group, not just the last row.
    overflow_refs = {f["related_doc_id"] for f in inconsistency["findings"] if f["code"] == "dependency_total_overflow"}
    blocked.update(d["doc_id"] for d in documents if d.get("accounting_facts", {}).get("reference_doc_id") in overflow_refs)
    # A dependency on a rejected invoice cannot justify its settlement. Block
    # all dependants transitively, independent of input ordering.
    while True:
        dependants = {d["doc_id"] for d in documents
                      if d.get("accounting_facts", {}).get("reference_doc_id") in blocked}
        if dependants <= blocked:
            break
        blocked.update(dependants)
    seen = set()
    # Explicit projection: no expected_* or scenario metadata enters extraction.
    for doc in documents:
        if doc["doc_id"] in seen:
            decisions.append({"doc_id": doc["doc_id"], "status": "duplicate_ignored"})
            continue
        seen.add(doc["doc_id"])
        if doc["role"] != "posting_doc" or doc["doc_type"] == "opening_trial_balance":
            decisions.append({"doc_id": doc["doc_id"], "status": "context_only"})
            continue
        if doc["doc_id"] in blocked:
            decisions.append({"doc_id": doc["doc_id"], "status": "review", "reason": "inconsistent_document_or_dependency"})
            continue
        if "accounting_facts" in doc:
            try:
                if policy is None or cutoff is None:
                    raise ValueError("structured journal requires policy and cutoff")
                posting = journal_policy.postings(doc, policy, documents, cutoff)
                paired = journal_policy.pair_entries(posting)
                postings.append(posting)
                entries.extend(paired)
                decisions.append({"doc_id": doc["doc_id"], "status": "predicted", "reason": "explicit_accounting_policy"})
            except (KeyError, TypeError, ValueError) as exc:
                decisions.append({"doc_id": doc["doc_id"], "status": "unsupported", "reason": str(exc)})
            continue
        batch, reason = document_entries(doc, record["industry"], record["allowed_accounts"])
        decisions.append({"doc_id": doc["doc_id"], "status": "predicted" if batch is not None else "unsupported", "reason": reason})
        if batch:
            entries.extend(batch)
    result = {"record_id": record["record_id"], "entries": entries, "decisions": decisions,
              "postings": postings, "inconsistency": inconsistency}
    if "opening_balances" in record:
        try:
            result["trial_balance"] = journal_policy.replay_trial_balance(record["opening_balances"], postings, policy, cutoff)
            structured_ids = {p["doc_id"] for p in postings}
            result["trial_balance"]["prediction_complete"] = all(
                d["status"] in ("context_only", "duplicate_ignored", "not_visible")
                or d["status"] == "predicted" and d["doc_id"] in structured_ids for d in decisions)
        except (KeyError, TypeError, ValueError) as exc:
            result["trial_balance"] = {"status": "unsupported", "reason": str(exc)}
    return result


def replay_simple(opening, entries):
    """Balance-sheet replay for the explicitly supported chart of accounts."""
    classes = {"Cash": "assets", "Accounts Receivable": "assets", "Accounts Payable": "liabilities",
               "Owner's Equity": "equity", "Retained Earnings": "equity"}
    balance = {section: {k: minor(v, "USD") for k, v in opening.get(section, {}).items()}
               for section in ("assets", "liabilities", "equity")}
    if any(k not in classes for values in balance.values() for k in values):
        raise ValueError("opening account unsupported by simple replay")
    profit = 0
    for e in entries:
        amount = e["amount_minor"]
        if type(amount) is not int or amount <= 0 or e["debit_account"] == e["credit_account"]:
            raise ValueError("invalid double-entry posting")
        for account, sign in ((e["debit_account"], 1), (e["credit_account"], -1)):
            if account.endswith(" Expense") or account == "Service Revenue":
                profit -= sign * amount
            elif account in classes:
                section = classes[account]
                balance[section][account] = balance[section].get(account, 0) + sign * amount * (1 if section == "assets" else -1)
            else:
                raise ValueError(f"account unsupported by simple replay: {account}")
    balance["equity"]["Retained Earnings"] = balance["equity"].get("Retained Earnings", 0) + profit
    balance["balanced"] = sum(balance["assets"].values()) == sum(balance["liabilities"].values()) + sum(balance["equity"].values())
    return balance


def evaluate(records, predictions):
    if len(records) != len(predictions):
        raise ValueError("journal predictions must cover every record, including unsupported ones")
    def token(e):
        return (tuple(sorted(e["doc_refs"])), e["debit_account"], e["credit_account"], e["amount_minor"], e["posting_date"])

    reports = []
    for r, p in zip(records, predictions):
        if r["record_id"] != p["record_id"]:
            raise ValueError("record/prediction mismatch")
        expected = [{**e, "amount_minor": minor(e["amount"], r["metadata"]["functional_currency_code"])}
                    for e in r["expected_entries"]]
        actual = Counter(token(e) for e in expected)
        predicted = Counter(token(e) for e in p["entries"])
        correct = sum((actual & predicted).values())
        row = {"record_id": r["record_id"], "expected_entries": len(expected), "predicted_entries": len(p["entries"]),
               "correct_entries": correct, "exact_journal": actual == predicted,
               "supported_documents": sum(d["status"] == "predicted" for d in p["decisions"]),
               "unsupported_documents": sum(d["status"] in ("unsupported", "review") for d in p["decisions"]),
               "balance_sheet_exact": None}
        if row["unsupported_documents"] == 0:
            try:
                balance = replay_simple(r["opening_balance"], p["entries"])
                wanted = {section: {k: minor(v, "USD") for k, v in r["expected_balance_sheet"][section].items()}
                          for section in ("assets", "liabilities", "equity")}
                # Missing zero-balance accounts are equivalent.
                clean = lambda values: {k: v for k, v in values.items() if v != 0}
                row["balance_sheet_exact"] = all(clean(balance[s]) == clean(wanted[s]) for s in wanted)
                row["replayed_balance_sheet"] = balance
            except ValueError as exc:
                row["replay_unsupported"] = str(exc)
        reports.append(row)
    total_p, total_e = sum(r["predicted_entries"] for r in reports), sum(r["expected_entries"] for r in reports)
    correct = sum(r["correct_entries"] for r in reports)
    return {"records": reports, "summary": {"coverage_records": len(records), "predicted_entries": total_p,
            "expected_entries": total_e, "correct_entries": correct,
            "entry_precision": correct / total_p if total_p else None,
            "entry_recall_full_coverage_pool": correct / total_e if total_e else None,
            "records_with_full_journal_exact": sum(r["exact_journal"] for r in reports),
            "records_with_balance_sheet_evaluated": sum(r["balance_sheet_exact"] is not None for r in reports),
            "records_with_balance_sheet_exact": sum(r["balance_sheet_exact"] is True for r in reports)}}


def run(folder, output):
    provenance = verified_source(folder, ["data/coverage/records.jsonl"])
    records = read_jsonl(Path(folder) / "data/coverage/records.jsonl", parse_float=Decimal)
    output = prepare_experiment_output(output)
    predictions = [predict({k: r[k] for k in ("record_id", "industry", "documents", "allowed_accounts")}) for r in records]
    write_json(output / "predictions.json", predictions)
    report = {"task": "finbalance_structured_text_journal", "provenance": provenance,
              "metrics": evaluate(records, predictions), "prediction_hash": fingerprint(predictions),
              "limitations": ["Source text baseline remains narrow; explicit policy/facts journal engine evaluated separately on synthetic contracts",
                              "Coverage pool already inspected, not blind", "No PDF/OCR run, no invoice-bank oracle",
                              "Text detector covers observed USD arithmetic/identity/running balances/loan/payroll; unknown policies abstain"],
              "inconsistency_quality": inconsistency_metrics(records, predictions)}
    write_json(output / "report.json", report)
    return report
