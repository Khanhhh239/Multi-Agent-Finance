# R2 ? chu?n ??u ra, model theo doanh nghi?p v? ngu?n t?ng lu?t

R2 t?ng th? **PARTIAL**. Hi?n ?? c? adapter MethodScore/GraphEvidence, fit/score ri?ng theo DN v? l?p n?i ??u v?o ngu?n cho t?ng lu?t. Ch?a c? b? t?nh ?i?m lu?t canonical ??y ?? ho?c benchmark hi?u qu?; ch?a m? active/queue/UI.

**C?p nh?t CR-015, 11/11/2026:** [b?o c?o n?i ngu?n t?ng lu?t](rule_sources_20261111/REPORT.md). Catalog ?? 35 lu?t, resolver theo effective/observed tr??c ch?n revision, lo?i nh?m ??ng th?i kh?i history, gi? signed money/provenance v? gaps c? th?. K?t qu? snapshot/CLI c? `methods.rules.details.rule_inputs`; source ready kh?c evaluated, t?ng lu?t canonical v?n unavailable/null.

- **572 tests pass**, 0 skip/failure/error: [JSON](rule_sources_20261111/native_tests.json). 13 test ngu?n m?i; 32 ca adapter/job hi?n h?nh n?m trong full regression. C?c log l?i tr??c s?a ???c gi? trong b?o c?o.
- [B?n ?? ngu?n](rule_sources_20261111/rule_source_catalog.json), [checks demo](rule_sources_20261111/demo_checks.json), [parity](rule_sources_20261111/parity_report.json): 5 ph??ng ph?p s? sai s? 0; native score/hits/graph kh?ng ??i.
- [Demo model b?n code hi?n h?nh](rule_sources_20261111/company_demo/summary.json): C001/Isolation Forest v? C002/ECOD, m?i DN train 10/reference 5, score 5/5 d?ng m?i b?ng process ri?ng t? DB. Source plans v?n b?o thi?u ??ng th?c t?, kh?ng gi? ?? ngu?n. S? d?ng ch?m th?nh c?ng kh?ng l? ?? ch?nh x?c ML.
- [Fit manifests hi?n h?nh](fit_manifest.json) d?ng hash code hi?n h?nh, kh?ng auto-active; manifest tr??c ???c gi? trong th? m?c CR-015. Feature contract R1 v?n 33 c?t, fingerprint kh?ng ??i. Guard v?n t? ch?i artifact code/feature/runtime c? kh?ng t??ng th?ch.

Ph?m vi c?n l?i: b? sung adapter/h?p ??ng cho b?ng/tr??ng thi?u, evaluator lu?t canonical + parity ri?ng, benchmark E1?E2, D-03/04/09, active lifecycle v? scheduler/recovery. Kh?ng c? formal command/gate cho to?n R2 trong ph?n nh? n?y; stage_commands R2 ch?a c?u h?nh, kh?ng g?n READY_FOR_REVIEW/DONE ho?c chuy?n R3.

L?ch s?: [chu?n h?a CR-012 + job CR-013](rule_sources_20261111/prior_R2_REPORT.md), [job model theo DN](company_fit_20261111/REPORT.md), [ki?m th? 5?5/no-fit CR-014](adapter_acceptance_20261111/REPORT.md). C?c b?ng ch?ng c? gi? nguy?n, kh?ng coi score ML l? x?c su?t gian l?n ho?c nh?n x?c minh.
