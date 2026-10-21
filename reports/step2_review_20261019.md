# Bước 2: hoàn thiện việc rà hồ sơ — 19/10/2026

Đã triển khai RR04–RR08 và RR10 ở backend/UI, kiểm chứng kỹ thuật trên mô phỏng. Luồng: **đọc bằng chứng → yêu cầu tài liệu → ghi nhận nhận tài liệu → rà lại → kết luận có lý do**. Chưa nghiệm thu trực quan trên browser mục tiêu hoặc bởi kế toán độc lập. RR09 tiếp tục chờ chủ kiểm soát quyết định.

## Thay đổi theo yêu cầu

| Mục | Hành vi đã bổ sung | Giới hạn còn giữ rõ |
|---|---|---|
| RR04: thời điểm biết/hiệu lực | Hiển thị lúc chi, phát hành, biết/xác minh và ranh giới hiệu lực. Thêm thiết kế `invoice_versions` phân biệt lần biết đầu, phiên bản đã biết lúc chi và cập nhật sau | Không tự sửa nguồn cũ hoặc khẳng định detector đã dùng dữ liệu tương lai; “đã biết” không tự xác nhận hiệu lực chứng từ. Bảng phiên bản là chiếu bằng chứng UI, chưa thay đầu vào detector |
| RR05: trả nhiều đợt và điểm | Câu giải thích nêu khoản chi 3 triệu, hóa đơn 12 triệu, mốc trong snapshot; hiện điểm nền/lặp lại và nhóm lấy điểm cao nhất. A4 3 điểm có tuyến `split_pattern`; E2 là căn cứ độc lập ưu tiên cao nhất; dịch phép đo A5 và phân biệt trích trước với dòng chi | Số điểm do snapshot quyết định. Điểm không phải xác suất gian lận; không cộng chồng mọi hit/mọi giao dịch |
| RR06: chi gốc–hoàn–đảo | Giữ tóm tắt/liên kết P2; main Case Management nạp thêm chuỗi giao dịch hoàn/đảo liên quan cùng công ty để đối chiếu | Không đổi thành viên hồ sơ, xóa hit lịch sử, tự đóng hồ sơ hoặc tự bù trừ VAT. Đảo sổ không chứng minh thực thu tiền |
| RR07: không có P2 | Tách dưới mốc theo snapshot, qua ngân hàng và dòng thu/hoàn/đảo; dòng thu chưa nối gốc cần xác định bên nộp/lý do/chứng từ | Không tạo P2 giả; không có P2 chưa phải chứng nhận hợp lệ |
| RR08: ngoại lệ | Hiện AGR_CONTROL/hợp đồng/tổng được phép/giao dịch liên quan/bằng chứng; PAT_CONTROL/3 triệu/P99 1 triệu/22 mẫu/chu kỳ/phê duyệt/hiệu lực | Ngoại lệ A1/A5 không tự miễn P2. Nguồn biết/phê duyệt muộn chỉ được ghi làm ngữ cảnh đối chiếu |
| RR10: lấy tài liệu | Tab Bổ sung tài liệu có người phụ trách, hạn tương lai, tuổi yêu cầu, quá hạn, tham chiếu và nhật ký riêng. Trạng thái nhận → chờ rà lại; muốn kết luận cuối phải rà lại/hủy từng yêu cầu đang mở có lý do | Tuổi/hạn theo lúc tạo yêu cầu hiện tại, không theo SLA giao dịch lịch sử. Không tăng điểm do thiếu mẫu hoặc quá hạn; chưa tự đổi chính sách thứ tự hoặc gửi nhắc việc thật |

Nhật ký yêu cầu lưu bền qua restart/làm mới cache và có chuỗi hash. Mỗi cập nhật kiểm tra phạm vi hồ sơ và phiên bản sự kiện; thay phạm vi không tự kế thừa nhiệm vụ cũ. Hồ sơ lưu trữ cho đọc lịch sử, không sửa. Thao tác nhận/rà tài liệu không tự tạo kết luận “hợp lệ”. Cổng chặn kết luận áp dụng cho web/ReviewStore; CLI feedback cũ chưa tích hợp kho yêu cầu SQLite, xem hướng dẫn vận hành.

