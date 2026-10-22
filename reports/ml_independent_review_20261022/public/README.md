# Hướng dẫn rà độc lập

Đây là bộ nguồn **mô phỏng**, không phải chứng từ SME thật. Chỉ giao thư mục public hoặc reviewer_packet.zip cho người rà. Các nhóm lựa chọn đã được trộn, không được cung cấp điểm mô hình, nhánh hoặc thứ hạng.

1. Mở REVIEW_INDEX.md rồi phiếu và evidence.json của từng mã. Chỉ dùng nguồn đã đóng băng tại cutoff; các cờ evidence_on_file không thay cho scan chứng từ gốc.
2. Điền primary_reviews.csv: condition_present/actionable là true, false hoặc unknown; document_request_needed là true/false. Có tài liệu thiếu phải ghi missing_evidence. Hành động hữu ích phải cụ thể, có căn cứ vượt ngoài yêu cầu tài liệu chung; không phải nhãn gian lận. actionable=true cần business_action. Thiếu căn cứ thì unknown, không tự biến thành false.
3. Ghi rationale và evidence_refs (tên các bảng trong evidence.json, cách nhau bằng dấu chấm phẩy). timing_method là measured_stopwatch hoặc measured_interval, không chấp nhận estimated. Ghi active_review_minutes đo thực tế, không dùng ước lượng mô phỏng. Với measured_interval, started_at/finished_at phải có múi giờ và paused_minutes; phút active phải khớp thời gian đã trừ nghỉ. Với đồng hồ bấm giờ có thể để cặp timestamp trống. Phút phân xử được ghi riêng theo cùng nguyên tắc.
4. Ghi primary_reviewer_id, reviewed_at và xác nhận independent_of_development=true, blind_to_arm_and_score=true chỉ khi đúng thực tế. Người đã phát triển/chọn model hoặc đã thấy nhánh/điểm của mẫu không ký như reviewer độc lập/mù.
5. Người phân xử khác người rà chính điền adjudications.csv, không xem nhánh/điểm. adjudication_status là confirmed/revised/unresolved. Mỗi kết luận cần căn cứ, phút phân xử thực tế, adjudicator_id và adjudicated_at. Chưa phân xử thì để trống, không sao chép máy móc kết luận.

Không điền 0 vào phút để thay cho thiếu dữ liệu. Không điền ký tên thay người khác. Mẫu đang thiếu tài liệu hoặc unresolved được báo riêng. Nguồn mô phỏng có review người thật vẫn chưa đóng cổng hiệu quả trên SME thật.
