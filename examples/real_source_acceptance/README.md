# Quy trình nghiệm thu mù trên nguồn SME thật

1. Chuẩn hóa các bảng trong `examples/phase4_sources`, thêm chúng vào bản sao dataset và cập nhật checksum trong manifest.
2. Hội đồng nghiệp vụ duyệt ngưỡng, đổi `policy_status` thành `approved`, điền người và thời gian phê duyệt.
3. Chạy `prepare` với `--criteria`. Lệnh khóa cùng lúc ngưỡng và kết quả detector, rồi tạo inventory cùng quần thể cần rà soát. `review_packet.csv` không có cột dự đoán.
4. Người rà soát chính điền kết luận điều kiện rule; người thứ hai độc lập phân xử. Hai ID phải khác nhau, mỗi kết luận phải có lý do và mã bằng chứng.
5. Chủ nguồn điền một coverage cho từng cặp công ty/rule. `source_names` nối bằng `|`, phải chứa đủ nguồn của rule; `data_origin=real_sme_export`; khoảng coverage phải bao trùm toàn cửa sổ.
6. Chạy `evaluate`. Chỉ rule có trạng thái `accepted` mới được coi là nghiệm thu.

```powershell
python -m sme_fraud.real_source_acceptance prepare --data data/sme_real_export --from 2025-01-01T00:00:00+07:00 --as-of 2025-12-31T23:59:59+07:00 --criteria reviews/acceptance_criteria.json --output reports/real_acceptance/prepared
python -m sme_fraud.real_source_acceptance evaluate --data data/sme_real_export --prepared reports/real_acceptance/prepared --reviews reviews/review_conclusions.csv --coverage reviews/coverage_attestations.csv --criteria reviews/acceptance_criteria.json --output reports/real_acceptance/result
```

`condition_present` là kết luận điều kiện predicate, không phải kết luận gian lận. Dùng `information_gap=1` và để trống `condition_present` khi hồ sơ không đủ. `blind_to_prediction=1` xác nhận người rà soát chưa xem kết quả detector. Ngưỡng mẫu trong file ví dụ chỉ là bản nháp, phải được chủ rule phê duyệt theo ngân sách và rủi ro của đơn vị.
