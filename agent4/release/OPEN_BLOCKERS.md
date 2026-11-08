# Open blockers

1. Real database schema, tenant key, auth boundary, DB grants and RLS were not
   supplied. Real-data execution and G7 are BLOCKED.
2. No human finance/domain owner has approved R-01..R-20 or custom formulas.
3. Ten custom metrics remain unsupported even in synthetic mode; all 20 remain
   unqualified for real data.
4. No approved LLM/embedding provider or credentials; provider plan ablations,
   token/cost and outage recovery against a real provider are BLOCKED.
5. Seed eval is too small and not independently expert-reviewed/sealed.
6. No independent human reviewer/red-team/acceptance signature was supplied.
7. Production load profile, concurrency target, logging backend, rate limiter,
   data residency and retention policy are unresolved.

Minimum owner actions are documented in `docs/implementation/OPEN_DECISIONS.md`.
