"""Agent 3 tax-risk assistant: fixed core over a per-enterprise adaptive pack (see DIGITAL_ACCOUNTING_PART11).

Pipeline: ingest (XML, bank statements, portal list) -> normalize -> data guards -> match invoices to payments
-> dated rules -> money at risk -> review queue -> report, questions, law-change impact.
Everything is deterministic; no language model is called in this package.
"""
