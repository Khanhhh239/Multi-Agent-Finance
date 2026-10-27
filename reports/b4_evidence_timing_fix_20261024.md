# Sửa B4 dùng xác nhận giao nhận biết muộn — 24/10/2026

**Đã sửa R01 trong mã nguồn:** nhánh B4 dự phòng không còn dùng xác nhận giao nhận biết sau ngày ghi sổ để giảm điểm cảnh báo lịch sử. Ca giao dịch ngày 12/08/2025, chứng từ biết ngày 14/08/2025 nay giữ **3 → 3 điểm B4**, thay cho **3 → 0** trước sửa.

Tại [rules.py](../sme_fraud/rules.py), B4 chỉ áp dụng miễn giảm theo cờ `goods_receipt_verified` khi `support_docs_observed_at <= posted_at` của chính giao dịch đang chấm. Thêm dữ kiện muộn hoặc thêm giao dịch sau đó không sửa lại kết quả B4 của giao dịch trước. Nhánh trạng thái rủi ro đã có tại ngày hóa đơn và nhánh danh sách thuế riêng vẫn được kiểm tra độc lập.

| Tình huống xác nhận giao nhận | Điểm B4 sau sửa |
|---|---:|
| Biết trước lúc ghi sổ, cờ đã xác nhận | 0 |
| Biết đúng lúc ghi sổ, cờ đã xác nhận | 0 |
| Biết muộn 1 giây, cờ đã xác nhận | 3 |
| Giao dịch 12/08, biết chứng từ 14/08 | 3 |
| Chứng từ đã biết nhưng chưa xác nhận giao nhận | 3 |
| NCC đã rủi ro tại ngày hóa đơn hoặc khớp danh sách thuế riêng; có xác nhận giao nhận | 10 |

[Bằng chứng tái hiện sau sửa](b4_evidence_timing_fix_20261024/reproduction_after.json) lưu mốc thời gian và toàn bộ hit B4. Bằng chứng trước sửa vẫn được giữ tại [rà soát 23/10](deep_rules_ml_audit_20261023/edge_probes.json). Các số trên là đóng góp B4; không phải tổng điểm hồ sơ hoặc kết luận gian lận.

Đã thêm [9 kiểm thử hồi quy](../tests/test_b4_evidence_timing.py), bao gồm hai chế độ policy, ranh giới thời gian, tính bất biến của cảnh báo lịch sử và hai nhánh B4 không được miễn giảm bởi giao nhận. Trước sửa có **5 lỗi assertion/subtest**, không có lỗi chạy; sau sửa cả **127 kiểm thử thuộc 7 module đều đạt**, không lỗi và không bỏ qua. [Kết quả trước sửa](b4_evidence_timing_fix_20261024/pre_fix.json), [kết quả sau sửa](b4_evidence_timing_fix_20261024/post_fix.json), [log sau sửa](b4_evidence_timing_fix_20261024/post_fix.log).

Các module đã chạy: `test_b4_evidence_timing` (9), `test_tax_risk` (12), `test_rule_repairs` (24), `test_noise_policy` (17), `test_spec_policy` (26), `test_exception_validation` (27), `test_rules` (12). Đây là hồi quy cho bản sửa B4; không phải chạy lại toàn bộ 669 kiểm thử của lượt rà soát trước.

**Giới hạn dữ liệu cũ:** nếu hoàn toàn không có cột `support_docs_observed_at`, engine giữ quy ước legacy rằng cờ giao nhận đã có tại `posted_at`. Không thể suy ra ngày biết thực tế từ một cờ cuối kỳ. Nguồn mới cần cung cấp ngày biết chứng từ chính xác để chặn đầy đủ tình huống biết muộn. Nếu đã có cột nhưng giá trị rỗng hoặc sai định dạng, bộ kiểm tra đầu vào từ chối; không tự coi chứng từ đã biết. Bản sửa này chưa thay cờ legacy bằng một quy trình xác minh chứng từ mới.

[Kiểm tra bảo toàn](b4_evidence_timing_fix_20261024/verification.json) xác nhận **2.273 tệp đã khóa không đổi checksum**. Chỉ `sme_fraud/rules.py` thay đổi trong mã hiện có; thêm một tệp test mới. Feature contract ML giữ nguyên fingerprint `b7426e60ce2fee4f1fc7afac1d2ab2cb13072a6f02a0bf7595a1d69134e4bee1`. Không huấn luyện lại model, không chấm lại nguồn/holdout hoặc ghi đè hàng đợi, báo cáo shadow và phiếu rà đã khóa.

Bản sửa áp dụng cho lượt chạy engine mới. Các kết quả và phiên bản ứng dụng đang chạy đã nạp mã cũ cần được cập nhật bằng quy trình chạy/phát hành tương ứng; lượt này chưa phát hành lại app hay tái tạo kết quả đã chốt. R02/B2, M01–M03 và RR09 trong báo cáo rà soát trước vẫn là các hạng mục riêng chưa được đóng bằng bản sửa B4 này.
