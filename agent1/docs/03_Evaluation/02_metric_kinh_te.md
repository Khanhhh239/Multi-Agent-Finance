# Giá trị sử dụng, chi phí và ROI

Tài liệu giữ công thức đo và giả thuyết kinh tế; các bảng giá, nhân sự, doanh thu và ROI giả định của bản kế hoạch cũ đã bỏ. Chưa có phép đo tác động sản phẩm trên doanh nghiệp thật. Bối cảnh kinh tế ở [BA](../01_Business_Analyst/01_kinh_te_hoc_dong_tien.md), giả thuyết thương mại ở [thị trường](../01_Business_Analyst/05_thi_truong_va_canh_tranh.md).

## Đo giá trị đối với doanh nghiệp

| Chỉ số | Cách đo và giới hạn |
|---|---|
| Trễ theo giá trị | `Σ amount × max(ngày trả−hạn,0) / Σ amount`; khóa cohort/cách tính trả nhiều lần và xử lý chưa tất toán |
| Vốn phải thu | Doanh thu bán chịu/ngày × DSO theo định nghĩa nhất quán; khác tuổi từng hóa đơn |
| Đệm tiền | Số tiền/ngày chi thực duy trì và rủi ro đã chấp nhận; chưa suy từ P10 từng tuần thành đệm tối ưu |
| Sự kiện thiếu hụt | Số lần dưới ngưỡng hoặc huy động vốn khẩn, có định nghĩa/gom sự kiện cố định |
| Chi phí thiếu hụt | Chi phí vốn/phí và tổn thất thực có chứng từ, tách khỏi giả định rủi ro đuôi |
| Công sức | Thời gian nạp, đối soát, kiểm tra dự báo, xử lý cảnh báo và sửa sai |
| Chất lượng đối soát | Phân bổ đúng, phải sửa/đảo, số phút duyệt; không gọi đề xuất auto là tự ghi |
| Hiểu và sử dụng | Hoàn tất nạp, đọc đúng phạm vi/dải, quay lại theo tuần, hiểu giới hạn kịch bản |

Hàng đợi ưu tiên hiện chưa tối ưu hóa tiền thu thêm do liên hệ. Kịch bản khách chậm là độ nhạy theo mô hình, chưa là ước lượng tác động cuộc gọi. Không quy giảm sai số dự báo thành tỷ lệ giảm vốn đệm hoặc nợ xấu theo hệ số cố định.

## Công thức chi phí và lợi ích

```text
Chi phí sử dụng = phí sản phẩm + tích hợp/nạp dữ liệu + công vận hành/sửa lỗi
Lợi ích ròng = chi phí tránh được + lợi ích vốn/thu hồi thực đo − chi phí sử dụng
ROI = lợi ích ròng / chi phí sử dụng  (khi mẫu số > 0)

Chi phí phát triển = công xây dựng + hạ tầng + rà soát chuyên môn + bảo mật/hỗ trợ
Đóng góp/khách = giá thực thu − chi phí biến đổi/khách
Hòa vốn khách = chi phí cố định / đóng góp/khách  (khi đóng góp > 0)
```

Phải thống nhất khoảng thời gian, đơn vị, trước/sau thuế và chi phí vốn. Không cộng cả tiền vốn giải phóng và toàn bộ lợi ích lãi của cùng khoản vốn thành hai lợi ích độc lập. Giảm đệm và giảm phải thu có thể chồng nhau; lợi ích giấy tờ khác tiền đã thu thực tế.

Chi phí mỗi forecast cần đo CPU/RAM/lưu trữ/source snapshot/export và hỗ trợ triển khai. Luồng T10 hiện không dùng LLM; không cộng ngân sách token giả định vào OPEX mặc định. Benchmark nhỏ không bảo đảm SLA trên doanh nghiệp lớn.

`scripts/roi_calc.py` là mô hình giả định lịch sử, không là báo cáo kinh doanh hiện tại. Nếu dùng cần thay tham số có nguồn, khóa giả định, phân tích thấp/cơ sở/cao và ghi rõ chưa phải hiệu quả đã đo.

## Thiết kế đo trên doanh nghiệp thật

Khóa thời gian baseline, định nghĩa chỉ số, lịch dữ liệu và đối chứng trước khi mở outcome. Bắt đầu với dự báo song song không can thiệp để kiểm dữ liệu/chất lượng; sau khi đủ điều kiện mới thiết kế đo tác động có nhóm hoặc thời điểm đối chứng. Ghi hành động thực tế và việc người dùng không làm theo, chi phí xử lý, mùa vụ và thay đổi kinh doanh.

Công bố cả lợi ích âm/không rõ, CI và giới hạn số doanh nghiệp; không xem trước/sau đơn giản là nhân quả. Điều kiện triển khai ở [nghiệm thu](03_cong_nghiem_thu.md).
