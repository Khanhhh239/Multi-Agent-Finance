# Kết quả thực hiện handoff — cập nhật 19/10/2026

**P2 đang triển khai theo yêu cầu mới:** Step0 → T2.1–T2.6 → dừng M2; xem `P2_PROTOCOL.md`. **formulas not accountant-approved**; G0.7 OPEN / CHƯA ĐẠT. Kết quả M1 phía dưới là lịch sử, không phải metric P2. Test seed9001 chỉ được mở câu hỏi/kết quả ở lượt final duy nhất sau khi đóng băng B*.

**công thức chưa được kế toán duyệt (G0.7 mở).** G0.7 vẫn **CHƯA ĐẠT**, không có chữ ký giả lập. Người dùng cho phép tiếp tục **P1 thử nghiệm** ngày 16/10/2026; không coi đó là duyệt công thức hay sẵn sàng pilot.

Kết quả lịch sử 17/10: phần kỹ thuật **T0.1–T0.5 và T1.1–T1.10 đã thực hiện và kiểm tra**. **M1 thử nghiệm: 10/10 câu mẫu đúng bằng Qwen4B thật**, 31.702/1.680 token vào/ra, p50=4,109s, p95=6,622s; lúc đó **2.586 test passed**. Hiện tiếp tục P2 theo yêu cầu mới; P3/P4 chưa thực hiện. Không coi M1 là qua G0.7, G1 hoặc sẵn sàng pilot. [Báo cáo M1](M1_REPORT.md) giữ cả lượt sai trước sửa; tiến độ P2 theo từng thẻ bên dưới.

## P1 thử nghiệm — tiến độ theo thẻ

- **T1.1:** `OllamaClient` và `ScriptedClient`; timeout, một retry, schema/native tools, think, keep_alive, usage và latency. Đã gọi thật cả 4B và 8B: 4B 16/6 token vào/ra, 56.183 ms; 8B 24/6 token, 28.856 ms. Đây là phép thử JSON có tính cả chi phí tải model, chưa phải M1 hay benchmark chất lượng. Chi tiết `measurements/t1_1_clients.json`; test đầy đủ kể cả `llm` được chạy trước commit.

## Bằng chứng lịch sử P0 (16/10/2026)

| Hạng mục | Kết quả | Tệp kiểm chứng |
|---|---|---|
| T0.1 | Python 3.12.13 trong `.venv`, package editable, fixture tự sinh/cache seed dev, script test | `pyproject.toml`, `scripts/run_tests.ps1`, `tests/conftest.py` |
| T0.2 / G0.1 | 396/396 ô = 66 chỉ số × 6 kỳ khớp oracle; thêm các test khung thuế và explain | `eval/oracle.py`, `measurements/g0_golden.json` |
| T0.3 / G0.2 | Tổng nhóm, cộng kỳ, số dư theo tháng, đối soát AR/AP/kho, LNST hai đường, idempotent | `tests/test_invariants.py` |
| T0.3 / G0.5 | Tái sinh cùng seed, hash toàn bộ dòng sổ cái bằng nhau | `tests/test_invariants.py::test_same_seed_reproduces_ledger` |
| T0.4 / G0.3–4 | 84 biểu thức kỳ tường minh × 5 ngày tham chiếu, 24 alias × 5 ngày, ca biên và property test định dạng | `tests/test_periods.py`, `tests/test_formatting.py` |
| T0.5 / G0.6 | Phạm vi AND, giao bộ lọc, phạm vi rỗng, exact code, explain, phép loại khách lớn nhất trong phạm vi; custom không hỗ trợ báo lỗi | `tests/test_engine_hardening.py` |
| T0.5 | So sánh custom, whitelist receipt/bank, CTE cash không replace, cursor từng yêu cầu, mã lỗi, lineage có version/phạm vi/tham số | `agent4/engine/`, `agent4/datagen/build.py` |
| Hiệu năng | p95 truy vấn kho 140.583 dòng trong lượt oracle và quét GL nhân bản 5 triệu dòng; số đo chi tiết trong JSON | `measurements/g0_golden.json`, `measurements/g0_gl_scan_5m.json` |
| Toàn bộ test | **1.390 passed**, không skipped/xfail, 34,48 giây trên máy hiện tại | `measurements/g0_test_suite.json`; XML đầy đủ tại `artifacts/g0-pytest.xml` |

