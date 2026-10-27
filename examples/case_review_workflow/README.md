# Rà hồ sơ và yêu cầu bổ sung tài liệu

Đã triển khai ngày 19/10/2026 cho web cục bộ. Quy tắc, trọng số, chính sách tiếp nhận và ngưỡng A5 giữ nguyên. [Biên bản kỹ thuật và các phần còn chờ](../../docs/reports/app/step2_review_20261019.md).

## Thử bản demo riêng

```powershell
python -B .runtime/step2_review_20261019/demo.py --serve
```

Mở [Case Management](http://127.0.0.1:8769/) hoặc [32 đối chứng P2](http://127.0.0.1:8769/p2-controls). Demo dùng nguồn 001/003 chỉ đọc, bản sao báo cáo và SQLite tại `.runtime/step2_review_20261019/`; không dùng 005. Thông báo ở chế độ `dry_run`.

Ba yêu cầu mẫu do trợ lý tạo trên bản sao có tên `SIM_*`, không đại diện người phụ trách thật, tài liệu thật hay nghiệm thu kế toán. Không có kết luận nghiệp vụ nào được tự tạo. Có thể mở nhanh:

- [003: yêu cầu đang chờ tài liệu](http://127.0.0.1:8769/#scenario=003&case=IR_c39bd6eef7d31a7c).
- [001: đã nhận, chờ rà lại](http://127.0.0.1:8769/#scenario=001&case=IR_30749635120c8936).
- [003: lịch sử nhận và rà lại, còn chờ người dùng kết luận](http://127.0.0.1:8769/#scenario=003&case=RC_d3c7009ff2ea6dbf).

## Luồng thực hiện

1. Đọc **Tổng quan/Bằng chứng**: căn cứ vào hàng đợi, điểm nền/lặp lại trong snapshot, các nguồn độc lập, ngưỡng A5 và trạng thái thiếu mẫu. Với P2, đối chiếu khoản chi, tổng hóa đơn, mốc đối chiếu và hạn mức đã xác minh đúng thời điểm.
2. Mở **Bổ sung tài liệu**. Nhập tài liệu cần lấy, người phụ trách, hạn tương lai theo giờ Việt Nam, người thực hiện và lý do. Hạn/tuổi yêu cầu dùng đồng hồ vận hành; ngày giao dịch mô phỏng không thành quá hạn bổ sung hôm nay.
3. Ghi **Đã nhận tài liệu** cùng 1–20 mã tham chiếu. Đây là ghi nhận của người dùng, chưa tải file hay xác minh nội dung và chưa chấm lại detector.
4. Đọc tài liệu rồi chọn **Đã rà lại tài liệu**, hoặc **Cần bổ sung tiếp**. Có thể đổi người/hạn, hoặc hủy yêu cầu có lý do. Nhật ký cũ luôn được giữ.
5. Khi mọi yêu cầu hiện hành đã rà lại/hủy, lưu kết luận với người rà và lý do. Nếu còn thiếu, dùng **Cần bổ sung bằng chứng**; không diễn giải thiếu mẫu, nhận tài liệu hoặc không có P2 là nghiệp vụ hợp lệ.

Các thao tác vẫn chịu ngân sách tiếp nhận hồ sơ hiện tại. Tạo yêu cầu/đổi người/hạn/nhận/rà tài liệu không tăng điểm hoặc tự đóng hồ sơ. Hạn quá hạn chỉ hiển thị nhắc việc; chưa có chính sách tự đổi thứ tự rủi ro hoặc gửi nhắc việc ra ngoài. Muốn mở lại hồ sơ đã kết luận, người dùng ghi quyết định cần bổ sung có lý do trước.

Yêu cầu gắn với công ty, kịch bản và hash phạm vi/bằng chứng hồ sơ. Yêu cầu của phạm vi cũ chỉ đọc, không tự áp sang phạm vi mới; hồ sơ tương đương chính xác có thể giữ lịch sử theo cơ chế định danh hiện có. API từ chối phiên bản ghi cũ và bảo vệ Host/Origin/CSRF. Tên người dùng là nội dung nhập trên web cục bộ, chưa phải danh tính được xác thực qua hệ thống đăng nhập.

## Thời điểm biết hóa đơn

Nguồn mới có thể cung cấp `invoice_versions.csv`, một dòng cho mỗi phiên bản; dùng [hợp đồng trường](../../sme_fraud/invoice_versions.schema.json) và [ví dụ mô phỏng](../invoice_versions.review_only.json). Cần `company_id`, `invoice_id`, `revision_id`, `observed_at` có múi giờ, `evidence_id`. `issued_at` là thời điểm phát hành; `source_updated_at` là lúc cập nhật tại nguồn; `observed_at` là lúc phiên bản được hệ thống biết. Không lấy ngày phát hành làm ngày đã nhận.

Đây là bảng bằng chứng tùy chọn cho UI, chưa phải importer xác minh nguồn hay đầu vào mới của detector. Kiểm tra schema, thứ tự và mã phiên bản tại bước nghiệm thu nguồn. UI đánh dấu dòng thiếu mốc biết/mã và phiên bản đồng thời cần xác minh; không dùng dữ kiện biết sau để sửa hit quá khứ. Bộ 001/003/P2 đã khóa chưa có bảng này và vẫn hiển thị phần chưa đủ lịch sử. Ví dụ phiên bản không được ghép vào nguồn cũ để giả lập bằng chứng đã có.

## Lưu trữ và phạm vi bảo vệ

- Kết luận tiếp tục ở `feedback_audit.jsonl` của thư mục báo cáo, cùng cơ chế hiện có.
- Yêu cầu tài liệu nằm ở bảng `information_request_events` trong SQLite của ReviewStore, có chuỗi hash và kiểm tra phiên bản trước khi ghi. Làm mới cache không xóa bảng này. Cần sao lưu SQLite bằng cơ chế backup nhất quán của SQLite cùng báo cáo/định danh nguồn; đừng xóa database như cache dùng một lần.
- Web, `ReviewStore.save_feedback` và CLI/API `record_feedback` nay dùng [cổng kết luận chung](../review_decision_gate/README.md). Thư mục báo cáo gắn với SQLite có thẩm quyền; thiếu/sai DB không được xem là không có yêu cầu tài liệu. [Sao lưu/khôi phục](../review_backup/README.md) bảo toàn và di chuyển liên kết này cùng lịch sử.
- Tham chiếu hoàn/đảo có thể nối thành chuỗi cùng công ty. UI cho đối chiếu dòng liên quan, phân biệt đảo sổ với nhận lại tiền; hit gốc, điểm và thành viên hồ sơ được giữ nguyên. Muốn detector đánh giá dữ kiện mới cần quy trình nguồn/snapshot mới.

Các file nên đọc theo luồng: [API](../../sme_fraud/review_server.py), [ReviewStore](../../sme_fraud/review_store.py), [nhật ký yêu cầu](../../sme_fraud/information_requests.py), [chiếu bằng chứng nguồn](../../sme_fraud/review_support.py), [giải thích chung](../../review_ui/review_explanations.js), [web hồ sơ](../../review_ui/app.js), [web đối chứng](../../review_ui/p2_controls.js).
