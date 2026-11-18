# Xử lý vụ trên màn hình chính Agent2

Mở Agent2 từ Portal → **Vụ cần rà** → chọn doanh nghiệp và lần phân tích → mở
một vụ. Kết quả rà, chứng từ và công việc được xử lý ngay tại đây, cùng nguồn
`snapshot_id`, `run_id`, `bundle_id`. Không cần chuyển sang màn hình cũ.

## Cách thực hiện

1. **Đối chiếu và ghi kết quả rà.** Đọc câu hỏi, lý do, dữ liệu nguồn và giới hạn.
   Bấm **Bắt đầu rà**, chọn kết quả, ghi giải thích/căn cứ/hành động rồi lưu.
   Chưa đủ tài liệu thì chọn **Chưa đủ căn cứ**.
2. **Bổ sung chứng từ.** Chọn loại tài liệu, chọn PDF/PNG/JPEG tối đa 2 MB, ghi
   chú và bấm **Lưu chứng từ**. Tài liệu mới ở trạng thái **Đã nhận, chờ xác minh**.
   Muốn thay bản cũ, chọn đúng tài liệu trong mục **Tệp mới hay phiên bản bổ sung?**.
   Mỗi bản có checksum và vẫn tải lại được; bản mới không kế thừa xác minh của bản cũ.
3. **Giao việc.** Nhập nội dung cần thực hiện, lý do, bộ phận và hạn xử lý theo giờ
   Việt Nam rồi bấm **Giao việc**. Không tự điền hạn xử lý hoặc một checklist chung.
4. **Người phụ trách gửi kết quả.** Trong thẻ công việc, ghi kết quả thực hiện,
   chọn chứng từ đã dùng; đánh dấu còn chờ bên ngoài nếu cần và bấm
   **Gửi kết quả thực hiện**. Có thể mở phần đổi bộ phận/hạn để phân công lại,
   kèm lý do.
5. **Người có quyền xác minh đối chiếu tài liệu.** Tải đúng phiên bản, kiểm tra
   với nguồn/chứng từ thực tế, ghi căn cứ rồi chọn **Xác minh đạt** hoặc
   **Từ chối chứng từ**. Nút luôn ghi rõ phiên bản đang được xác minh.
6. **Xác nhận công việc.** Đọc kết quả đã gửi và các mục còn thiếu. Chỉ khi đủ
   điều kiện mới mở **Xác nhận hoàn tất**. Ghi căn cứ quyết định; hoặc chọn
   **Yêu cầu làm lại**. Với việc đã đóng, ghi lý do rồi chọn **Mở lại công việc**.
   Sau làm lại/mở lại, phải có kết quả thực hiện mới trước khi hoàn tất tiếp.
7. **Xem lại và báo cáo.** Reload vẫn thấy chứng từ, các phiên bản, công việc
   và lịch sử. Báo cáo JSON chứa metadata chứng từ/công việc; CSV có mã và trạng
   thái. Các số tổng trên màn hình tách kết quả rà, việc đang mở và chứng từ.

Tệp đính kèm từ phiếu cũ vẫn tải được. Để đưa vào quy trình xác minh mới, chọn
tệp đó ở **Nguồn tệp**, khai rõ loại chứng từ và lưu. Tệp cũ không tự thành
chứng từ đã xác minh.

## Quyền và dữ liệu

- Quyền `data.import`: bổ sung chứng từ, giao/đổi phân công, gửi kết quả thực hiện.
- Quyền `evidence.verify`: xác minh tài liệu, xác nhận hoàn tất, yêu cầu làm lại,
  mở lại. Vai trò Giám đốc đơn lẻ không thay thế quyền này.
- Backend kiểm tra quyền hiện hành, doanh nghiệp, lượt chạy, vụ và phiên bản
  công việc; client không tự khai nguồn hoặc nâng quyền. Hai người cùng sửa
  một công việc sẽ được yêu cầu tải lại nếu phiên bản đã thay đổi.
- Portal đang dùng danh tính workspace; phân công bộ phận không có nghĩa đã
  xác minh danh tính từng cá nhân.
- Hoàn tất việc không tự đóng vụ hoặc tạo nhãn gian lận. Chứng từ bổ sung sau
  phân tích không sửa snapshot/feature/điểm cũ. Dữ liệu thử nghiệm vẫn là mô phỏng.

## Mất kết nối hoặc mất phản hồi

Bấm **Tiếp tục yêu cầu đã gửi** để dùng lại đúng mã và nội dung; server lưu
thao tác cùng biên nhận trong một transaction. Không đổi thành thao tác mới
chỉ vì mất phản hồi. Nếu đã reload sau khi tải tệp, chọn lại đúng tệp ở ô khôi
phục; checksum phải khớp trước khi gửi tiếp. Nội dung tệp không lưu vào
sessionStorage. Trình duyệt khác vẫn đọc được trạng thái đã lưu trên server.

## Thành phần và kiểm thử

- Adapter: `sme_fraud/bundle_remediation.py` nối dữ liệu immutable bundle với
  `RemediationStore` hiện có; không tạo kho task thứ hai.
- API:
  `/api/v1/companies/{company}/pipeline-workspace/runs/{run}/reviews/{review}/remediation`;
  GET đọc hồ sơ, POST lệnh có `action`, `request_id`, `payload`.
  Tải đúng phiên bản tại `/documents/{document_id}/versions/{version}`.
- Giao diện: `web/bundle-workspace.*` và `web/bundle-remediation.*`.
- Backend: `tests_he/test_bundle_remediation.py`, `test_bundle_workspace.py`,
  `test_remediation.py`. Browser: `scripts/check_bundle_workspace_ui.py`.
- Chạy trong môi trường kiểm thử cô lập; việc nạp vào Portal đang chạy vẫn cần
  quy trình phát hành/backup của dự án. Không đổi quyền live để cho demo đi qua.

Ảnh nghiệm thu: [máy tính](../../Agent2_Spec_v2_1/evidence/R4/bundle_case_workspace_20261118/desktop.png),
[điện thoại](../../Agent2_Spec_v2_1/evidence/R4/bundle_case_workspace_20261118/mobile.png).
