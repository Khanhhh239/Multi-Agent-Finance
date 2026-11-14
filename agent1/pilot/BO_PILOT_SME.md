# Bộ chạy pilot Agent1 · dành cho kế toán và người điều phối

**Bộ biểu mẫu chuẩn bị, chưa nghiệm thu pilot thật.** Công cụ đóng gói tạo phiếu quan sát và sổ dự báo trống trong ZIP. Hai hóa đơn ví dụ bên dưới chỉ kiểm tra thao tác. Không dùng kết quả từ dữ liệu mẫu để chọn mô hình hay công bố lợi ích.

## Trước buổi đầu

Người phụ trách DN điền phạm vi vào [biên bản](quyet_dinh.md): đơn vị tiền VND, tài khoản nào nằm trong số dư, tiền mặt có nằm ngoài phạm vi không, ngày chốt, mức tiền tối thiểu, ngày kết thúc lưu dữ liệu. Đối chiếu [nội dung bảo vệ dữ liệu](../docs/06_Pilot/02_CAM_KET_BAO_MAT.md) với người có thẩm quyền trước khi nhận file. Chỉ dùng mã khách, mã chứng từ và bí danh tài khoản. Không đưa tên người mua, số tài khoản thật, token hoặc sao kê vào Git. Dùng một bộ thư mục dữ liệu và khóa riêng cho mỗi DN.

Kế toán xuất CSV UTF-8 hoặc XLSX. Mỗi dòng cần mã ổn định để nạp tháng sau. Chọn đúng sheet, dạng ngày và dấu phân cách số. Thứ tự: **hóa đơn → dòng sao kê → thanh toán đã phân bổ → kỳ sao kê → lịch chi → nhật ký thu nợ**. Ghi ngày hệ thống thực sự biết từng khoản trong cột `known_at`. Bắt đầu từ nút tải mẫu cho từng bảng trong trang Dữ liệu. Nếu chỉ có hóa đơn/lịch chi vẫn xem được dự báo theo phạm vi đó; chưa thể chấm sai số số dư thực.

## Tự diễn tập trước khi mời đối tác

Từ gốc repository, chạy `.\agent1\scripts\start-business.ps1 -Port 8012 -Company DIENTAP` rồi mở `http://127.0.0.1:8012/workspace`. Chuẩn bị môi trường theo [README Agent 1](../README.md) trước. Khóa riêng của DIENTAP nằm ở đường dẫn mà lệnh in ra. Có thể dùng gói diễn tập đã đóng lại từ nguồn hiện tại; giải nén và mở BAT_DAU.txt. Hướng dẫn thao tác chung nằm trong [sổ tay](../docs/06_Pilot/SO_TAY_AGENT1.md).

Dùng workspace thử riêng. Thư mục [fixtures](fixtures) có hai hóa đơn DEMO_30 và DEMO_70, một khoản thu DEMO_BANK100, hai kỳ số dư và lịch lương. Chọn ngày dd/mm/yyyy, số Việt Nam. Nạp lần lượt hóa đơn, sao kê, kỳ số dư, lịch chi. Ở trang Dữ liệu, ghép DEMO_BANK100 với DEMO_30 bằng mã P30, số tiền 30000000, sau đó P70 và 70000000. Kiểm tra số treo 100 → 70 → 0 triệu; gửi lại P30 không tăng tiền. Bài fixture tham chiếu số dư đầu 20 triệu ở 30/09/2026. Chỉ dự báo nếu bundle thực dùng hợp lệ tại cutoff này; nếu bị chặn do ngày sẵn sàng thì dùng ca mới với cutoff/dữ liệu/số dư đồng bộ, không lùi ngày artifact. Chỉ xác nhận lịch chi tuần đã kiểm tra. Với ca fixture gốc, đối chiếu đến 31/10/2026 có số dư thực cuối tuần đầu 120 triệu; đây là đáp án kế toán, không là đáp án dự báo của engine mới. Chênh lệch với lịch chi giả định là điều kế toán cần giải thích. Không kích hoạt huấn luyện từ mẫu DEMO. Để thử file lỗi, làm việc trên một bản sao và đổi ngày lập sang 31/02/2026.

## Phiên có người quan sát (A04)

Mời 5 kế toán, có người mới và người nạp kỳ kế tiếp. Dùng hồ sơ thử riêng. Người điều phối đọc yêu cầu, không chỉ vị trí nút; nếu phải hướng dẫn, ghi đúng bước. Mỗi người một mã P01–P05. Không ghi màn hình khi chưa có đồng ý cụ thể.

