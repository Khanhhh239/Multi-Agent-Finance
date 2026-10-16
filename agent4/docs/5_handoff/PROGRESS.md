# Kết quả thực hiện handoff — 16/10/2026

**công thức chưa được kế toán duyệt (G0.7 mở).** G0.7 vẫn **CHƯA ĐẠT**, không có chữ ký giả lập. Người dùng cho phép tiếp tục **P1 thử nghiệm** ngày 16/10/2026; không coi đó là duyệt công thức hay sẵn sàng pilot.

Phần kỹ thuật **T0.1–T0.5 đã thực hiện và kiểm tra**. P1 đang triển khai; P2–P4 chưa thực hiện, chưa tuyên bố M1. Kết quả P0 cũ được giữ làm bằng chứng lịch sử bên dưới.

## P1 thử nghiệm — tiến độ theo thẻ

- **T1.1:** `OllamaClient` và `ScriptedClient`; timeout, một retry, schema/native tools, think, keep_alive, usage và latency. Đã gọi thật cả 4B và 8B: 4B 16/6 token vào/ra, 56.183 ms; 8B 24/6 token, 28.856 ms. Đây là phép thử JSON có tính cả chi phí tải model, chưa phải M1 hay benchmark chất lượng. Chi tiết `measurements/t1_1_clients.json`; test đầy đủ kể cả `llm` được chạy trước commit.

## Bằng chứng

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

Theo `3_evaluation/05_tieu_chi_nghiem_thu.md`: “Ba cổng, cứ qua cổng mới sang cổng sau”. Vì chưa có xác nhận G0.7, công việc dừng tại cổng này; không giả lập chữ ký kế toán. Nếu người dùng cho phép tiếp tục P1 thử nghiệm, phải giữ G0.7 là chưa đạt và không gắn nhãn sẵn sàng pilot.

Git riêng đã được khởi tạo trong workspace để tránh thay đổi Git cha ở `C:/Users/Admin`. Các thẻ được tách thành commit và nhánh local. Chưa có remote của dự án nên chưa tạo/push PR.
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
