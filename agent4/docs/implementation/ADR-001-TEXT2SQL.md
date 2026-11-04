# ADR-001 — Safe semantic plan and synthetic qualification tier

Status: accepted for synthetic demonstrator, pending production review.

The existing retrieval stack remains intact. A modular application layer is
added rather than replacing it. Untrusted text produces only a strict
`SemanticPlanDraft`; deterministic validation creates immutable
`ValidatedPlan`; only that type reaches `SQLCompiler`. Relations, columns,
dimensions, measures and predicate shapes are allowlisted in code. Prefixes,
dates and filters are bound values. A fresh read-only DuckDB connection executes
one SELECT/CTE and returns Decimal strings.

Custom metrics fail closed unless a dedicated synthetic handler and source are
present. Synthetic support and real-data support are separate matrix fields.
This preserves useful offline execution while preventing synthetic evidence
from being misrepresented as production DB/RLS/domain qualification.

Alternatives rejected: free-form LLM SQL; treating every custom ID as a generic
ledger formula; silently mapping absent tenant/auth fields; adding a vector DB
for 66 catalog records.