| Bài giao cho kế toán | Bằng chứng để người quan sát chấm |
|---|---|
| Nạp file có một ngày sai định dạng; sửa rồi nạp lại | Tìm đúng dòng, sửa đúng ngày, tự lưu được; ghi số lần thử và giây thực hiện |
| Khoản thu 100 triệu trả hai hóa đơn 30 và 70 triệu | Số thu ngân hàng giữ 100; sau ghép lần đầu còn treo 70; sau lần hai còn 0; nhập lại cùng mã không tăng tiền |
| Chốt sổ khi lịch lương mới có tới tuần 2 | Tự chỉ ra tuần chưa biết; phân biệt với tuần đã xác nhận chi bằng 0 |
| Đọc cảnh báo khi vẫn còn tiền kỳ vọng | Nêu tuần, mức tối thiểu, xác suất và một khoản cần xác minh; không coi xác suất là cam kết |
| Nạp tháng hai; tìm lại dự báo cũ và thử kịch bản | Tìm đúng phiên bản và số dư đầu, giải thích chênh lệch bằng VND; bản gốc vẫn mở lại được |

Ghi phiếu quan sát ở kho thử riêng ngay sau mỗi bài, gồm mã người tham gia, bài giao, thời gian, số lần thử, bước cần trợ giúp, kết quả và phản hồi. Thành công nếu **≥4/5** tự sửa và nạp xong, **5/5** nhận ra tuần thiếu lịch chi. Người không hoàn tất vẫn nằm trong mẫu số. Ghi phản hồi nguyên ý, không ghi tên. Không đạt: sửa bước gây lỗi rồi thử lại với người khác.

## Chạy song song với sổ thực (A12)

1. Chốt cùng tài khoản, ngày, số dư đầu kỳ, danh sách khoản đã biết và lịch chi. Chọn trước mốc so sánh (ví dụ kế hoạch tiền tuần kế toán đang dùng), ngưỡng cảnh báo, khoảng thời gian và mức sai số DN chấp nhận. Không đổi sau khi thấy kết quả.
2. Cuối mỗi kỳ, **trước khi biết tiền về**, lưu dự báo trên web; ghi ID, hash, ngày tạo, mức sàn và số phút thao tác vào sổ theo dõi ở kho riêng. Khóa bản kế hoạch đối chứng cùng ngày. Một dự báo lập lại sau khi biết kết quả chỉ là hồi cứu.
3. Nạp sao kê và số dư kỳ đến sau. Mở lại đúng kế hoạch, chọn ngày đối chiếu. Lưu số tuần đủ dữ liệu, MAE thu/chi/số dư, độ phủ và độ rộng P10–P90, cảnh báo giả/bỏ sót và thời gian báo trước. Mỗi kế hoạch 13 tuần cần tới 13 tuần sau để chấm đủ. Kỳ không có sao kê để trống và ghi lý do.
4. Theo từng DN, báo riêng tuần 1–4 và 5–13; ghi số lượt dùng, phút kế toán so với mốc, chi phí máy, các lần cần trợ giúp. So sánh trên đúng những tuần cả hai phương án đều quan sát được. Không cộng nhiều dự báo trùng một tuần thành nhiều sự cố độc lập.
5. Đối với danh sách thu nợ: chốt số lượt liên hệ trước khi xem kết quả; ghi số khoản còn cần xử lý, số kiểm tra và giá trị tiền. Không quy tiền về là nhờ gọi điện khi chưa có đối chứng. Hoàn tất [biên bản quyết định](quyet_dinh.md).

Nếu số dư không khớp hoặc nhập nhầm DN: dừng dùng kế hoạch, kiểm tra tài khoản, ngày ghi nhận và giao dịch trùng. Không tự gửi nhắc nợ hay tự chuyển tiền. Khi kết thúc, người phụ trách xử lý bản lưu và khóa theo đúng thời hạn đã ký.


## Ghi nhận mốc trước pilot

Chốt trong [biên bản](quyet_dinh.md) mã DN, ngày được phép dùng dữ liệu, ngành/quy mô, tỷ lệ bán chịu, số tháng lịch sử và phạm vi tài khoản. Ghi cách lập kế hoạch hiện tại, mức sàn do DN chọn, các sự cố thiếu tiền/vay khẩn cấp, lãi/phí/phạt thực trả và thời gian kế toán kèm nguồn xác nhận. Số thiếu để trống; không gán chi phí chuẩn. Các chỉ số K1–K9 chỉ tính khi đủ đầu vào theo [metric kinh tế](../docs/03_Evaluation/02_metric_kinh_te.md).

Không coi lịch chạy song song cố định là đã đủ nghiệm thu: mỗi origin cần thực tế trưởng thành, các origin chồng lấn không độc lập, và hiệu chỉnh dải có điều kiện riêng theo [T6](../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md). Bài năm kế toán ở trên là tiêu chí UAT đề xuất, chưa là kết quả đã đạt.
