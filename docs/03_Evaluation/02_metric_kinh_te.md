# 2. Chỉ số kinh tế và kinh doanh

Chuyển chỉ số kỹ thuật thành **tiền** và **hành vi người dùng**. Công thức dùng cho SME mẫu ở file 06.

## 2.1 Chỉ số tiền của doanh nghiệp khách hàng

| Mã | Chỉ số | Công thức | Trước → Sau kỳ vọng | Cách đo ở pilot |
|---|---|---|---|---|
| K1 | **Trễ bình quân theo giá trị** (ngày) | `Σ (số tiền × max(0, ngày trả − hạn)) / Σ số tiền` hoá đơn bán chịu | 11,7 → 9,7 | Từ sao kê, hằng tháng |
| K2 | **Vốn lưu động khách giữ hộ** | `doanh thu bán chịu/ngày × K1` | 0,83 → 0,69 tỷ | tính từ K1 |
| K3 | **Đệm tiền mặt tối thiểu duy trì** | `P10 của số dư thấp nhất 13 tuần tới` hoặc "ngày chi bảo đảm" | 27 → 21,6 ngày chi | so với đệm DN tự đặt |
| K4 | **Số sự kiện thiếu hụt khẩn cấp / năm** | số lần số dư <ngưỡng an toàn hoặc phải vay nóng | 2 → 0,6 | nhật ký DN + sao kê |
| K5 | **Chi phí tài chính do thiếu hụt** | lãi vay nóng + phí + phạt chậm nộp + mất chiết khấu NCC | 35 → 17 triệu/năm (chưa tính rủi ro đuôi) | kế toán |
| K6 | **Nợ xấu** (% doanh số bán chịu) | `xoá sổ / doanh số bán chịu` | 3,0% → 2,7% | sổ |
| K7 | **Giờ công kế toán cho dự báo + đối chiếu** | giờ/tháng | 47 → 17 | khảo sát/log |
| K8 | **Tỷ lệ khớp sổ – sao kê tự động** | HĐ khớp tự động / tổng HĐ có thanh toán | ~0 → ≥60% (hiện F1 0,69) | hệ thống |
| K9 | **Chi phí cơ hội của tiền nhàn rỗi** | `(đệm − đệm tối ưu) × lãi suất` | — | |

## 2.2 Chỉ số tác động sản phẩm (người dùng thật)

| Mã | Chỉ số | Mục tiêu năm 1 | Ghi chú |
|---|---|---|---|
| P1 | Tỷ lệ kích hoạt (hoàn tất onboarding ≤3 ngày) | ≥70% | cần kết nối HĐĐT + sao kê |
| P2 | Mở app/tuần (WAU/MAU) | ≥60% | H4 |
| P3 | Cảnh báo được hành động (nhấn "đã xử lý" / có thay đổi chi-thu) | ≥40% | tránh mệt mỏi cảnh báo |
| P4 | Tỷ lệ báo giả bị đánh dấu | ≤30% | phản hồi 1 chạm |
| P5 | Điểm tin cậy dự báo tự đánh giá (1–5) | ≥4 | khảo sát hằng quý |
| P6 | NPS | ≥30 | |
| P7 | Giữ chân (churn tháng) | ≤2% | |

## 2.3 Chỉ số đối với chủ sản phẩm

| Mã | Chỉ số | Công thức |
|---|---|---|
| F1 | Giá trị tạo ra / giá | `lợi ích khách hàng ròng / giá thuê bao` |
| F2 | Biên gộp | `(doanh thu − chi phí vận hành biến đổi) / doanh thu` |
| F3 | CAC, payback | qua kênh đối tác |
| F4 | Chi phí mỗi dự báo | CPU-giây × giá + token LLM |
| F5 | Độ chính xác theo chi phí | cải thiện WAPE trên mỗi 1.000đ hạ tầng |

## 2.4 Chỉ số kinh tế của mô hình (chuyển đổi trực tiếp từ kỹ thuật)

| Quan hệ | Cách chuyển |
|---|---|
| Giảm WAPE dòng thu 4 tuần → giảm đệm | Đệm cần ≈ `z·σ_sai_số_thu 4 tuần`; σ giảm θ% ⇒ đệm giảm ≤θ% (chặn trên). Ở file 06 dùng 20% (thận trọng so với −63% WAPE vì sai số số dư còn gồm chi và nợ xấu) |
| Tăng độ phủ khoảng → giảm báo giả/trượt | Mỗi 1 điểm phần trăm cov80 sai lệch ≈ nhiều/ít cảnh báo; giá trị nằm ở Brier của P(thiếu hụt) |
| Lead time ≥4 tuần → chi phí vay kế hoạch | chi phí khẩn ≈ 4× chi phí kế hoạch (giả định, file 06) |
| P(nợ xấu) tốt → giảm tổn thất | chỉ khi DN hành động (ngừng giao, đòi sớm); phần lớn giá trị ở chính sách chứ không ở mô hình |

## 2.5 Thiết kế đo "trước/sau" ở pilot

1. **Chạy song song 8–12 tuần không can thiệp (baseline thật)**: ghi K1–K9 theo cách DN làm hiện tại.
2. **Bật sản phẩm**: 12–24 tuần; ghi cùng chỉ số.
3. **Đối chứng**: nếu ≥6 DN, chia ngẫu nhiên 3 dùng, 3 chưa dùng (hoặc dùng bất đối xứng theo thời gian — stepped-wedge); DiD (difference-in-differences) trên K1, K4–K6.
4. **Giữ quyền xem xét lại**: người đòi nợ có thể không làm theo → ghi "tuân thủ" để tách hiệu quả mô hình và hiệu quả hành vi.
