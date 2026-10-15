# 01 · Hiện trạng và khoảng trống (đọc đầu tiên)

## 1. Bảng tóm tắt trung thực
| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Bộ sinh doanh nghiệp mẫu | ✅ Xong, chạy được (~1 phút) | `python -m agent4.datagen.build` → 140.583 dòng sổ cái; đối soát AR/AP/kho = 0 |
| Lõi chỉ số (66 chỉ số) | ✅ Viết xong, **chưa được kiểm chứng độc lập** | Smoke: 66 chỉ số × 3 kỳ không lỗi; **chưa có golden test** |
| Bộ phân giải thời gian / định dạng số | ✅ Viết + thử tay | Chưa có unit test chính thức |
| Test hợp đồng v0 | ✅ 12/12 xanh | `pytest tests/test_legacy_contract.py` |
| **Agent loop, công cụ LLM, retriever, validator, verifier, guardrail** | ❌ **Chưa có** | thư mục `agent4/agent/` rỗng |
| Approval gate, audit log, phân quyền | ❌ Chưa có | |
| API, UI, bản tin tuần, adapter Agent 1/2/3 | ❌ Chưa có | `agent4/api`, `agent4/integrations`, `web/` rỗng |
| Bộ dữ liệu đánh giá (E1–E12) và runner | ❌ Chưa có | chỉ có spec (`2_data/07`) |
| Chạy thử với Qwen | ❌ **Chưa chạy lần nào** | Mới tải model (`qwen3:8b`, `qwen3:4b-instruct-2507-q4_K_M`); không có số đo độ chính xác/độ trễ nào |
| Text‑to‑SQL dự phòng | ❌ | |
| Dữ liệu đa công ty / quy mô lớn | ❌ | bộ sinh mới cho 1 công ty |

> **Đừng tin bất kỳ con số "đạt" nào cho agent** — chưa có agent. Các số duy nhất đã đo: tính chất của dữ liệu và 12 test hợp đồng v0.

## 2. Bản đồ mã nguồn hiện có (`agent4/`)
```
agent4/
├─ config.py                    Settings: đường dẫn DB, AS_OF_DATE=2026-10-14, LAST_CLOSED_MONTH=2026-08, LLMConfig (qwen3:8b, T=0, ctx 8192, think off)
├─ datagen/
│   ├─ company.py               Dữ liệu chủ: TK TT133 (60), chi nhánh, phòng ban, 82 mặt hàng, 30 NCC, phân khúc khách, tỷ lệ BH/thuế, Tết/lễ
│   ├─ ledger.py                Sổ cái kép: post(), số dư theo TK/đối tượng, đánh số chứng từ
│   ├─ simulator.py             Mô phỏng ngày‑theo‑ngày (bán/thu/mua/trả/lương/thuế/…) + ca A1…A10   (≈1.280 dòng; có thể tách)
│   └─ build.py                 Ghi DuckDB: sao + sổ chi tiết + view + ngân sách + ground_truth + kiểm tra cuối
├─ engine/
│   ├─ periods.py               resolve_period, previous_period, same_period_last_year, comparable_partial, extract_periods, detect_comparison
│   ├─ formatting.py            fmt_vnd/pct/days/ratio/delta; extract_numbers (phân tích số VN cho verifier)
│   ├─ metrics.py               66 MetricDef (công thức, đồng nghĩa, khung, chiều)
│   ├─ engine.py                ExecutionEngine: query / explain / resolve_entity / build_filters / get_metric (v0) / trạng thái khóa sổ
│   ├─ custom.py, custom2.py    Chỉ số cần sổ chi tiết: tuổi nợ, quá hạn, DSO/DPO/DIO/CCC, dòng tiền trực tiếp, nghĩa vụ sắp tới, bất thường, ngân sách, lương, thuế
├─ agent/ api/ integrations/    (trống — việc cần làm)
tests/test_legacy_contract.py   12 test v0 (đã sửa lỗi của bản gốc, xem mục 4)
data/ (không commit)            cfo_warehouse.duckdb (~28 MB), cfo_warehouse_ground_truth.json — tái sinh được từ seed
docs/                           bộ tài liệu này
```
Các tệp tham chiếu ở gốc nhánh: `schema.md`, `metrics-v0.md`, `sample-questions.md`, `generate_data.py` (đã sửa 2 lỗi), `requirements.txt`.

