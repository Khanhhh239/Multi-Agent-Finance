# Xử lý nguồn nhiễu và cộng điểm — đợt 2

Chọn trong bốn cấu hình A5 trên validation 0,3%, lưu cấu hình trước khi đánh giá test; chấm lại 300.000 quan sát, không ML.
E3/B5/E4 là kiểm tra master; C1/A5/B3 là ngữ cảnh cần bằng chứng giao dịch đủ ngưỡng để góp điểm. Hit chẩn đoán vẫn được lưu, không được coi 0 điểm là predicate đúng 100%.

## Hàng đợi test tại ngưỡng 7

| Tỷ lệ | TP trước → sau | FP trước → sau | Precision trước → sau |
| --- | ---: | ---: | ---: |
| 0.1% | 22 → 22 | 889 → 447 | 2.41% → 4.69% |
| 0.3% | 67 → 67 | 900 → 458 | 6.93% → 12.76% |
| 0.5% | 114 → 109 | 890 → 446 | 11.35% → 19.64% |

## Rule — test 0,3%

| Rule | FP góp điểm trước → sau | Ứng viên sau | Tín hiệu chưa loại |
| --- | ---: | ---: | ---: |
| E3 | 12625 → 0 | 0 | 0 |
| C1 | 10372 → 199 | 10403 | 10403 |
| A1 | 392 → 385 | 414 | 393 |
| A2 | 144 → 144 | 154 | 147 |
| A5 | 931 → 0 | 12 | 12 |
| B3 | 15 → 0 | 51 | 51 |
| B5 | 1144 → 0 | 1154 | 1154 |
| E4 | 1144 → 0 | 1154 | 1154 |

## Phát hiện đúng bị ảnh hưởng

Mọi TP mất khỏi hàng đợi có ID/family/variant/luật cũ trong lost_true_detections.csv từng bộ. Một số tín hiệu yếu còn trong rule_hits nhưng không đủ bằng chứng độc lập để mở hồ sơ.
Đây là đánh đổi được báo cáo, chưa đủ để nghiệm thu trên SME thật. Không thay threshold theo test hoặc sửa master gốc để làm đẹp precision.

## Master và hồ sơ chưa đủ nguồn

Bộ 0,3%: 2043 tên giả lập không đủ dùng cho so khớp; 222 cụm master riêng. B5/E4 cùng evidence, không nhân đôi bằng chứng.
Đã rà 15 hồ sơ B3 trước đó mang nhãn new_legitimate_vendor; chi tiết ở sme_fraud_003/b3_review.csv. Thiếu nguồn loại chứng từ được ghi needs_typed_fulfilment_evidence, không tự xem là đã xác minh hợp lệ.
540 cặp tên hư cấu độc lập gồm biến thể cố ý, tên gần giống hợp lệ và tên độc lập cùng loại hình pháp nhân: name_challenge.csv. Nhãn gần giống/same_entity khác nhãn gian lận; fuzzy match không tự gộp hai pháp nhân.

## Tái lập và nguồn mới

Cấu hình đã chọn: amount_baseline=log_mad, robust_z=3.5.
Validation selection có số liệu từng cấu hình và positive control. comparison.json chứa ba kỳ và TP/FP góp điểm so với tín hiệu chưa loại.
Thiết kế, nguồn lịch ca/chứng từ và kiểm thử: [báo cáo triển khai](../../rule_repairs_phase2.md).

```powershell
python -m sme_fraud.run_noise_reduction --output reports/rule_repairs/phase2_new
python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase2 --database .runtime/review/phase2.sqlite3 --port 8767
```

UI cũ/snapshot trước và phản hồi người dùng được giữ nguyên; lệnh trên đọc hàng đợi mới.