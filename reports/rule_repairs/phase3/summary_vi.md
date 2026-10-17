# Thống nhất mô tả và mã rule — đợt 3

Chấm mới 300.000 dòng; giữ dữ liệu/nhãn, baseline A5 và ngưỡng 7 của đợt 2. Chính sách được ghi trước khi chấm test, không ML hoặc tối ưu theo test.

| Tỷ lệ mô phỏng | TP test trước → sau | FP test trước → sau | Precision trước → sau |
| --- | ---: | ---: | ---: |
| 0.1% | 22 → 23 | 447 → 432 | 4.69% → 5.05% |
| 0.3% | 67 → 68 | 458 → 443 | 12.76% → 13.31% |
| 0.5% | 109 → 111 | 446 → 431 | 19.64% → 20.48% |

## Rule — test 0,3%

| Rule | TP góp điểm trước → sau | FP góp điểm trước → sau | Ứng viên sau |
| --- | ---: | ---: | ---: |
| A3 | 4 → 5 | 8 → 8 | 13 |
| A4 | 6 → 4 | 470 → 287 | 291 |
| A5 | 0 → 0 | 0 → 0 | 12 |
| B1 | 3 → 3 | 0 → 0 | 3 |
| B3 | 3 → 3 | 0 → 0 | 51 |
| F1 | 5 → 0 | 15 → 0 | 20 |
| C1 | 30 → 31 | 199 → 192 | 10403 |

B1 master là chẩn đoán riêng (master_identity_findings.jsonl); F1 proxy không góp điểm. Ứng viên/chẩn đoán không đồng nghĩa gian lận hoặc predicate đã chính xác.
Nguồn mới còn trống trong dữ liệu gốc; không tự điền CCCD/mã ngân hàng/quyền lương/lịch khóa sổ. B3 là lần đầu trong lịch sử quan sát có sẵn, chưa chứng minh là lần đầu suốt đời NCC.
changed_hits.csv và lost_true_detections.csv lưu thay đổi theo ID, family, variant và hard negative ở cả ba kỳ. comparison.json chứa replay, nguồn/hash và các kiểm soát giữ nguyên.

[Chính sách, schema nguồn và đối chứng](../../rule_repairs_phase3.md). Các kết quả là một seed mô phỏng; bước tiếp theo cần nguồn nghiệp vụ và tập nghiệm thu mới có rà soát độc lập.