Benchmark 5 triệu dòng chỉ nhân bản `gl_wide`, đo 46 chỉ số tuyến tính/tỷ số, **không nhân bản sổ chi tiết**. Đây là bằng chứng tốc độ quét cho G0.8; chưa thay thế bài đo đầy đủ 1M/5M/10M, dữ liệu đa công ty, tải đồng thời hoặc pilot T4.2. Không tuyên bố toàn bộ G0.8 đã được chứng nhận.

## Lỗi và ngoại lệ được ghi nhận

- Đã sửa lỗi đọc số `1.25`, mã hóa đơn bắt đầu bằng số và mã kỳ `2026-Q3`; lỗi ngày sai rò ValueError; khoảng 0 ngày/tháng; thiếu kỳ canonical và thứ tự trích kỳ.
- Đã sửa thứ tự nhóm không ổn định khi giá trị bằng nhau; `explain` hiện kiểm tra khung/phạm vi.
- A4 vẫn lệch 500.000 đồng có chủ đích. G0.2 được kiểm tra kèm ngoại lệ, không đổi thành khẳng định cân sổ nguyên trạng.
- Tháng 01 có chuyển LNST năm trước 4212 → 4211. Test tách chuyển năm khỏi kết quả tháng và kiểm tra chuyển năm bằng LNST 2025. Đã ghi `DECISIONS.md`.
- Ngân sách dùng random không seed từ trước; chưa tái lập toàn kho và chưa có cache thực tế. Sổ cái và ground truth được giữ nguyên.
- Các custom nhận phạm vi hiện có: `dso`, `dpo`, `dio`, `cash_conversion_cycle`, `expense_spikes`, `mgmt_vs_tax_gap`. Custom còn lại báo `ScopeNotSupported` khi có hạn chế phạm vi; cần mở rộng có test ở P3. Không coi bộ lọc giao diện là biện pháp phân quyền.
- Oracle lọc chiều hỗ trợ chỉ số GL và một số custom; những phép lọc sổ chi tiết chưa cài đặt báo lỗi rõ, không im lặng bỏ bộ lọc.

## Chạy lại trên máy này

```powershell
cd C:\Users\Admin\Downloads\Agent4
./.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=artifacts/g0-pytest.xml
./.venv/Scripts/python.exe -X utf8 -m eval.review_formulas
# Benchmark cần đường dẫn scratch chưa tồn tại:
./.venv/Scripts/python.exe -X utf8 -m eval.benchmark_engine --out data/benchmark_5m_repeat.duckdb
```

Kho mặc định hiện có `data_version=v2.0`, seed 20251, mốc dữ liệu 14/10/2026, khóa sổ đến 08/2026. Bản kho ban đầu được giữ ở `data/cfo_warehouse.duckdb.unversioned`. Chưa sinh/chạy seed val 71 hoặc test 9001; bộ test agent giữ nguyên chưa sử dụng.

## Phần cần người phụ trách

`FORMULA_REVIEW.md` có đủ 66 hàng: công thức, ví dụ Q3, kết quả oracle và câu hỏi cần chốt. Kế toán trưởng cần xác nhận các chỉ số Must, ghi tên, ngày và quyết định Đồng ý/Sửa/Bỏ. Ưu tiên DSO gồm VAT, ngày tiền về, vốn chủ chưa kết chuyển, khung nghĩa vụ thuế, giả định dự báo, cách so chi phí nhiều tháng và thuế mô phỏng.

Theo `3_evaluation/05_tieu_chi_nghiem_thu.md`: “Ba cổng, cứ qua cổng mới sang cổng sau”. Người dùng đã cho phép tiếp tục riêng P1 **thử nghiệm**, giữ G0.7 **CHƯA ĐẠT** và dừng tại M1; không giả lập chữ ký hay gắn nhãn sẵn sàng pilot. 22 chỉ số Must đều **cần duyệt trước pilot**.

