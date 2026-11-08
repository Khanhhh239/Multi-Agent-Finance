# Security report — synthetic scope

Implemented controls:

- User/model text cannot supply executable SQL, identifiers or formulas.
- Strict plan schema and deterministic authorization/capability validation.
- Trusted relation/dimension/measure allowlists; all values use DuckDB binds.
- Static single-SELECT/CTE guard rejects semicolons, DML/DDL/COPY/ATTACH/PRAGMA.
- Fresh `read_only=True` DuckDB connection per request; bounded rows/top-k.
- API authentication fails closed when no token is configured; identity and
  views are server-fixed, not accepted from JSON.
- Public errors omit SQL, columns, stack traces, credentials and raw rows.
- Prompt/SQL injection and unauthorized-view paths have executable tests.

Critical limitation: the synthetic database has no tenant key, DB role grants
or RLS. Therefore production tenant security (G7) is BLOCKED, not passed. The
demo only proves isolation of the compiler boundary and read-only embedded
execution. Dependency/SCA audit is also pending in a network-enabled approved
environment.
