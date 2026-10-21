# Hồ sơ chuẩn bị pilot

Agent 1 dự báo dòng tiền 13 tuần và hỗ trợ đối soát, ưu tiên thu nợ, kịch bản căng thẳng.
Hiệu quả trên doanh nghiệp Việt Nam phải được đo trong pilot, không suy từ tổng hợp.

## Tuyển và dữ liệu

Đề xuất DN có ít nhất 10 lao động, bán chịu B2B, dùng hoá đơn điện tử và có ít nhất 12 tháng lịch sử.
Đầu vào mong muốn: XML hoá đơn, sao kê, sổ công nợ 24 tháng, lịch lương/thuế/thuê/vay,
ngưỡng số dư an toàn và thông tin đối chiếu của kế toán. Không tự liên hệ DN hoặc gửi dữ liệu ra ngoài.

## Mẫu nội dung đồng ý để chuyên gia rà soát

Ghi tên đơn vị kiểm soát/xử lý dữ liệu, người đại diện DN, mục đích thử nghiệm,
loại dữ liệu, người có quyền truy cập, thời gian lưu, nơi xử lý, thủ tục rút lại/xoá,
đầu mối xử lý sự cố và cơ chế phản hồi. Hoàn thiện văn bản theo pháp luật hiện hành
trước khi ký; đây là danh sách nội dung, chưa phải hợp đồng pháp lý được duyệt.

## Đo lường

Chạy song song 8–12 tuần; chỉ bật hiển thị khi đủ cổng; quan sát 12–24 tuần tiếp theo.
Nếu có ít nhất sáu DN, lập nhóm đối chứng theo thiết kế ở docs/03_Evaluation/02.
`analysis.py` tính K1–K9 khi có đầu vào; số thiếu giữ trống. K3 cần phân phối dự báo
đã kiểm định và chưa tự tính từ số dư quan sát. DiD có CI theo DN nhưng không tự khẳng định nhân quả.

## UAT cần người thực hiện

U1 xem tuần có rủi ro; U2 đối chiếu số dư/công nợ; U3 thử khách trễ; U4 dời chi;
U5 ghi lời hứa; U6 xem lời giải thích và phản hồi cảnh báo. Lưu người tham gia,
thời gian, kết quả và lỗi; cần ít nhất ba người. Chưa có phiên UAT người thật trong hồ sơ này.

## Dự phòng

Dữ liệu thiếu: giữ hàng chờ, đối chiếu với kế toán. Báo giả nhiều: rà soát ngưỡng
trên dữ liệu hiệu chỉnh, hạn chế tần suất. Độ phủ trôi bốn tuần: dừng dải xác suất,
chạy kịch bản tất định và huấn luyện lại. Sự cố dữ liệu: cô lập, giữ nhật ký và xử lý theo quy trình bảo mật.
