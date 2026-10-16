"""Check numeric fidelity against the evidence attached to one explanation.

This verifies numbers, not the truth of unrestricted natural-language claims.
Use with controlled templates and evidence scoped to that template.
"""
from __future__ import annotations

import math
import re

NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:\.\d+)?%?")


def check(reason_text, evidence_row):
    values = []
    for value in dict(evidence_row).values():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    unsupported = []
    for token in NUMBER.findall(reason_text):
        percent = token.endswith("%")
        literal = token.rstrip("%")
        places = len(literal.partition(".")[2])
        observed = float(literal)
        if not any(math.isclose(observed, round(v * (100 if percent else 1), places), abs_tol=1e-9, rel_tol=0)
                   for v in values):
            unsupported.append(token)
    return {"ok": not unsupported, "unsupported_numbers": unsupported}
