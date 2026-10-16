# Catalog versions and legacy head filenames

`legal_registry_v1.json`, `ruleset_v1.json`, `taxonomy_v1.json` are **compatibility head files** read by existing loaders. Their embedded `version` is the identity; the suffix in the filename is not the current data version. Updating these data heads avoids changing the replay-pinned calculation implementation.

- Immutable v1 bytes: `versions/20261014-v1/`, with SHA-256 in `byte_pins.json`. Includes the original model manifest; original JDM files remain unchanged in `rules/models/`.
- Immutable v2 snapshots: `legal_registry_20261016_v2.json`, `ruleset_20261016_v2.json`, `taxonomy_20261016_v2.json`, and `rules/models/manifest_20261016_v2.json`.
- Existing planning/execution/evaluation rows contain complete input/package snapshots. Replay uses those snapshots, not the current data heads. Never rewrite stored artifacts to point at a newer catalog.

V2 is DRAFT. The support end `2026-10-17` is **exclusive and is a technical review horizon**, not a statutory expiry date. NĐ 174's document expiry is separately recorded as `2027-01-01` exclusive. Source review does not publish tax rules or approve classification mappings.

MVP scope: backend-confirmed `VAT`; invoice-content model checks seller tax-ID presence only, payment supports STANDARD cases only, and VAT reduction check applies only to DEDUCTION/TAXABLE_RATE/independently approved REDUCTION_CANDIDATE. Other cases must not be described as legally compliant merely because outside these checks. Real models remain DRAFT; actual classification mapping remains unapproved.
