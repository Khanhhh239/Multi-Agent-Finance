# ML — kiểm tra sẵn sàng cho pilot, 19/10/2026

**Mục ML vẫn chưa thể nghiệm thu lợi ích vận hành.** Workspace chưa có nguồn SME thật hoặc phiếu đánh giá độc lập tương ứng. Đợt này đã kiểm tra tương thích model/cache và chuẩn bị phép so sánh; chưa triển khai runner suy luận shadow cho nguồn thật, chưa train/chấm model mới hoặc thay hàng đợi.

**Kết quả kiểm tra chỉ đọc**

| Model hiện có | Cache đem đối chiếu | Kết quả |
|---|---|---|
| IF 001 của đợt đồng bộ 17/10 | feature_model_sync_20261017 / 001 | Tương thích hợp đồng; checksum feature đúng |
| IF 001 của đợt đồng bộ 17/10 | synthetic_sources_20261017_v2 / 001 | Cache đúng hợp đồng nhưng model bị từ chối do dataset_format_version_mismatch |
| IF 003 của đợt đồng bộ 17/10 | feature_model_sync_20261017 / 003 | Tương thích hợp đồng; checksum feature đúng |
| IF 003 của đợt đồng bộ 17/10 | synthetic_sources_20261017_v2 / 003 | Cache đúng hợp đồng nhưng model bị từ chối do dataset_format_version_mismatch |

Cả hai loại cache có 190 đặc trưng. Model khai báo định dạng `2.1-feature-sync`; nguồn mới khai báo `synthetic-source-world-v1`. Trùng số cột không cấp quyền bỏ qua ràng buộc phiên bản. Kết quả từ chối chỉ nói về hợp đồng tương thích, không đo được mức giảm/tăng độ chính xác hoặc chứng minh model sẽ hoạt động kém. Không đổi metadata của model để ép nhận nguồn mới.

Đã nạp 2 model do workspace tạo để đọc metadata/kiểm tra hợp đồng. **0 model được fit, 0 dòng được chấm**. Không đọc nội dung nhãn/oracle; 005 chỉ kiểm tra hash trong danh sách bảo toàn. 1.209 tệp nguồn/kết quả và 10 tệp model/manifest/feature liên quan giữ nguyên hash. [Kết quả máy đọc](ml_pilot_readiness_20261019/compatibility_audit.json).

`evaluate.py` hiện phục vụ benchmark có tập test và nhãn mô phỏng; `sync_feature_model.py` phục vụ lượt đồng bộ train/validation với đầu vào đã định trước. Không dùng trực tiếp các lệnh đó như một API suy luận nguồn SME chưa có nhãn. Luồng pilot sau này cần riêng phần dựng feature đúng thời điểm, kiểm tra hợp đồng, suy luận và xuất điểm ở output mới; không gọi fit trên cửa sổ đánh giá và không tự cập nhật journal/hàng đợi.

**Phép so sánh đã chuẩn bị, chưa phê duyệt/chạy**

1. Chọn một SME và quy trình có nguồn kiểm chứng, xác nhận coverage, mapping và các cửa sổ train/calibration/đánh giá. Model/cache mới phải có provenance phù hợp và được kiểm tra tương thích.
2. Khóa baseline rules + graph + A5 hiện hành, cùng phạm vi hồ sơ, cutoff từng ngày, ngân sách lượt/phút, chính sách tồn đọng và suất bắt buộc. Ngân sách chính 5 hoặc 10 hồ sơ/ngày phải được chọn trước khi xem kết quả.
3. Chạy ML riêng ở chế độ quan sát. Đề xuất ban đầu giữ các suất bắt buộc của baseline; trong các suất còn lại, dùng IF đổi thứ tự hồ sơ giao dịch trong cùng mức ưu tiên. Các loại hồ sơ khác giữ baseline và báo độ phủ riêng. Chưa mở hồ sơ mới chỉ do ML.
4. Khóa dự đoán, phiên bản model/nguồn/policy và scope trước khi phát phiếu. Kế toán độc lập rà hợp của hai tập chọn và mẫu tham chiếu ngẫu nhiên được định trước; phiếu không lộ nhánh chọn, điểm ML hoặc thứ hạng. Người khác phân xử; chưa đủ chứng từ vẫn là chưa kết luận.
5. So sánh số hồ sơ có hành động hữu ích, thời gian thực tế, hồ sơ bị đẩy chậm, tồn đọng và tỷ lệ thiếu tài liệu trên cùng ngân sách. Báo riêng chi phí lấy mẫu tham chiếu/phân xử. Chỉ chuyển ML vào vận hành khi đạt tiêu chí đã được chủ nghiệp vụ duyệt trên giai đoạn giữ kín; nếu không đạt thì giữ baseline.

Các trường doanh nghiệp, thời gian, ngân sách chính, người rà, tiêu chí lợi ích và phê duyệt hiện để trống. Chưa có kết quả pilot, không gán giá trị giả hoặc dùng nhận xét của trợ lý làm nhãn thật.

- [Protocol máy đọc — bản nháp](ml_pilot_readiness_20261019/comparison_protocol.draft.json): mô tả phép thử, không phải runtime config.
- [Phiếu duyệt thiết kế](ml_pilot_readiness_20261019/protocol_review.md): cần chủ nghiệp vụ chốt trước khi chạy.
- [Mẫu review độc lập](ml_pilot_readiness_20261019/independent_review_template.json): 0 dòng kết luận, không chứa điểm/thứ hạng/nhánh dự đoán.
- [Biên bản kiểm tra và hash](ml_pilot_readiness_20261019/verification.json).

Điểm Isolation Forest biểu diễn mức bất thường; chưa có cơ sở diễn giải thành xác suất gian lận. Tham khảo [tài liệu anomaly detection của scikit-learn](https://scikit-learn.org/stable/modules/outlier_detection.html). Việc tách dữ liệu và chỉ fit trên train nhằm tránh ước lượng quá lạc quan do thông tin đánh giá lọt vào huấn luyện; xem [hướng dẫn data leakage](https://scikit-learn.org/stable/common_pitfalls.html).

Trong phạm vi thử đầu tiên chỉ đổi thứ tự các hồ sơ đã có, không tuyên bố ML tìm thêm gian lận ngoài quần thể đó. “Có ích để rà”, “điều kiện rule đúng”, “nghi vấn” và “gian lận đã kết luận” là những kết quả khác nhau. Chưa có thiết kế nhãn phù hợp thì không báo precision/recall gian lận thực địa.

**Việc tiếp theo:** lấy nguồn thật và người rà độc lập, duyệt thiết kế, rồi mới xây/kết nối runner score-only cho phạm vi đã chọn. Có thể kiểm thử kỹ thuật runner bằng mô phỏng khi triển khai, nhưng điều đó không đóng cổng nghiệm thu lợi ích vận hành. Hiện trạng vẫn `awaiting_real_data`.
