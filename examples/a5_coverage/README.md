# A5: độ phủ theo giao dịch

Đo tại `posted_at`, dùng lịch sử có cả ngày nghiệp vụ và thời điểm được biết **trước** giao dịch. Không thay P99, cửa sổ 90 ngày, tối thiểu 20 mẫu hay chính sách chu kỳ.

Các mẫu số được xuất riêng:

- Toàn bộ giao dịch: gồm cả nghiệp vụ ngoài phạm vi A5.
- Giao dịch có nguồn (`eligible`): có phép đo chi phí đã ghi sổ; nếu không có, dùng chi tiền VND đã xác minh. Giữ nguyên thứ tự chọn nguồn của A5.
- Giao dịch đủ lịch sử (`ready`): ít nhất một phép đo được chọn có ngưỡng. `fully_ready` yêu cầu tất cả phép đo đủ mẫu; `partial_history` vẫn còn tài khoản thiếu mẫu.
- Điều kiện A5 (`a5_gate`): bút toán tài chính, số tiền giao dịch chia hết cho 1.000. Báo cáo cả độ phủ trong nhóm này.

`insufficient_history` là có nguồn nhưng chưa đủ mẫu. `not_observed_at_cutoff` là nguồn chưa được biết lúc ghi sổ. `not_applicable` là không có nguồn phù hợp. Các trạng thái này và không có hit đều không phải kết luận giao dịch hợp lệ. Thiếu mẫu chu kỳ có thể dùng ngưỡng toàn bộ ngày nếu ngưỡng đó đủ mẫu; xem `phase`.

Chạy đo và đối chứng A5 cũ `log_mad` với cùng cấu hình hiện tại, vào **thư mục mới**:

```powershell
python -B -m sme_fraud.run_a5_coverage --output reports/a5_coverage_NEW
```

Runner chỉ chấm reporting 001/003, không đọc nhãn/oracle. 005 chỉ được băm tệp. Kiểm tra hit, điểm và hàng đợi hiện tại trùng snapshot đã khóa trước khi xuất bản đo. Các hồ sơ đối chứng chỉ thay `amount_baseline`; không dùng chênh lệch giữa hai chính sách P2 để quy kết cho A5.

Kết quả chính: `a5_coverage.json` (toàn bộ/công ty/tháng và phép đo theo tài khoản), `a5_evaluations.csv` (một dòng/giao dịch), `a5_evaluations.jsonl` (mọi phép đo của giao dịch), `a5_hit_review.csv`, `a5_added_hit_cases.csv`, `a5_baseline_comparison.json`. Đây là số liệu hành vi bộ phát hiện, chưa phải precision hoặc tỷ lệ cảnh báo sai.

Xem UI bằng snapshot có bản đo, database riêng:

```powershell
python -B -m sme_fraud.review_server --data-root data/synthetic_sources_20261017_v2 --reports-root reports/a5_coverage_20261018_v2 --database .runtime/a5_coverage_20261018/web.sqlite3 --port 8766
```

Mở `http://127.0.0.1:8766`: nút **Phạm vi quy tắc** hiển thị độ phủ với tử số/mẫu số; hồ sơ và chi tiết nghiệp vụ hiển thị số mẫu, phạm vi tài khoản và trạng thái thiếu mẫu. Snapshot cũ hiển thị chưa có bản đo. Snapshot mới không sao chép kết luận cũ; runner không gửi thông báo.

Lần chạy chuẩn: [báo cáo](../../docs/reports/rules/a5_coverage_20261018.md).