## Kiểm chứng

Kết quả kiểm thử máy đọc được: [Python](step2_review_20261019/python_tests.json), [UI](step2_review_20261019/ui_tests.json), [HTTP](step2_review_20261019/http_smoke.json), [đối chiếu hash](step2_review_20261019/verification.json).

- Toàn bộ **597 kiểm thử Python đạt**, không lỗi hoặc bỏ qua; [log](step2_review_20261019/python_tests.log).
- JavaScript: 19 kiểm tra hồi quy và 13 kiểm tra luồng mới đạt; thêm dựng 35 tab của 7 hồ sơ bằng payload API thực tế và 32 đối chứng/73 giao dịch/78 chứng từ. Kiểm tra không làm thay đổi payload.
- Backend mới kiểm tra bắt buộc người/hạn/tài liệu/lý do, hạn vận hành, restart, rà lại trước kết luận, ghi đồng thời, đổi phạm vi/công ty, chuỗi hoàn/đảo và phát hiện sửa nhật ký. API kiểm tra CSRF/Origin và asset chung.
- HTTP demo: 10 trang/asset/API trả 200, chế độ thông báo `dry_run`. Chưa kiểm tra tương tác/render trực quan bằng browser vì phiên làm việc không có browser được kết nối.
- Hash của **1.209 tệp đã khóa** không đổi; bốn module `rules.py`, `accounting.py`, `cash_controls.py`, `case_queue.py` không đổi so trước Bước 2. Không chấm lại detector; 005 chỉ băm opaque, không parse/nạp/chấm hay dùng oracle.
- Bằng chứng [HTML trước/sau](step2_review_20261019/before_after.html), [projection JSON](step2_review_20261019/ui_before_after.json). Đây là kết quả renderer, không phải ảnh browser hoặc biên bản nghiệm thu nghiệp vụ.

## Dùng thử

Mở [web hồ sơ](http://127.0.0.1:8769/) hoặc [P2](http://127.0.0.1:8769/p2-controls). Xem [hướng dẫn và ba trạng thái mẫu](../examples/case_review_workflow/README.md). Server dùng bản sao báo cáo tại `.runtime/step2_review_20261019/demo_reports`, database riêng; không ghi vào báo cáo gốc.

Ba yêu cầu mẫu được gắn `SIM_DEMO_ASSISTANT`/`SIM_OWNER_CHUA_PHAN_CONG_THAT`, tài liệu chỉ là tham chiếu mô phỏng. Không tự ghi kết luận hoặc nhận là nghiệm thu độc lập. Nhận tài liệu qua UI hiện là nhập mã tham chiếu, chưa có upload file hay xác minh nội dung. Thông báo chỉ giả lập; chưa gửi ra ngoài.

## Việc cần nghiệm thu tiếp

1. Kế toán dùng browser thử 5–10 mẫu trọng tâm: INSTALL_CASH/MIXED, RECUR_A5/CASH/GAP, REFUND_FULL/PART, REVERSAL_JOURNAL và hồ sơ A5 thiếu mẫu. Ghi rõ giải thích còn khó hiểu, tài liệu cần lấy, ai thực hiện và kết luận có căn cứ. Không dùng review của trợ lý thay người nghiệp vụ.
2. Chủ nguồn xác nhận thời điểm biết và lịch sử phiên bản ở bản xuất mới; nguồn đã khóa vẫn được giữ nguyên. Chưa có lịch sử thì tiếp tục hiển thị chưa đủ bằng chứng.
3. Chủ kiểm soát chốt riêng [RR09](ui_evidence_repairs_20261019/rr09_policy_decision.md). Trường hợp vượt 1 VND vẫn 14 điểm/ưu tiên cao; không thêm dung sai.

Trạng thái phù hợp để chuyển sang Bước 3 dùng thử với kế toán. Chưa đóng cổng nghiệm thu nghiệp vụ, nguồn thật hoặc lợi ích ML. [Backlog ngày 18/10](representative_review_20261018/backlog.json) và các đánh giá cũ được giữ làm lịch sử, không sửa thành “đạt”.
