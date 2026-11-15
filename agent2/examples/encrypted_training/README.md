# Prototype train có nhãn trên bản mã

Đã có [adapter đọc snapshot nghiệp vụ](../../docs/HE_TRAINING_SNAPSHOT_ADAPTER.md).
Dùng `preview-snapshot` rồi `prepare-snapshot` để lấy đúng hai feature 0/1 từ
snapshot đã commit, thay vì tự điền ma trận. Cần chọn rõ bốn giao dịch/revision;
không dùng lại preview khi thay nguồn, thời gian hoặc mapping.

Mục tiêu nhãn được người dùng chốt: **gian lận đã xác minh / đã xác minh không
gian lận**. `confirmed_risk`, `legitimate` hoặc `inconclusive` của phiếu rà cũ
không tự trở thành nhãn train. Doanh nghiệp phải xác minh nhãn một cách tường minh.

`dataset.synthetic.json` chỉ là ma trận mô phỏng 4 dòng x 2 biến, mỗi giá trị
trong `{-1,0,1}`. Đây chưa phải bản xuất 33 feature của pipeline tài chính.

Để thử sáu bước bằng HE thật, dùng `scripts/demo_encrypted_training.py` theo
[hướng dẫn](../../docs/HE_SUPERVISED_TRAINING.md). Demo tự tạo nhãn ở chế độ
`synthetic_expected`; không ghi nhận ai đã xác minh gian lận thực tế.

Với thao tác thủ công, cấu hình operator riêng từ `config.example.json` và
chạy `review-template` **sau upload**. Template được ràng buộc đúng tenant,
doanh nghiệp, mã dataset và checksum biên nhận. Điền từng dòng:

- `outcome`: `verified_fraud` hoặc `verified_non_fraud`.
- `verified_by`: người được cấp quyền xác minh, khớp actor hiện hành trong prototype.
- `verified_at`: thời điểm xác minh có múi giờ.
- `evidence_refs`: mã căn cứ đã kiểm tra, không để rỗng.

Template khởi tạo `outcome=null`, không tự xác nhận. Thiếu nhãn, sai dataset,
thiếu căn cứ hoặc chỉ có một lớp thì chưa cho train. Prototype cố định 4 dòng;
muốn thay tập dòng/nhãn đã xác nhận phải tạo phiên mới, giữ nguyên phiên cũ.

Khóa bí mật, dữ liệu, nhãn và model giải mã chỉ lưu trong thư mục doanh nghiệp.
Không đưa thư mục runtime hoặc config operator lên Git.
