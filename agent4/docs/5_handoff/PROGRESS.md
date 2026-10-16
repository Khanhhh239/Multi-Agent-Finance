# Kết quả thực hiện handoff — 16/10/2026

Phần kỹ thuật **T0.1–T0.5 đã thực hiện và kiểm tra**. Toàn dự án chưa hoàn tất: **T0.6/G0.7 cần kế toán trưởng duyệt**, nên chưa tuyên bố qua G0, M0 hoặc M1. P1–P4 chưa thực hiện. Không có số đo agent/Qwen để báo đạt.

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
