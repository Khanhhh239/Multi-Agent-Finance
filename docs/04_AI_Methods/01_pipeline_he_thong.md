# 1. Pipeline hệ thống đầu-cuối

> **Phạm vi sau gộp 06/11/2026:** Đây là kiến trúc pipeline nhị phân/T2/T6 và đề xuất vận hành gốc. Ứng viên v6/unified là các luồng nghiên cứu riêng, chưa tự thay kiến trúc dịch vụ. Phần T0 bên dưới bổ sung mô tả đã ghi ngày 25/10.

## 1.1 Sơ đồ

```
 NGUỒN                CHUẨN HOÁ (T0)            ĐẶC TRƯNG / NHÃN             MÔ HÌNH                    TỔNG HỢP & SẢN PHẨM
 ─────────────        ───────────────           ───────────────────          ─────────────              ─────────────────────
 HĐĐT XML ───────┐    lược đồ chuẩn             snapshot as-of T             T1 hazard rời rạc ──┐
 Sổ ERP/kế toán ─┼──► cổng chất lượng ───────►  (landmarking)  ───────────►  T2 cure (không trả)─┼─►  T6 Monte Carlo ─► P10/50/90, P(thiếu hụt)
 Sao kê NH ──────┤    (MST, tổng, ngày…)        + biến lịch tuần k           T3 tranh chấp/một phần┤    copula-t + ACI    │
 Lời hứa (chat) ─┘    T9 khớp sao kê  ───────►  nhãn = ngày TIỀN VỀ          T8 lời hứa ──────────┘        ▲              ▼
                      (ngày trả thật)            bị kiểm duyệt tại T          T4 doanh thu mới ───────────────┤       T10 giải thích (SHAP)
 Luật VN (T5) ───────────────────────────────────────────────────────────────► lịch chi tất định ───────────┘       + đòi nợ ưu tiên + "nếu như"
 Vĩ mô/OxCGRT ──► T7 điểm gãy  ───────────────────────────────────────────────► chế độ khủng hoảng (nới khoảng) ──► cảnh báo Zalo/app
                                                                              ▲ phản hồi: tiền về thực tế → hiệu chỉnh theo khách
```

## 1.2 Các nguyên tắc nền

### As-of snapshot (landmarking) — chống rò rỉ
Tại mỗi ngày cắt T (mặc định mỗi thứ Hai):
- **Tập mở** = hoá đơn đã lập ≤T, chưa tất toán (ngày nhãn >T), chưa xoá sổ ≤T.
- **Lịch sử khách** = hoá đơn đã tất toán ≤T *và nhìn thấy được* (`visible_from`: mô phỏng DN mới onboard chỉ có M tháng lịch sử).
- **Đặc trưng lời hứa** = lời hứa đã ghi ≤T; độ tin cậy từ các lời hứa đã đến hạn ≤T.
- **Nhãn**: `remaining = ngày tiền về − T` (vô hạn nếu không bao giờ trả); quan sát đến `label_end`: `event = remaining ≤ label_end − T`, `time_obs = min(remaining, label_end − T)`.

Hệ quả: một hoá đơn xuất hiện ở nhiều snapshot (mỗi tuần mở); chia train/test **theo ngày cắt**, hiệu chỉnh ở cửa sổ riêng, cách test ≥120 ngày để nhãn đã chín.

### Nhãn đúng
`label_col` ∈ {`paid_date_true` (ngày tiền về NH), `ledger_clear_date` (ngày ghi sổ)}. Sản phẩm dùng sao kê (T9) khi có; khi
không có, dùng *nhãn khoảng* (kế hoạch WP-1.4).

### Đặc trưng bất biến miền
Số ngày tương đối hạn; tiền chia trung vị của công ty; thống kê khách co về trung bình công ty (EB, k=4); tất cả đặc trưng
tính từ chính lịch sử của DN → mô hình dùng được cho DN mới sau vài tháng.

## 1.3 Luồng vận hành (đề xuất triển khai)

| Chu kỳ | Việc | Chi tiết |
|---|---|---|
| Liên tục | Nhập HĐĐT/sao kê | cổng chất lượng → bảng chuẩn; T9 khớp, đánh dấu khớp không chắc chắn để người duyệt |
| Hằng đêm (≤5 phút CPU/DN) | Snapshot → T1/T2/T3/T8 → T6 → T10 → cảnh báo | tiền không đổi theo giây, không cần real-time |
| Hằng tuần | Cập nhật hiệu chỉnh ACI theo tiền về thực tế; PSI `c_delay_ewm` | retrain hazard của DN nếu PSI>0,1 hoặc cov80 trượt ngoài [70,90]% 4 tuần |
| Hằng tháng | Retrain mô hình nguồn trên dữ liệu gộp đã ẩn danh (nếu có đồng ý) | ghi MLflow: dữ liệu as-of, tham số, chỉ số |
| Hằng năm / khi có văn bản mới | Cập nhật bộ quy tắc luật (T5) kèm kiểm thử | |

Điều kiện chạy: CPU (LightGBM/NumPy); chỉ Chronos (T4 tuỳ chọn) cần PyTorch — vẫn chạy CPU được (Bolt-small).

## 1.4 Vị trí của LLM
- **Được làm**: diễn đạt cảnh báo bằng tiếng Việt từ bảng số đã tính (lý do, hành động); phân tích cú pháp lời hứa từ tin nhắn
  ("khách A xin khất 5 tỷ sang 15/8") → bản ghi có cấu trúc **qua cổng phê duyệt**.
- **Không được làm**: tự sinh số; quyết định tín dụng; gửi tin cho khách hàng không có người duyệt.
- **Kiểm thử bắt buộc**: mọi con số trong văn bản LLM phải xuất hiện nguyên vẹn trong bảng tính toán (kiểm tra bằng regex).

## 1.5 Cấu trúc mã

```
agent1/calendar_vn.py            T5   | agent1/models/features.py  snapshot + nhãn
agent1/models/t1.py              T1/T2 (HazardGBM, HazardLR, QuantileLGBM, AFT, CureGBM, CQR)
agent1/models/t4_revenue.py      T4   | agent1/models/t6_cash.py   T6 (simulate, ACI)
agent1/models/t7_changepoint.py  T7   | agent1/models/t9_recon.py  T9
agent1/eval/metrics.py           đo   | scripts/run_*.py           thí nghiệm
```


<a id="t0-scope"></a>

## 1.6 T0 — phạm vi bộ nạp và cổng chất lượng ghi nhận ngày 25/10

**Mô tả đã ghi ngày 25/10/2026:** Bộ nạp đọc XML hoá đơn điện tử (phiên bản 2.0.0/2.0.1/2.1.0), bảng kế toán và sao kê; chuẩn hoá định danh, ngày, tiền trước khi chuyển cho các T sau. Với hoá đơn, `quality_gate` kiểm từng dòng bằng quy tắc, không học máy: thiếu trường bắt buộc; chữ số kiểm tra MST người bán/người mua; ngày lập không hợp lệ, hạn trước ngày lập; `tiền trước thuế + VAT ≠ tổng tiền` (dung sai 1.000đ); thuế suất ngoài tập cho phép; tiền không dương; trùng bộ `(MST người bán, ký hiệu, số hoá đơn)`; tiền tệ không hỗ trợ. Kết quả là bảng cờ lỗi theo dòng để chặn hoặc yêu cầu sửa đầu vào. XML còn bị giới hạn kích thước và chặn DTD/thực thể; thông tin hoá đơn thay thế/điều chỉnh được đọc ra, nhưng chuỗi tham chiếu chưa được kiểm tra đầy đủ.