Git riêng được khởi tạo trong workspace để tránh thay đổi Git cha ở `C:/Users/Admin`. Mỗi thẻ có commit riêng; `scripts/publish_card.py` đồng bộ vào thư mục `agent4/` của monorepo và đẩy lên `agent4-Khanh`, giữ lịch sử upstream, không force push. Không tạo PR trong phạm vi yêu cầu này.
- T1.1 xác nhận trước commit: **1.398 passed, 0 skipped**, 78,44 giây; có hai test Ollama thật (`AGENT4_RUN_LLM=1`). công thức chưa được kế toán duyệt (G0.7 mở).

### T1.2 — P1 thử nghiệm

Schema bảy công cụ chỉ đọc/draft, enum từ registry/engine, executor kiểm quyền và scope, facts pack chỉ display và văn bản bọc; 66 chỉ số chạy qua executor.

Toàn bộ test trước commit: **1472 passed, 0 skipped**, 72.38 giây; `artifacts/t1_2-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### Phiếu kế toán song song — G0.7 CHƯA ĐẠT

`FORMULA_REVIEW_ONE_PAGE.pdf`: A4 ngang đúng 1 trang, 22 chỉ số Must, mỗi dòng có công thức lời, ví dụ Q3, câu hỏi và nhãn “cần duyệt trước pilot”. Đã kiểm tra pypdf và ảnh render Poppler, không tràn/cắt chữ. Bản đầy đủ vẫn giữ 66 chỉ số; không có chữ ký duyệt. Toàn bộ test gần nhất trước commit: 1.472 passed (có 4B/8B thật). công thức chưa được kế toán duyệt (G0.7 mở).

### T1.3 — P1 thử nghiệm

BM25 metadata, 100 câu smoke dev phủ66 chỉ số: recall@8=100%; 500 lượt mean0.285ms/p950.410ms, chưa đo held-out hoặc embedding.

Toàn bộ test trước commit: **1695 passed, 0 skipped**, 90.74 giây; `artifacts/t1_3-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.4 — P1 thử nghiệm

Hints metadata-only: 100 câu có nhãn, 100 benign và các ca kho thật; trích kỳ/so sánh/nhóm/khung/thực thể, không tính tài chính. Đã sửa FP kinh doanh và còn/CON.

Toàn bộ test trước commit: **1793 passed, 0 skipped**, 83.28 giây; `artifacts/t1_4-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.6 — P1 thử nghiệm

97 test validator riêng: schema, candidate enum, khung điều hành/thuế, kỳ/nhóm/thực thể, scope/quyền và từ chối bộ lọc custom chưa cài đầy đủ. Toàn bộ hồi quy gồm oracle vẫn xanh.

Toàn bộ test trước commit: **2331 passed, 0 skipped**, 98.44 giây; `artifacts/t1_6-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.7 — P1 thử nghiệm

Renderer/verifier:66 chỉ số render thật qua kiểm;200 diễn đạt đúng FP0;320 lỗi tiêm8loại chặn320/320 trong unit test. Kiểm kiểu tiền/phần trăm/ngày/hệ số, kỳ, nhãn, dấu và anchor giá trị đầu khối.

Toàn bộ test trước commit: **2387 passed, 0 skipped**, 96.66 giây; `artifacts/t1_7-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.5 — P1 thử nghiệm

Prompt ba phần có snapshot,60 few-shot dev, BM25 loại câu trùng nguyên dạng, state giữ ba lượt/hết hạn15phút và ràng buộc người dùng; dữ liệu state và câu hỏi được bọc.

Toàn bộ test trước commit: **2395 passed, 0 skipped**, 125.03 giây; `artifacts/t1_5-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.8 — P1 thử nghiệm

Orchestrator đã có30 kịch bản scripted: đường hints/retriever/schema/validator/engine/render/verifier, sửa<=2, model chết chuyển form, số sai fallbackfacts, scope/state/timeout. Chưa đo accuracy thật10câu.

