# Sửa rule đợt 1 — B7, E1, A2

Đã chấm lại 300.000 giao dịch bằng engine mới trên dữ liệu gốc và cấu hình/ngưỡng cũ. Không train/chấm ML.
Các rule giao dịch ngoài A2/B7/E1 giữ nguyên tập hit hoạt động. Benford được dùng lại từ baseline vì đầu vào và luật D không thay đổi.

Đối chứng: 46/51 khớp; toàn bộ đối chứng của ba rule đã sửa khớp. 
E1 nghỉ hưởng lương được bổ sung nguồn quyền chi đã duyệt trong fixture; dữ liệu gốc không có nguồn này và không được tự điền ngoại lệ.

## Hàng đợi test tại ngưỡng 7

| Tỷ lệ | Cảnh báo trước → sau | TP trước → sau | FP trước → sau | Precision trước → sau |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 911 → 911 | 22 → 22 | 889 → 889 | 2.41% → 2.41% |
| 0.3% | 967 → 967 | 67 → 67 | 900 → 900 | 6.93% → 6.93% |
| 0.5% | 1004 → 1004 | 114 → 114 | 890 → 890 | 11.35% → 11.35% |

## Từng rule — test 0,3%

| Rule | Hit trước → sau | TP trước → sau | FP trước → sau | Hit bỏ / thêm |
| --- | ---: | ---: | ---: | ---: |
| A2 | 151 → 147 | 3 → 3 | 148 → 144 | 4 / 0 |
| B7 | 0 → 0 | 0 → 0 | 0 → 0 | 0 / 0 |
| E1 | 4 → 4 | 4 → 4 | 0 → 0 | 0 / 0 |

TP/FP theo nhãn ý đồ gian lận tổng hợp; chưa phải nhãn độc lập cho mọi vi phạm rule hoặc hiệu quả trên SME thật.
E1/B7 có thể không thay đổi số liệu nền vì dữ liệu gốc không cài những trường hợp đã tái hiện; fixture và kiểm thử thời gian là bằng chứng sửa logic.
Số liệu train/validation/test và hard negatives ở comparison.json từng bộ; changed_hits.csv liệt kê mọi hit thay đổi.

## Đối chứng còn lệch, ngoài phạm vi đợt 1

- A3_short_branch: Hai NCC chung SĐT, hai khoản 9 triệu/3 ngày theo nhánh A1
- A4_month_boundary: Ba khoản qua hai tháng lịch; không tháng nào đủ ba
- A5_low_tail: Khoản tròn thấp hơn baseline trên 2 sigma theo độ lệch tuyệt đối
- B1_rent: Chi thuê NCC có TK trùng nhân viên, kiểm tra master theo mô tả
- B3_prior_purchase: NCC mới đã có giao dịch mua hàng trước khoản chi lớn

## Nguồn và cách chạy

Chi tiết logic, nguồn HR/hợp đồng và kiểm thử ở [báo cáo triển khai](../../rule_repairs_phase1.md).
Baseline [Rule Audit](../../rule_audit/summary_vi.md) được giữ nguyên để đối chiếu. Các báo cáo cũ thể hiện phiên bản trước khi sửa.

```powershell
python -m sme_fraud.run_rule_repairs --output reports/rule_repairs/phase1_new
```

CLI không ghi đè dữ liệu/báo cáo đã có và không thay đổi features.csv hoặc model cũ.

Các snapshot mới có rule_scores, rule_hits, case_queue và case_events để dùng trong UI. 
```powershell
python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase1 --database .runtime/review/phase1.sqlite3 --port 8766
```

Lệnh này mở hàng đợi mới trên cổng riêng; phản hồi của snapshot cũ giữ tại nguồn cũ.
