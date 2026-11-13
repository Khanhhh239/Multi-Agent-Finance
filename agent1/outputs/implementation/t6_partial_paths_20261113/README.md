# Bằng chứng hoàn thiện T6 ngày 13/11/2026

`checks_summary.json` tổng hợp 389 ca Python duy nhất: 386 đạt, 3 bỏ qua,
không còn ca lỗi. 28 ca UI đạt; Ruff E9/F không báo lỗi trên các file đã sửa.
XML chạy rộng giữ cả hai ca lỗi ban đầu; các XML sau chứng minh đã sửa và
chạy lại. `summarize_checks.py` hợp nhất theo danh tính ca, không đếm lặp.

`fresh_synthetic_final/` là lượt tích hợp dùng mã cuối cùng. Protocol khóa
catalog, source, dataset, policy và luật cảnh báo. Tất cả dự báo của cả hai
ledger được lưu trước khi chấm. CLI `evaluate_t6_new_company.py score` đã
chạy và lưu `summary.json`, với trọng số bằng nhau giữa doanh nghiệp.

Hai ledger toy tạo trong phiên làm việc này không phải doanh nghiệp thật.
Các lượt `fresh_synthetic/` và `fresh_synthetic_verified/` là bằng chứng
trung gian đã được xem. Payload trung gian đã dọn ngày 14/11; chỉ giữ
`protocol.json` khóa cấu hình/seed của từng lượt. Dữ liệu và dự báo đầy đủ
còn ở `fresh_synthetic_final/`. Lượt final dùng lại cùng ca sau kiểm tra
ổn định số học và sửa nhãn diễn giải; không gọi đó là holdout mới.

Rà soát 14/11: `source_signature` hiện tại khác phiên bản khóa trong protocol
final. Các file mã được tính hash không thuộc danh sách dọn output. Giữ
nguyên protocol/hash lịch sử; cần đúng source/runtime đã khóa để phát lại
lượt này, hoặc dùng output mới khi kiểm phiên bản hiện tại. Việc kiểm hash
dữ liệu/dự báo đã lưu không thay thế kiểm tương thích engine.

Cả hai ca giữ bundle global vì một cửa sổ validation chưa đủ nhãn được xác
nhận ở đúng thời điểm lịch sử. Coverage raw lần lượt 3/13 và 10/13 tuần;
không nghiệm thu chất lượng dải tiền hoặc hiệu quả thích nghi từ kết quả
này. Không kích hoạt model tenant, không cài scheduler và không đổi gate.

Hợp đồng đầy đủ:
[T6 partial và vận hành](../../../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md).
