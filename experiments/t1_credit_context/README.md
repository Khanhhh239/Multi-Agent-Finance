# Credit context: research and real input boundaries

The original `features.py`, `observations.py`, and
`analysis.audit_t1_credit_context` reproduce a **hypothetical measurement study**.
Its survey does not exist as an actual connected source. Its first-invoice KYC
date is a simulation assumption. Do not use that output as a deployable input.

For records supplied by a B2B seller, use `practical.practical_context_features`.
It returns only 14 industry indicators, including an unknown category per side.
It does not accept simulated macro releases or infer industry availability from
invoice dates. This adapter has not been connected to production or a model.

- Forecast keys: `firm_id`, `customer_id`, `cutoff`.
- Buyer observations: `firm_id`, `customer_id`, `industry`, `known_at`,
  `source_kind`, `source_ref`.
- Seller observations: `firm_id`, `industry`, `known_at`, `source_kind`,
  `source_ref`.
- `known_at`: when that seller actually had this version of the information.
  Records imported today do not automatically become available in past snapshots.
- Buyer sources: customer master, customer-supplied classification, or a verified
  registry extract. Seller sources: own company profile or a verified extract.
  No registry lookup or external access is supplied by this module.
- The caller must verify the mapping to the six research industry categories.
  Ambiguous, absent or unmapped classifications remain unknown.
- Classifications are versioned by knowledge date and isolated by seller.
  The same buyer tax ID at another seller does not provide access to that seller's
  records. Updates learned later do not change old features.

The complete source access inventory is produced by:

```powershell
.\.venv\Scripts\python.exe -B -m analysis.audit_t1_feature_access --output outputs/analysis/t1_feature_access_rerun
```

See the [B2B access audit](../../docs/04_AI_Methods/T1_V6_B2B_FEATURE_ACCESS_2026-11-05.md).
