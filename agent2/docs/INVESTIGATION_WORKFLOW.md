# Hàng đợi và điều tra giao dịch

Mở Portal → Agent2. Màn hình mặc định là **Hàng đợi & điều tra**. Dữ liệu đầu vào được nhập tại sảnh chung; màn hình này đọc snapshot và kết quả pipeline đã lưu, không tự chấm lại hay huấn luyện.

## Cách sử dụng

1. Chọn doanh nghiệp được cấp quyền. Mặc định mở lần phân tích gần nhất có vụ đã tiếp nhận; có thể chọn lần khác trong **Nguồn kết quả**. Các điểm thô khác lần chạy/phiên bản không được trộn để xếp hạng chung.
2. Chọn dòng giao dịch để đọc giải thích, rồi bấm **Mở điều tra**. Điểm là điểm giao dịch đã lưu, không tự đổi sang thang 100 hoặc xác suất gian lận. Thiếu điểm được ghi là chưa khả dụng.
3. Trong **Quan hệ**, bấm một nút để mở rộng các đối tượng kề nó. Bấm đường nối hoặc chọn liên kết trong khung bên phải để đọc căn cứ. Có tìm kiếm, phóng to, thu nhỏ và thu gọn sơ đồ. Mã nút gồm doanh nghiệp, snapshot, loại nguồn và định danh; tên trùng không làm gộp người.
4. **Giao dịch liên quan** mở các bản ghi cùng thành phần quan hệ. Đây là thông tin phục vụ điều tra, không tự thêm ứng viên hay tăng điểm. **Bằng chứng** hiển thị tập căn cứ của phiếu đã khóa; thông tin giao dịch và hồ sơ nguồn có thể mở riêng.
5. Bấm **Bắt đầu rà**, nhập kết quả, giải thích, hành động và tài liệu còn thiếu. Chọn các căn cứ đã xem. Kết luận có/không có vấn đề đòi hỏi xác nhận đã đối chiếu đủ; thiếu tài liệu thì chọn **Chưa đủ căn cứ**.
6. Có thể đính kèm PDF, PNG, JPEG tối đa 2 MB, tối đa 10 tệp theo chính sách kho phiếu hiện có. Tệp được lưu tại backend, chống trùng theo nội dung và tải lại được. Tệp bổ sung chưa tự được coi là chứng từ gốc đã xác minh.
7. **Lịch sử** hiển thị các lần bắt đầu, đính kèm và lưu cùng người thao tác theo danh tính Portal, thời gian, phiên bản kết quả và nội dung đã lưu. Phiếu và kết luận được dùng chung cho các giao dịch cùng vụ.

Trạng thái **Đang kiểm tra** được lưu ở kho workflow; phiên đồng hồ còn hiệu lực được khôi phục trong cùng tab sau reload. Khi backend khởi động lại làm phiên đồng hồ hết hiệu lực, người dùng bấm bắt đầu để nhận phiên mới. Ghi chú chưa lưu được bảo vệ bằng xác nhận khi rời màn hình; chỉ kết quả đã lưu mới có trong lịch sử server.

## Dữ liệu và giới hạn

- Chỉ giao dịch thuộc vụ đã tiếp nhận trong packet được đưa vào hàng đợi này. Vụ chờ ngân sách/thiếu nguồn vẫn giữ trong kho cũ, không tự vượt gate. Người quản lý có đường dẫn **Quản lý lần phân tích** để vào tác vụ vận hành trước đây.
- Thông tin truy vết gồm snapshot, checksum, run, bundle, model artifact và feature contract nếu lần phân tích có lưu. Không suy diễn model cho kết quả cũ thiếu dấu vết.
- Đồ thị sử dụng nguồn bất biến tại doanh nghiệp và thông tin đã biết đến thời điểm giao dịch (không muộn hơn `as_of` của lần chạy). Không nối master mới vào lịch sử, không truy vấn nguồn của doanh nghiệp khác. Dữ kiện tham chiếu chưa chứng minh sai phạm; địa chỉ và tài khoản thiếu mã ngân hàng là liên kết bối cảnh.
- Hiện kết nối giao dịch–NCC/khách hàng/nhân viên/người lập/người duyệt, tài khoản, điện thoại, địa chỉ, hóa đơn, phân bổ và chứng từ nếu nguồn có. Thiếu bảng hoặc định danh thì không tự tạo dữ kiện. Các tín hiệu chia nhỏ, thanh toán trùng, phê duyệt... được trình bày từ kết quả luật đã lưu; việc mở đồ thị không chạy thêm một engine cảnh báo mới.
- Tối đa 10.000 bản ghi nguồn trong một lượt dựng đồ thị; vượt giới hạn báo rõ, không cắt ngầm. Giao diện hiển thị tối đa 80 nút ở một lượt mở rộng và có bộ đếm số nút; dữ kiện nguồn không bị xóa.
- Danh tính người rà hiện theo actor của phiên Portal. Khi Portal dùng workspace chia sẻ, lịch sử này không tự chứng minh danh tính cá nhân.
- Phần điều tra chạy tại node doanh nghiệp. Không gọi fit, không đổi thuật toán/trọng số/gate và không chuyển phép chấm cloud sang dữ liệu rõ. Các worker HE hiện có giữ nguyên phạm vi hỗ trợ.

## Kiến trúc và kiểm thử

`investigation.py` đọc observation/packet bất biến, lấy điểm giao dịch từ phân rã đã lưu, chiếu nguồn thành đồ thị và quản lý sự kiện workflow. Kết quả rà và tệp tiếp tục dùng kho `CompanyReviewStore` hiện có. Các API trong `investigation_api.py` kiểm tra quyền doanh nghiệp, ràng buộc run–giao dịch–phiếu và recheck quyền trước khi trả/lưu.

Trang `/pipeline-workspace` và trang Agent2 mặc định dùng giao diện mới. Tác vụ vận hành cũ ở `/pipeline-operations`. Phần ngoài Agent2 chỉ bổ sung allowlist đường dẫn và phục hồi ngữ cảnh khi reload Portal.

```powershell
$env:PYTHONPATH='D:\agent22\agent2;D:\agent22\agent2\tests_he;D:\agent22\agent2\tests'
.\agent2\.venv\Scripts\python.exe -X utf8 -m unittest test_investigation -q
.\agent2\.venv\Scripts\python.exe -X utf8 agent2/scripts/check_investigation_ui.py --output .runtime/investigation-check-new
```

Phép thử giao diện dùng Portal, kho và pipeline thật trong môi trường tạm, dữ liệu mô phỏng; không phải bằng chứng hiệu quả phát hiện gian lận thực tế hoặc nghiệm thu FHE mới. Bằng chứng phát triển được lưu trong `.runtime/investigation-build-20261119/`.