## 3. Quyết định kiến trúc đã chốt (không cần bàn lại)
1. LLM không tính số, không viết SQL tài chính; mọi số từ `ExecutionEngine.query`.
2. Hai khung `mgmt`/`tax` từ một sổ cái; chọn khung bằng luật + validator.
3. Thời gian & thực thể giải bằng mã tất định.
4. Tool‑use trên tập công cụ ≤ 8, `metric.enum` thu hẹp theo retrieval.
5. Trả lời = khối sự kiện tất định + diễn giải ngắn; verifier chặn số lạ.
6. Hành động chỉ qua `propose_action` → duyệt người → handler → nhật ký.
7. Model mặc định chạy tại chỗ qua Ollama: `qwen3:4b-instruct-2507-q4_K_M` (6 GB) và `qwen3:8b`.

## 4. Lỗi/giới hạn đã biết (cần xử lý hoặc cân nhắc)
| ID | Mô tả | Mức | Gợi ý |
|---|---|---|---|
| K1 | `generate_data.py` gốc có 2 lỗi (INSERT `dim_period` 7 tham số cho 8 giá trị; ghi mã `'C001'` vào khóa số `partner_key`) nên `test_engine.py` gốc chưa từng chạy được. **Đã sửa.** | Đã xử lý | |
| K2 | `test_engine.py` gốc tự mâu thuẫn: kỳ vọng doanh thu 110,4 tr nhưng AR 720 tr không thể cùng đúng với một ngày cố định; kỳ vọng `operating_expenses` = 12 tr trái với `metrics-v0.md` (641+642 = 30 tr). **Bản port đặt `today`=15/05/2026 và sửa kỳ vọng thành 129,6 tr / 77,76 tr / 30 tr.** | Đã xử lý (cần người xem lại) | Xác nhận với tác giả test gốc |
| K3 | `metrics-v0.md` §7 `cash_and_equivalents` có lỗi ưu tiên toán tử (`OR` / `AND` thiếu ngoặc). Bản mới đã đúng. | Đã xử lý | Cập nhật `metrics-v0.md` |
| K4 | **Công thức chưa được kế toán duyệt**; xem danh sách rà soát ở `4_ai_engineering/03` §1.6 | Cao | Task T0.2, T0.6 |
| K5 | `compare_to` bị bỏ qua với chỉ số `kind=custom` (chưa hỗ trợ so sánh kỳ cho tuổi nợ, DSO…) | TB | Task T0.5: thêm hỗ trợ cho `dso`, `dpo`, `dio`, `expense_*` |
| K6 | `custom.cash_journals` dùng `str.replace` trên chuỗi SQL để đổi tên cột (mong manh) | TB | Viết lại bằng CTE thuần |
| K7 | `ExecutionEngine` dùng một kết nối + `RLock`; API đồng thời nên dùng `con.cursor()` mỗi yêu cầu | TB | T3.3 |
| K8 | `explain()` chưa có test; `top_entries` có thể chứa văn bản tự do (diễn giải) — phải bọc khi đưa vào prompt | Cao (an toàn) | T1.9 |
| K9 | `dso_actual` dùng `receipt_date` (ngày ghi sổ), chưa dùng `bank_txn_date` (ngày tiền về) | TB | Quyết định với kế toán; thêm tham số |
| K10 | Biểu thuế TNCN 7 bậc & giảm trừ 11/15,5 tr là giả định (luật mới có thể khác từ giữa 2026) | Thấp (dữ liệu) | Xác minh, cập nhật bộ sinh |
| K11 | `budget` không độc lập với thực tế | Thấp | Ghi rõ trong demo |
| K12 | `build.py` chưa có tham số dòng lệnh cho `as_of`, `last_closed_month` (đang đọc từ `config.py`/biến môi trường) | Thấp | T4.1 |
| K13 | Nhật ký của Git trên Windows: đường dẫn dài có thể làm clone lỗi (`core.longpaths`) | Môi trường | Xem `06` |
| K14 | Trình khởi chạy Python (`py`) trên máy dev hỏng; dùng venv `uv` | Môi trường | Xem `06` |

## 5. Rủi ro lớn nhất cho người làm tiếp
1. **Tự chấm bằng chính engine** → mọi lỗi công thức sẽ "nhìn như đúng". Làm oracle độc lập (T0.2) **trước** khi đo agent.
2. **Model nhỏ bỏ qua gọi công cụ** → xây thu hẹp công cụ + schema ràng buộc trước khi chỉnh prompt.
3. **Rò rỉ dữ liệu test** vào few‑shot/fine‑tune → tuân thủ tách seed.
4. **Tiêm nhiễm qua `description`** — đừng đưa cột này vào prompt chưa bọc.
5. Kỳ vọng: kho mẫu *căng thẳng* (hạn mức vay chạm 20 tỷ) — đó là chủ ý để có hard case; đừng "sửa" nó mà không cập nhật `ground_truth` và docs.