Toàn bộ test trước commit: **2425 passed, 0 skipped**, 133.45 giây; `artifacts/t1_8-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.9 — P1 thử nghiệm

A8 thật đi qua explain được ẩn chỉ dẫn và có cảnh báo; lợi nhuận trước/sau không đổi. 40 attack tổng hợp bắt40/40, 100 câu tài chính benign FP0 trong smoke; không suy ra miễn nhiễm phổ quát.

Toàn bộ test trước commit: **2569 passed, 0 skipped**, 163.75 giây; `artifacts/t1_9-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### T1.10 — P1 thử nghiệm

CLI chat/form và trace JSONL hoàn tất. M1 Qwen4B thật: lượt dev 1=9/10, lượt 2=8/10, lượt 3=10/10; 31.702/1.680 token vào/ra, p50=4,109s, p95=6,622s. Giữ cả ba lượt và báo cáo fallback; không chạy val/test hoặc đánh giá lớn.

Toàn bộ test trước commit: **2586 passed, 0 skipped**, 64.53 giây; `artifacts/t1_10-final-pytest.xml`. công thức chưa được kế toán duyệt (G0.7 mở).

### P2.Step0a — P2 thử nghiệm

formulas not accountant-approved. Symbolic insight slots: M1 dev 10/10, fallback 7/10 to 0/10; 20 calls, 15129/414 tokens. Excluded from P2 metrics; n10 does not prove population fallback below10%.

Toàn bộ test trước commit: **2595 passed, 0 skipped**, 91.40 giây; `artifacts/p2_step0a-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### P2.Step0b — P2 thử nghiệm

formulas not accountant-approved. Budget generation uses warehouse-seeded SHA256 per group, independent of SQL thread/group order. Regenerated dev v2.1; 396/396 independent goldens; GL hash unchanged; same-seed budget reproduction tested.

Toàn bộ test trước commit: **2596 passed, 0 skipped**, 88.85 giây; `artifacts/p2_step0b-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### P2.Step0c — P2 thử nghiệm

formulas not accountant-approved. Created val seed71 and sealed test warehouse seed9001, all v2.1. All AR/AP/inventory reconciliation gaps exactly0 for train/val/test. No test questions or evaluation results opened.

Toàn bộ test trước commit: **2597 passed, 0 skipped**, 82.48 giây; `artifacts/p2_step0c-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.1 — P2 thử nghiệm

formulas not accountant-approved. E1/E2 each600 TRAIN /200 val /400 sealed test, 66 metrics, >=3 per metric and >=2 forms per split, exactly25% noise, 100% independent oracle coverage. Excluded880 tuning strings. TRAIN-only bank1200 examples replaces old dev bank.

Toàn bộ test trước commit: **2602 passed, 0 skipped**, 109.02 giây; `artifacts/t2_1-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.2 — P2 thử nghiệm

formulas not accountant-approved. E3/E4 150/50/100 each; E5 100/40/100.30 ambiguity families,15 refusal groups, missing-period negative controls. Reviewed54 train/val rows (10%); test rows not reviewed. TRAIN bank1600, behavior diverse.

Toàn bộ test trước commit: **2604 passed, 0 skipped**, 111.67 giây; `artifacts/t2_2-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.3 — P2 thử nghiệm

formulas not accountant-approved. E6 400/100/300 with7 error kinds plus faithful variants (TRAIN50 per kind); E7 80/30/80 conversations of2–5 turns and10 reference patterns. Gold conversation values use independent oracle; test content remains sealed.

Toàn bộ test trước commit: **2628 passed, 0 skipped**, 73.26 giây; `artifacts/t2_3-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.4 — P2 thử nghiệm

formulas not accountant-approved. E8 60/20/60 with20 techniques and user/tool/name/A8 stages; poison copies preserve amounts. E9 100/30/100 independent reference-SQL tasks, SQL capability disabled. E10 ten seed-varied ground-truth warehouses generated; bulletin not measured.

