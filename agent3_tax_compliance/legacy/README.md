# Legacy prototype (archived, not part of the pipeline)

This folder holds the first prototype: a single-transaction rule engine with a keyword
extractor, a SQLite table and a "tax inspector" view that listed only verdict PASS rows.

Why it was archived:
- it fails open (an unknown or missing fact could still end in PASS);
- it reads hard-coded `d:/financial/...` paths, so its own tests cannot run on another machine;
- the current pipeline (`src/ingestion` to `src/review`, with `src/rules` and `src/legal_registry`)
  replaces every part of it with versioned, replayable, fail-closed stages.

Nothing under `src/` imports this folder (`tests/contracts/test_foundation.py` asserts that
`src.main` and `src.database` are never loaded by the application). The code is kept for
reference only and is not expected to run.
