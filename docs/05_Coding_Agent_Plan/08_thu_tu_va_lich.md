# Thứ tự, phụ thuộc, mốc và tiêu chí hoàn thành

## 8.1 Đồ thị phụ thuộc

```
WP-0 (nền: contract, leakage tests, env) ───────────────┐
        │                                                │
        ├─► WP-1 (T1: đo công bằng, tuning, CQR 2 phía) ─┼─► WP-3 (thích nghi miền, domain randomization)
        │            │                                   │            │
        │            └─► WP-2 (T2 SBA, T3) ──────────────┤            │
        │                                                ▼            ▼
        ├─► WP-D1 (vector hoá máy phát) ─► WP-D2 (hard cases) ─► WP-D3 (sinh lớn, C2ST)
        │                                                │
        ├─► WP-4 (T9 lai) ─► WP-1.4 (nhãn khoảng) ───────┤
        ├─► WP-5 (T5 phiên bản hoá) ─────────────────────┤
        ├─► WP-7 (T7 cụm) ───────────────────────────────┤
        └─► WP-8 (T8 lời hứa) ───────────────────────────┤
                                                         ▼
                                     WP-6 (T6 + T10 + E2E)  ──►  WP-9 (sản phẩm) ──► WP-10 (pilot)
```

## 8.2 Thứ tự đề xuất (tuần làm việc của 1 coding agent; song song được nếu có nhiều agent, **không để hai agent sửa cùng file**)

| Tuần | Gói | Kết quả bắt buộc |
|---|---|---|
| 1 | WP-0.1–0.4; WP-1.1, 1.3, 1.5; WP-6.1 (sửa & chạy `run_t6`) | Test rò rỉ xanh; bảng T1/T6 theo giao thức mới; lỗi demo T10 đóng |
| 2 | WP-1.2 (tuning), WP-1.7 (phân tầng), WP-1.8 (seed), WP-2.1 (SBA) | `best_params.json`; `A_strata.csv`; SBA đa biến thể |
| 3 | WP-3.1–3.4 (B chạy lại có CI; khoảng cách miền), WP-D1 (vector hoá) | Đường cong học; DA1–DA7 có kết luận; máy phát ≥5× |
| 4 | WP-D2 (12 hard-case), WP-3.3 (domain randomization) | `hc_*` + `dr_*`; so sánh (A) vs (B) |
| 5 | WP-4 (T9 lai), WP-1.4 (nhãn khoảng), WP-8 | Precision ≥0,95 / coverage ≥60%; G17/G18 lại |
| 6 | WP-7 (T7 cụm), WP-6.2–6.7 (đối chứng thêm, copula phân tầng, ngưỡng) | G13, G14 có kết luận |
| 7 | WP-D3 (sinh lớn + C2ST), WP-3.6 (scaling), WP-D4 (Home Credit, SEC, BCTC VN) | Tiền huấn luyện lớn; df̂ từ SEC |
| 8 | WP-6.8 (E2E), WP-5 (rules YAML), WP-1.9 (cải tiến mô hình) | `run_e2e.py`; G12/G13 trên nhãn ước lượng |
| 9–10 | WP-9 (API, UI, cảnh báo, LLM, MLOps) | UAT U1–U6 |
| 11–12 | WP-10 (pilot prep), viết báo cáo | Tài liệu pilot, báo cáo kỹ thuật |

## 8.3 Điều kiện GO sang pilot (tóm tắt, chi tiết 03_Evaluation/03)
G1, G2, G5, G9, G11, G12, G13, G15 (F1+MAE), G16 đạt; G3/G4 trong ±5 điểm; không nhóm phân tầng nào cov80 <60%; UAT đạt; giấy tờ dữ liệu (NĐ 13/2023) đủ.

## 8.4 Quyết định đang chờ (hỏi người giao việc trước khi làm)

| # | Quyết định | Phương án mặc định nếu không có trả lời |
|---|---|---|
| Q1 | Có tài khoản Kaggle để tải Home Credit/M5? | Bỏ qua D4.1–4.2, ghi vào báo cáo |
| Q2 | Email/tổ chức dùng làm User-Agent SEC? | Bỏ qua WP-6.4; dùng df=4, ghi giả định |
| Q3 | Có đối tác pilot hoặc dữ liệu DN thật (ẩn danh)? | Chỉ làm tới WP-9 trên dữ liệu giả lập |
| Q4 | Được dùng LLM nào/ngân sách token? | Dùng mẫu câu (không LLM) |
| Q5 | Kênh Zalo OA có sẵn? | Mô phỏng gửi vào file |
| Q6 | Giá thuê bao mục tiêu (9–18 triệu/năm)? | Giữ giả định hiện tại |
| Q7 | Cho phép fine-tune Chronos? | Chỉ zero-shot |
| Q8 | Chọn nền tảng triển khai (Windows/Linux, cloud)? | Docker local |

## 8.5 Điều kiện hoàn thành toàn bộ ("sản phẩm hoàn hảo")

1. **Dữ liệu**: ≥24 thế giới tổng hợp (đa dạng) + 12 hard-case + ≥5 nguồn thật có kết quả; mọi thế giới qua `validate_world`; C2ST AUC báo cáo; marginal Atradius ± 3 điểm.
2. **Mô hình**: G1–G18 đã đo theo giao thức mới; không chỉ số nào chỉ có "bảng cũ"; CI bootstrap theo công ty.
3. **Hệ thống**: T0→T10 chạy đầu-cuối từ dữ liệu thô (XML + sao kê) trong ≤5 phút/DN; UI/API/cảnh báo; MLOps cơ bản.
4. **Kiểm thử**: ≥100 ca đơn vị/thuộc tính; hồi quy chỉ số; kiểm thử hiệu năng; kiểm thử bảo mật cơ bản.
5. **Kinh tế**: `roi_calc.py` cập nhật bằng số đo thật từ pilot (hoặc nêu rõ vẫn là giả định).
6. **Tài liệu**: mọi bảng kết quả trong docs sinh từ CSV; "kết quả xấu" có mục riêng.