Toàn bộ test trước commit: **2630 passed, 0 skipped**, 114.59 giây; `artifacts/t2_4-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.5a — P2 thử nghiệm

formulas not accountant-approved. Configurable pipeline/CLI supports true66 native functions, schema/hints/kNN/language controls, validated read-only batches<=3, canonical-code history, source templates and why-premise caveats. Added multi60/20/40 and why30/20/30 oracle datasets; no val/model results or final test run yet.

Toàn bộ test trước commit: **2707 passed, 0 skipped**, 281.78 giây; `artifacts/t2_5a-security-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.5b — P2 thử nghiệm

formulas not accountant-approved. Runner/scorers/bootstrap95%CI, exclusions and one-final-run global seal implemented; 3 TRAIN smoke cases exported tokens/latency, not validation metrics. Blind aggregate split audit: 2330/760/1710. Corpus language-v2 uses genuine synonym/noise variation; no val model measurement or test preview.

Toàn bộ test trước commit: **2720 passed, 0 skipped**, 82.82 giây; `artifacts/t2_5b-final-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.5c — P2 thử nghiệm

formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở). Audited first-response layer scoring, exact currency checks, source-derived renderer footer counts, sealed-test controls and VAL-only interrupted recovery; 2733 tests passed. B0 8B remains partial446/760, no held-out access.

Toàn bộ test trước commit: **2733 passed, 0 skipped**, 75.50 giây; `artifacts/p2-recovery-pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### P2 running checkpoint — 2026-10-20T08:25:47.425937+00:00

**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở). G0.7 OPEN / CHƯA ĐẠT;22 Must cần duyệt trước pilot.

T2.5c published upstream72d4205d17eb49311915db23d7283aab89cdbf47 after2733/2733 tests (0skip). B08B resumed without repeating446 completed cases; one E3 lost-started case remains excluded. At this checkpoint657 completed/760planned,658 recorded; E7 still running. B04B complete: first-response E1 TSA72.5% CI[66,78.5],n200; E2 args36% CI[29,42.5],n200. Do not present these as G1 success. No held-out test opened.

Detached ordered worker and final worker are alive; see artifacts/p2_background_workers.json, p2_ordered_checkpoint.json, p2_ordered_detached.*.log and p2_final_detached.*.log. They run hardware TRAIN probes, ordered val experiments, tests/publish each card, matching-family quantization preparation, full B* val, freeze, sole test, M2 report/publish, then stop. Codex thread heartbeat agent4-p2-n-m2 is ACTIVE every10minutes to diagnose interruptions, avoid duplicate GPU runs, and report M2 once verified; pause it after M2. Do not rerun an active worker or completed/lost-started test case. Current helper/doc edits are pending the next B0 card full test+commit; no concurrent live pytest during measurements.

### Reboot recovery — 2026-10-20T11:14:16.917723+00:00

**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở). B08B full-val run completed759/760 with one lost-started E3 excluded: E1 first TSA83.5% CI[78.4875,88.5],n200; E2 args45% CI[37.5,52],n200; observed tokens5554862/40903,20 usage-unknown calls; latency n480 p50=4523.9174ms,p95=21230.7581ms. This is not G1 acceptance.

OS reboot at20Oct18:08:13 terminated hardware probe/server/workers.4B ctx8192 TRAIN probe completed38/40 with2 tuning exclusions and1 scheduler OOM; sampled available RAM minimum49MiB.8B ctx4096 has17 recorded rows (15 complete,2 excluded), one started E7 lacks a result. Hardware helper now reuses complete measurement and resumes exactly frozen partial journal without repeat; resumed preload/VRAM scope and split server logs are recorded. No held-out access. Next B0 card will run all tests and publish the pending helper/docs changes before H2.

### T2.6-H00_B0 — P2 thử nghiệm

formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở). Both full-val baselines measured; no held-out test accessed.

Toàn bộ test trước commit: **2733 passed, 0 skipped**, 263.55 giây; `artifacts\H00_B0_pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).

### T2.6-H02_hints — P2 thử nghiệm

formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở). Measured H02_hints on frozen val; selected reference.

Toàn bộ test trước commit: **2733 passed, 0 skipped**, 264.70 giây; `artifacts\H02_hints_pytest.xml`. formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).
