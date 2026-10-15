# 9. Tham số, tối ưu hiệu năng và bẫy kỹ thuật

## 9.1 Bảng siêu tham số hiện tại

| Khối | Tham số | Giá trị | Ghi chú tối ưu |
|---|---|---|---|
| Snapshot | tần suất | 7 ngày (train dùng 14 ngày) | 14 ngày giảm 50% dữ liệu, ít mất thông tin vì HĐ lặp |
| | visible_from | M tháng | thí nghiệm B |
| | EB k | 4 | X14 học k |
| | nửa đời EWM | 90 ngày | thử 45/90/180 |
| T1 hazard | leaves / min_data / lr | 63 / 200 / 0,05 | X11 |
| | rounds | 600 | early stopping |
| | tuần K | 13 | đuôi hình học sau đó |
| | cap | 120 ngày | đồng bộ với nhãn |
| T1 QLGBM | leaves / lr / rounds | 63 / 0,1 / 350 | giảm để nhanh |
| T1 AFT | σ / depth / rounds | 0,3 / 6 / 300 | σ rất nhạy (xem bẫy) |
| CQR | α | 0,2 | cửa sổ ≥63 ngày, cách test ≥120 ngày |
| T2 | leaves / min_data / λ₂ / rounds | 31 / 200 / 10 / 400 | isotonic nếu ECE > 0,02 |
| T4 | lags / leaves / min_data / rounds | 13 / 31 / 50 / 500 | |
| T6 | n_sim | 1.000 (kịch bản 600) | CRN (common random numbers) cho so sánh kịch bản |
| | ρ, ν | chọn trên nguồn, 4 | X32 |
| | ACI γ | 0,01 | tăng ×3 ở chế độ khủng hoảng |
| T7 | cửa sổ PIT | 40 lần trả | |
| | CUSUM k,h | 0,25; 5 | |
| T9 | top-k tên | 4 (+2 theo nội dung) | |
| | ngưỡng p | 0,5 | tăng 0,9 + hàng chờ |
| | dung sai tiền | 25.000đ | theo phí |
| Thread | `AGENT1_THREADS` | 6 | máy dùng chung |

## 9.2 Hiệu năng đã đo / ước lượng

| Thao tác | Quy mô | Thời gian | Nguồn |
|---|---|---|---|
| Sinh thế giới | 17.825 HĐ | ≈20 giây | đo |
| `expand` hazard | 82.509 snapshot-hàng → 203.203 | 0,9 giây | đo |
| LightGBM hazard 100 vòng | 203k hàng, khi CPU bận | 47,6 giây | đo (tranh chấp luồng) |
| QLGBM 100 vòng ×3 | 82k hàng, 20 luồng bận | 193 giây | đo — *bẫy luồng* |
| XGBoost AFT 100 vòng | | 19 giây | đo |
| Cache snapshot `src` (848k hàng × 59 cột) | | vài phút | đo; parquet float32 |
| T9 sinh ứng viên + huấn luyện (12 công ty `src` 2023) | 31.346 ứng viên | 506 giây (Python + RapidFuzz, máy bận); phần `tgt` chưa đo riêng | đo |
| T6 MC 1 DN × 13 tuần | 1.000 đường × ≤2.000 HĐ | ≤3 giây (ước lượng; chưa đo đầy đủ) | ước |

## 9.3 Bẫy kỹ thuật đã gặp (đừng lặp lại)

1. **Quá tải luồng.** LightGBM mặc định dùng mọi nhân; khi máy đang chạy việc khác, thời gian tăng 10–50×. Luôn đặt `num_threads` (`agent1/threads.py`).
2. **Bộ nhớ.** Snapshot >1M hàng × float64 làm `MemoryError` khi lọc; ép float32, lấy mẫu 400k hàng cho BPI.
3. **AFT σ.** XGBoost `survival:aft` với σ≥1 cho MAE 77 ngày; `base_score` phải ở thang log-thời gian.
4. **Rò rỉ khi chia cửa sổ.** Cửa sổ hiệu chỉnh phải cách test ≥ chiều dài nhãn (120 ngày), không thì nhãn "chưa chín" lọt vào.
5. **Nhãn bị kiểm duyệt phải bị cắt tại `label_end`** — kể cả ở tập test (nếu không, đánh giá nhìn thấy tương lai).
6. **CDF từ phân vị** không công bằng với hazard (X3).
7. **Số mô tả thời gian trong SBA**: `EXEMPT` (xem 03_t2).
8. **Tiền xử lý Python ngày/tháng**: `sed` trên file Windows với dấu Unicode — đọc bằng `encoding="utf-8"`.
9. **Kết nối Python:** môi trường mặc định của máy lỗi; dùng venv `Agent1/.venv` (tạo từ `codex-primary-runtime` Python 3.12).

## 9.4 Tối ưu đề xuất khi mở rộng

| Việc | Cách | Lợi ích |
|---|---|---|
| Vector hoá `bank_ledger`/`promises` của máy phát | thay vòng `groupby` bằng sort+cumsum | 10–20× nhanh khi sinh >10M HĐ |
| Sinh ứng viên T9 | blocking theo công ty + chỉ mục n-gram (`rapidfuzz.process.cdist` theo khối) | 5–10× |
| Huấn luyện hazard | lấy mẫu âm (giữ y=0 với p=0,3, trọng số 1/0,3) | giảm 3× hàng khai triển |
| Suy luận đêm | tính hazard 1 lần/khách-hoá đơn, MC dùng lại; cache theo `invoice_id` + hash đặc trưng | giảm 5× |
| Inference | LightGBM `predict` đa luồng, `pred_contrib` chỉ cho top-50 | |
| T6 kịch bản | CRN + bỏ qua hoá đơn nhỏ (<0,1% tổng mở), gộp chúng thành xấp xỉ chuẩn | 5–10× |
| ACI | lưu `α_k` theo DN, vài byte | |
| Môi trường | `requirements.txt` ghim phiên bản; Docker | tái lập |
