# Open decisions and blockers

| ID | Decision/evidence | State | Owner action |
|---|---|---|---|
| D-01 | Existing Python/FastAPI retained; modular `agent4.text2sql` added | ACCEPTED synthetic | Engineering review |
| D-02 | Actual local engine is DuckDB, not proposed PostgreSQL | ACCEPTED synthetic | Choose production engine |
| D-03 | Synthetic schema mapped; real schema absent | BLOCKER real data | Data owner supplies read-only metadata |
| D-04 | Synthetic OPENING/is_closing flags verified | BLOCKER real data | Finance maps production flags |
| D-05 | No tenant key/RLS in synthetic warehouse | BLOCKER security | Auth/DB owner supplies policy and grants |
| D-06 | `v_mgmt`/`v_tax` are synthetic governed views | BLOCKER tax/production | Tax owner approves real view semantics |
| D-07 | R-01..R-20 formulas retained unchanged | OPEN | Domain owner adjudicates risks |
| D-08 | Decimal(18,2) source; ratio cast Decimal(38,10) | ACCEPTED synthetic | Approve production rounding |
| D-09 | 10 custom synthetic handlers, 10 explicitly blocked | PARTIAL | Source/domain owners approve each handler |
| D-10 | No raw warehouse rows are sent to LLM; offline selector default | ACCEPTED synthetic | Privacy owner approves provider use |
| D-11 | Ollama adapter exists; provider/model not supplied | BLOCKER E0/E1 provider eval | Product owner selects provider |
| D-12 | Hashing embedding is reproducible baseline | ACCEPTED baseline | Benchmark approved multilingual model |
| D-13 | Clock 2026-10-14, Asia/Ho_Chi_Minh | ACCEPTED demo | Product owner approves relative-time policy |
| D-14 | GitHub Actions + Makefile supplied | ACCEPTED implementation | CI owner enables workflow |
| D-15 | Official competition rules unavailable | OPEN | Demo owner supplies rubric |
| D-16 | Performance measured locally only | OPEN | Ops supplies load profile/hardware |
| D-17 | Stateless single turn | ACCEPTED P0 | Product owner decides multi-turn |
| D-18 | 46 catalog metrics generic; runtime custom matrix explicit | PARTIAL | Domain owner approves advertised set |
| D-19 | Ambiguous generic profit asks for clarification | ACCEPTED demo | Domain owner may version a default |
| D-20 | Warehouse metadata says VND | ACCEPTED synthetic | Real DB owner verifies production unit |

No decision in this file constitutes human finance, security or acceptance
signoff.
