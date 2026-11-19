# API-key-only migration evidence

Date: 2026-11-19

## Scope

- Agent 4 metric selection, direct web, Portal launcher, and health metadata.
- Agent 3 LLM, embedding, reranker, explanation transport, direct web, and Portal launcher.
- Setup scripts, policies, schemas, docs, UI copy, and evaluation helpers.

## Acceptance evidence

- Provider defaults are OpenAI-compatible API providers; no legacy local daemon, local embedding endpoint, or local reranker fallback remains.
- Agent 3 direct launcher and Portal launch specification require authenticated LLM and embedding keys.
- Agent 4 production demo factory and Portal launch specification require both Agent 4 keys.
- Repository search returned no legacy local-provider markers or old local-model setup switches.

## Checks run

- Agent 3 lawbase tests: `17 passed`.
- Agent 3 selected AI resilience tests: `2 passed`.
- Agent 4 remote metric-selection contracts: `23 passed`.
- Agent 4 retrieval/few-shot contracts: `47 passed`.
- Agent 4 E0 contracts: `18 passed`.
- Agent 4 recovery contracts: `24 passed`.
- Portal Agent 4 launch-spec test: `1 passed`.
- AST/JSON parse: `206 Python files parsed`.
- Mocked API transport smoke: authenticated OpenAI-compatible explanation response materialized into validated claims.

## Environment limitations

- The Agent 3 HTTP transport test that starts a local socket cannot run in this sandbox (`PermissionError: Operation not permitted`); it was not counted as passing.
- One broader Agent 3 integration setup failed before the changed transport ran because an existing extraction fixture returned `FAILED` instead of `SUCCEEDED`.
- No real provider request was made during verification, so quota and provider-side availability remain deployment checks.
