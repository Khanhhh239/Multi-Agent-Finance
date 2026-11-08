# 9. Hiệu năng, môi trường và bẫy kỹ thuật

> **Biên tập 06/11/2026:** thời gian và giới hạn tài nguyên bên dưới là đo/ước lượng trong bối cảnh cũ, không phải benchmark mới hoặc cam kết latency. Phần tối ưu là đề xuất cần kiểm chứng, chưa được áp dụng chỉ vì tài liệu được gộp.

## 9.1 Tra tham số theo đúng phiên bản

Bảng siêu tham số lặp trước đây đã bỏ để tránh coi cấu hình Khánh 13 tuần
là cấu hình v6 hoặc unified hiện tại. Các bản chạy khóa tham số trong
protocol/train metadata; không suy tham số từ một bảng “hiện tại” chung.

| Phiên bản / khối | Nguồn định nghĩa |
|---|---|
| T1 nhị phân Khánh/pipeline cũ | [T1 hazard](02_t1_hazard_thoi_diem_tra.md), `agent1/models/t1.py` và protocol của benchmark |
| V5 / V6 gốc | [Phương pháp v5/v6](T1_COMPETING_RISKS_V5_V6.md), protocol trong package từng thử nghiệm |
| V6 ngành + ledger, 93 feature | [Protocol P0–P4](T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md) và `final_selection.lock.json` |
| Unified v2/r3 | [Contract v2](UNIFIED_COLLECTION_V2_CONTRACT_2026-11-04.md), `experiments/unified_collection_v2/protocol.json` |
| T2/T3/T8 | [Xác suất hóa đơn](03_t2_t3_t8_xac_suat_hoa_don.md) |
| T4/T5 | [Doanh thu và lịch chi](04_t4_t5_thu_moi_va_chi.md) |
| T6 / T7 / T9 | [Mô phỏng](06_t6_monte_carlo_conformal.md), [điểm gãy/đối soát](07_t7_t9_t10.md) và protocol riêng |

Tần suất snapshot, cửa sổ nhãn, EB/EWM, số đường MC, seed và ngân sách
thread cũng thuộc giao thức từng lần chạy. Không chuyển các giá trị cũ
sang mô hình mới mà không ghi nhận thay đổi.

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
9. **Môi trường Python:** workspace hiện có `.venv/Scripts/python.exe`; không dùng đường dẫn `Agent1/.venv` của môi trường cũ. Ghi môi trường thực tế của lần chạy, không giả định venv có thể chuyển nguyên sang máy khác.

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
