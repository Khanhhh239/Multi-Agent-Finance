# Rà sơ bộ 128 phiếu — 23/10/2026

Đã hoàn tất **128/128 lượt rà của trợ lý**, có căn cứ nguồn, hành động đề xuất và danh sách tài liệu cần bổ sung cho từng cutoff. Người dùng xác nhận chưa phân công người rà độc lập và người phân xử. Kết luận độc lập đã xác thực: **0/128**; phút rà/phân xử thực tế của con người: **chưa có**, giữ null.

| Kết quả sơ bộ của trợ lý | Lượt rà theo cutoff | Phạm vi nguồn phân biệt |
|---|---:|---:|
| Có vấn đề nguồn, đề xuất hành động cụ thể | 5 | 4 |
| Chưa đủ căn cứ, giữ unknown | 60 | 40 |
| Chưa nhận diện hành động có căn cứ từ nguồn | 63 | 55 |
| Tổng | 128 | 99 |

Phạm vi được nhận diện bằng công ty, source_object và danh sách transaction_id chính xác. Có 29 phạm vi xuất hiện ở hai cutoff. Không coi các phạm vi còn lại là độc lập về thống kê. false chỉ có nghĩa chưa tìm được hành động cụ thể từ nguồn hiện có; unknown không được tính như kết quả âm tính. Các đề xuất chưa phải hành động hữu ích được xác nhận, nhãn gian lận hoặc nhãn huấn luyện.

**Bốn phạm vi cần ưu tiên xác minh độc lập:**

- [Phiếu 11](ml_assistant_review_20261023/cases/DRV_c20d6c4e9e02a032.md): regular_salary 11.349.000 đồng cho kỳ phục vụ sau ngày nghỉ việc. Đối chiếu HR/payroll và căn cứ hưởng, kiểm soát trả lương tiếp theo.
- [Phiếu 77](ml_assistant_review_20261023/cases/DRV_5d2babd8bdb7459c.md): maker action trong kỳ nghỉ được duyệt, gắn khoản chi 223.162.000 đồng. Xác minh phiên/người dùng, bảo toàn log và cấp độc lập xác nhận lệnh chi.
- [Phiếu 87](ml_assistant_review_20261023/cases/DRV_90c2fa90d0aa1c14.md) và [101](ml_assistant_review_20261023/cases/DRV_f6ea8280a2c025a5.md): cùng maker action trong kỳ nghỉ, khoản 4.361.000 đồng; xử lý như một sự kiện tại hai cutoff.
- [Phiếu 109](ml_assistant_review_20261023/cases/DRV_a4c6997fbddfe12c.md): số dư phải thu 51.541.192 đồng sau phân bổ đã xác minh, có độ phủ sổ thu đến cuối kỳ và chưa có giải thích trong gói. Mở theo dõi thu hồi/đối chiếu khách hàng; chưa kết luận mất khả năng thu.

**Khoảng trống tài liệu:** 65 phiếu có yêu cầu bổ sung có mục tiêu. Các nhóm chính là phiếu chi/người nhận và thẩm quyền/ngoại lệ; giao nhận/nghiệm thu; bảng tính trích trước, hoàn nhập và chi tiết 335; sổ thu/phân bổ và độ phủ; hiệu lực hủy nghỉ/log phiên; hợp đồng tái tuyển và cách tính kỳ lương. [Danh sách yêu cầu theo từng phiếu](ml_assistant_review_20261023/DOCUMENT_REQUESTS.md).

Các bằng chứng giải thích đã được xét riêng: quan hệ nhà cung cấp khai báo từ trước; override được chính sách cho phép; công nợ đã thu đủ; backpay phục vụ trước ngày nghỉ; và sự kiện tái tuyển. Khoản tái tuyển có kỳ phục vụ bao gồm khoảng chưa làm việc vẫn giữ unknown để đối chiếu cách tính. Bút toán cân bằng hoặc evidence_on_file=1 không thay cho chứng từ gốc.

Thẩm quyền được kiểm tra nhất quán cho cả khoản tiền mặt và nghiệp vụ khác. Bốn phiếu 13, 17, 34, 37 đã được hiệu chỉnh từ “chưa nhận diện” sang unknown khi đối chiếu hạn mức approver master với phạm vi chính sách còn thiếu; giữ đầy đủ dấu vết trước/sau trong revisions.json và revision_history. Không tự coi trường hạn mức giao dịch là ma trận thẩm quyền đã xác minh.

**Thời gian:** 11 batch có tổng **19.0173 phút trôi qua được ghi timestamp**. Đây là thời gian trợ lý/công cụ/chuẩn bị trong các interval đã ghi, không phải phút active của người rà, không chia đều cho từng phiếu và không gồm toàn bộ chuẩn bị/kiểm tra/báo cáo ngoài các batch. Phút human review và adjudication vẫn null. Chi phí mô phỏng 20/30 phút không được đưa vào kết quả thời gian thực.

**Kiểm tra:** 22 kiểm thử đạt; 128 phiếu gắn đúng công ty, cutoff và hash evidence; mọi JSON pointer trỏ được về nguồn; các biểu mẫu người rà còn nguyên và trống; 1830 file nguồn/kết quả đã đóng băng giữ nguyên SHA256. Model, hàng đợi, split thời gian và nhãn sản xuất không thay đổi. Không đọc nhãn/oracle/holdout, không chấm lại train/calibration, không mở mapping nhóm mẫu để lập kết quả theo nhánh. Trợ lý đã tham gia phát triển và biết ngữ cảnh tổng hợp nên không ký xác nhận độc lập/mù.

[Mở danh sách đủ 128 phiếu](ml_assistant_review_20261023/CASE_INDEX.md) · [Kết quả có cấu trúc](ml_assistant_review_20261023/assistant_assessments.json) · [Trạng thái và kiểm tra](ml_assistant_review_20261023/summary.json).

Bước còn lại để có bằng chứng so sánh ML: phân công một người rà chính và một người phân xử khác, độc lập với phát triển; giao [gói public nguyên bản](ml_if_discovery_review_20261022/public/README.md), chốt nhận định của họ trước khi đối chiếu đề xuất trợ lý, đo thời gian active thực tế trên biểu mẫu gốc. Sau khi có kết quả được phân xử mới mở mapping để so sánh các nhánh cùng ngân sách. Hiện actionable_gain, precision và recall giữ null; chưa có cơ sở kết luận IF cải thiện hiệu quả.
