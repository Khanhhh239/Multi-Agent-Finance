# Agent 1 — Trợ lý dòng tiền (Cash-Flow Copilot): dữ liệu + mô hình T0–T12

Hiện thực hoá [Phần 7 — nhiệm vụ Agent 1](../graphRAG/DIGITAL_ACCOUNTING_PART7_AGENT1_TASKS.md) trên nền
[Phần 5 — nguồn dữ liệu](../graphRAG/DIGITAL_ACCOUNTING_PART5_AGENT1_DATA_SOURCES.md), kế thừa và vượt
`invoice_prediction` (T1 cũ chỉ dùng LightGBM phân vị trên một bộ dữ liệu).

- **Dữ liệu**: xem [docs/DATA_CARD.md](docs/DATA_CARD.md) — crawl 8 nguồn thật (có SHA-256), 4 thế giới SME Việt Nam
  tổng hợp hiệu chỉnh theo Atradius VN 2025 + OxCGRT VN + luật VN, thiết kế cho **domain adaptation** (nguồn → đích niêm phong).
- **Phương pháp**: xem [docs/METHODS.md](docs/METHODS.md) — lựa chọn SOTA theo từng T và lý do.
- **Kết quả**: xem [docs/RESULTS.md](docs/RESULTS.md) — mọi bảng số lấy từ `outputs/` (CSV), kể cả chỗ mô hình thua.

## Cấu trúc

```
Agent1/
  agent1/
    calendar_vn.py          T5: lịch VN, Tết, nghỉ bù, hạn thuế/BHXH/lương, lương tối thiểu vùng (có ngày hiệu lực)
    synth/                  T12: máy phát thế giới (world.py), tên/MST/nội dung CK (names.py),
                            XML hoá đơn điện tử (einvoice.py), kiểm định độ trung thực (fidelity.py), calibration_vn.json
    data/                   T0: real_loaders.py (8 nguồn thật -> lược đồ chuẩn), schema.py (cổng chất lượng)
    models/                 features.py (snapshot as-of, chống rò rỉ), t1.py (T1/T2), t4_revenue.py, t6_cash.py,
                            t7_changepoint.py, t9_recon.py
    eval/metrics.py         T11: pinball, interval score, CRPS, IBS, ECE, C-index, WAPE, bootstrap
  scripts/
    crawl.py                tải dữ liệu công khai + MANIFEST
    build_worlds.py         hiệu chỉnh máy phát + dựng src / tgt / sens_uk / sens_coface
    run_t1.py               T1/T2/T8/T9-nhãn: A rolling-origin, B domain adaptation, C dữ liệu thật, D cure, E/F
    run_t2_t3.py            T2 trên SBA 7(a) thật, T3 tranh chấp/trả một phần
    run_t4.py  run_t6.py  run_t7.py  run_t9.py
    run_all_t1.sh           chạy tuần tự (giới hạn luồng: máy dùng chung)
    realism_audit.py        công cụ kiểm tra bộ hoá đơn (từ Phần 7)
  tests/test_t0_t5.py       15 kiểm thử: hạn thuế theo ví dụ luật, MST, XML, cổng chất lượng
  data/{raw,interim,processed,synthetic}/   outputs/{t1,t4,t6,t7,t9,t2_t3}/   docs/
```

## Chạy lại từ đầu

```bash
python -m venv .venv && .venv/Scripts/pip install numpy pandas scipy scikit-learn lightgbm xgboost catboost holidays rapidfuzz ruptures statsmodels pyarrow matplotlib requests openpyxl lxml pytest unidecode torch chronos-forecasting
```
```bash
.venv/Scripts/python.exe scripts/crawl.py --only wdi_vn,oxcgrt,uk_ppr,online_retail_ii,berka,customer_invoices,sba_7a,bpi2019
```
```bash
.venv/Scripts/python.exe scripts/build_worlds.py --calibrate --worlds src,tgt,sens_uk,sens_coface
```
```bash
.venv/Scripts/python.exe -m pytest -q tests
```
```bash
bash scripts/run_all_t1.sh
```
```bash
.venv/Scripts/python.exe scripts/run_t6.py
```

`AGENT1_THREADS` (mặc định 6) giới hạn số luồng LightGBM/XGBoost — trên máy dùng chung, để mặc định 20 luồng làm
huấn luyện chậm hơn hàng chục lần do tranh chấp CPU.
