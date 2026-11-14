# Kinh tế học dòng tiền doanh nghiệp bán chịu

## Dồn tích và tiền mặt

Doanh thu ghi trên sổ và tiền đã nhận là hai đại lượng khác nhau. Ví dụ một lô hàng bán chịu 2 tỷ đồng, kỳ hạn 60 ngày, tạo khoản phải thu trong khi lương, thuê và các khoản chi khác vẫn đến hạn. Lợi nhuận dương chưa bảo đảm đủ tiền trả nghĩa vụ.

```text
Số dư cuối = số dư đầu + tiền thu − tiền chi
```

Trong Workspace, tiền thu gồm công nợ mở và các dòng hoạt động được bật, đủ điều kiện ước lượng. Tiền chi gồm nghĩa vụ T5 còn phải trả và chi hoạt động bổ sung nếu đủ lịch sử. Vì vậy phải đọc số dư cùng phạm vi tài khoản và phạm vi chi; hóa đơn chưa tất toán vẫn có thể phát sinh nhiều lần thu một phần.

## Vốn lưu động và chu kỳ chuyển đổi tiền

```text
CCC = DSO + DIO − DPO
Vốn phải thu xấp xỉ = doanh thu bán chịu mỗi ngày × DSO
```

DSO là số ngày phải thu, DIO là số ngày tồn kho và DPO là số ngày phải trả. Kỳ hạn hợp đồng khác thời gian tiền thực về. DSO tính từ báo cáo tài chính cũng khác thời gian trả của từng hóa đơn; không hoán đổi hai cách đo khi hiệu chỉnh dữ liệu.

Ví dụ giả định doanh thu 40 tỷ đồng/năm, 65% bán chịu: doanh thu bán chịu mỗi ngày khoảng 71 triệu đồng. Nếu toàn bộ dòng bán chịu chậm thêm 30 ngày, vốn bị giữ thêm khoảng 2,1 tỷ đồng. Nếu chỉ 39% giá trị chậm thêm 30 ngày thì ước lượng còn khoảng 0,83 tỷ đồng. Đây là minh họa độ nhạy, không phải tác động đã đo của sản phẩm.

## Rủi ro cần mô hình hóa

| Rủi ro | Hệ quả đối với dự báo |
|---|---|
| Thời điểm thanh toán | Dùng ngày đến hạn làm ngày nhận tiền có thể dự báo thừa tiền |
| Tương quan giữa khách | Nhiều khách cùng chậm có thể tạo thiếu hụt lớn hơn giả định độc lập |
| Thu một phần hoặc không thu đủ | Xác suất tất toán không thể thay trực tiếp cho tỷ lệ tiền thu |
| Tập trung khách hàng | Một khách lớn có thể chi phối khả năng thanh khoản |
| Quan sát và ghi sổ | Ngày ghi nhận, ngày giao dịch và ngày biết thông tin có thể khác nhau |
| Phạm vi thu chi chưa đủ | Số dư trong phạm vi dữ liệu không đại diện toàn bộ thanh khoản doanh nghiệp |

Đệm tiền mặt mỏng, ít khách lớn và thiếu nhân sự tài chính chuyên trách là các giả thuyết giải thích vì sao SME cần dự báo. Nguồn tham chiếu về đệm tiền nằm ở [danh mục dữ liệu](../02_Data/08_tai_lieu_tham_khao.md); không suy thống kê nước ngoài thành phân phối của SME Việt Nam.

## Giá trị đến từ quyết định

| Quyết định | Dự báo hỗ trợ |
|---|---|
| Giữ tiền đệm | Xem dải số dư và nguy cơ dưới ngưỡng |
| Chuẩn bị vốn | Nhận biết tuần cần chú ý để chủ động kiểm tra phương án |
| Liên hệ khách | Xem dư nợ, thứ tự ưu tiên và lý do của chính sách đang chọn |
| Điều chỉnh kế hoạch | Thử khách trả chậm hoặc dời khoản chi trong mô phỏng |

Thứ tự ưu tiên hiện tại chưa tối ưu hóa mức giảm xác suất thiếu tiền trên mỗi cuộc gọi. Kịch bản đổi giả định chưa chứng minh liên hệ khách tạo ra tác động tương ứng. Công thức đo chi phí và ROI nằm ở [giá trị kinh tế](../03_Evaluation/02_metric_kinh_te.md).
