# Rule Audit — 31 quy tắc A–F

Audit baseline trên ba bộ v2, cùng seed, tổng 300.000 quan sát. Không train/chấm ML, không sửa luật/ngưỡng/dữ liệu.
Mỗi rule được đánh giá độc lập ở tất cả hit còn điểm sau ngoại lệ, không lấy top-75 hoặc ngưỡng tổng hợp làm hit của rule.
Bảng chính dùng **test 0,3%: 25.000 quan sát, 75 dòng gian lận**. Train/validation/test và cả ba tỷ lệ có trong CSV/JSON.

Precision dưới đây là tỷ lệ hit rơi vào dòng có ý đồ gian lận được cài. FP là hit trên dòng nhãn 0, chưa chứng minh rule sai về điều kiện nghiệp vụ.
Bao phủ kịch bản là proxy theo family/variant, không phải sensitivity của vi phạm rule được gán nhãn độc lập.

**Phạm vi:** 20 rule giao dịch đo được theo nhãn dòng, 6 rule D thiếu nhãn cấp tập, 5 rule thiếu nguồn/implementation. 
Không có rule nào được tuyên bố hoàn thiện chỉ từ một seed tổng hợp. Quyết định cho đủ 31 rule ở [rule_decisions.csv](rule_decisions.csv).

| Rule | Hit độc lập | TP | FP | Precision gian lận | FPR trong phạm vi | Bao phủ kịch bản | Ghi chú |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [A1](rules/A1.md) | 400 | 8 | 392 | 2.00% | 5.28% | 30.77% | Kịch bản là proxy |
| [A2](rules/A2.md) | 151 | 3 | 148 | 1.99% | 1.99% | 23.08% | Kịch bản là proxy |
| [A3](rules/A3.md) | 12 | 4 | 8 | 33.33% | 0.11% | 66.67% | Kịch bản là proxy |
| [A4](rules/A4.md) | 476 | 6 | 470 | 1.26% | 3.90% | 46.15% | Kịch bản là proxy |
| [A5](rules/A5.md) | 933 | 2 | 931 | 0.21% | 3.75% | N/A | Chưa có nhãn dương riêng |
| [A6](rules/A6.md) | 0 | 0 | 0 | N/A | 0.00% | N/A | Chưa có nhãn dương riêng |
| [B1](rules/B1.md) | 3 | 3 | 0 | 100.00% | 0.00% | 60.00% | Kịch bản là proxy |
| [B2](rules/B2.md) | 9 | 9 | 0 | 100.00% | 0.00% | 100.00% | Kịch bản là proxy |
| [B3](rules/B3.md) | 18 | 3 | 15 | 16.67% | 0.12% | 75.00% | Kịch bản là proxy |
| [B4](rules/B4.md) | 9 | 9 | 0 | 100.00% | 0.00% | 75.00% | Kịch bản là proxy |
| [B5](rules/B5.md) | 1154 | 10 | 1144 | 0.87% | 9.06% | 100.00% | Kịch bản là proxy |
| [B6](rules/B6.md) | 0 | 0 | 0 | N/A | 0.00% | N/A | Chưa có nhãn dương riêng |
| [B7](rules/B7.md) | 0 | 0 | 0 | N/A | 0.00% | N/A | Chưa có nhãn dương riêng |
| [C1](rules/C1.md) | 10403 | 31 | 10372 | 0.30% | 41.61% | N/A | Chưa có nhãn dương riêng |
| [C2](rules/C2.md) | 12 | 12 | 0 | 100.00% | 0.00% | 100.00% | Kịch bản là proxy |
| [C3](rules/C3.md) | 1 | 0 | 1 | 0.00% | 0.0040% | N/A | Chưa có nhãn dương riêng |
| [C4](rules/C4.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |
| [D1](rules/D1.md) | 3 cửa sổ | N/A | N/A | N/A | N/A | N/A | 30/30 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [D2](rules/D2.md) | 29 cửa sổ | N/A | N/A | N/A | N/A | N/A | 29/30 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [D3](rules/D3.md) | 0 cửa sổ | N/A | N/A | N/A | N/A | N/A | 0/360 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [D4](rules/D4.md) | 0 cửa sổ | N/A | N/A | N/A | N/A | N/A | 30/30 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [D5](rules/D5.md) | 0 cửa sổ | N/A | N/A | N/A | N/A | N/A | 30/30 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [D6](rules/D6.md) | 0 cửa sổ | N/A | N/A | N/A | N/A | N/A | 0/360 cửa sổ đủ điều kiện; thiếu nhãn cấp tập |
| [E1](rules/E1.md) | 4 | 4 | 0 | 100.00% | 0.00% | 100.00% | Kịch bản là proxy |
| [E2](rules/E2.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |
| [E3](rules/E3.md) | 12672 | 47 | 12625 | 0.37% | 100.00% | N/A | Chưa có nhãn dương riêng |
| [E4](rules/E4.md) | 1154 | 10 | 1144 | 0.87% | 9.06% | 100.00% | Kịch bản là proxy |
| [F1](rules/F1.md) | 20 | 5 | 15 | 25.00% | 1.89% | 41.67% | Kịch bản là proxy |
| [F2](rules/F2.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |
| [F3](rules/F3.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |
| [F4](rules/F4.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |

## Baseline hàng đợi tại ngưỡng nghiệp vụ 7

| Tỷ lệ gian lận mô phỏng | Cảnh báo test | TP | FP | Precision | FPR toàn tập |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.1% | 911 | 22 | 889 | 2.41% | 3.56% |
| 0.3% | 967 | 67 | 900 | 6.93% | 3.61% |
| 0.5% | 1004 | 114 | 890 | 11.35% | 3.58% |

Baseline trên gồm 31 rule và ba rule phụ lục đang hoạt động. Đây là ngưỡng vận hành 7, khác benchmark top-75 hoặc ngưỡng validation 14 trong báo cáo trước.

## Nguồn cảnh báo sai cần xem trước

| Rule | FP độc lập test 0,3% | Giảm FP validation | Mất TP validation | Giảm FP test | Mất TP test |
| --- | ---: | ---: | ---: | ---: | ---: |
| E3 | 12625 | 465 | 2 | 413 | 0 |
| C1 | 10372 | 364 | 1 | 309 | 0 |
| A1 | 392 | 305 | 0 | 322 | 0 |
| A5 | 931 | 233 | 0 | 212 | 0 |
| A4 | 470 | 129 | 1 | 97 | 0 |
| A2 | 148 | 102 | 1 | 108 | 0 |
| F1 | 15 | 18 | 0 | 15 | 0 |
| B3 | 15 | 9 | 0 | 15 | 0 |
| C3 | 1 | 4 | 0 | 1 | 0 |
| A3 | 8 | 2 | 2 | 5 | 4 |

Thứ tự trên theo mức giảm FP **validation**, không chọn ngưỡng theo test. Loại bỏ rule chỉ là đối chứng audit, chưa áp dụng vào engine.
Không cộng các delta bỏ rule do chồng lặp và max theo nhóm; không suy ra việc tắt rule là an toàn chỉ từ delta TP bằng 0 ở một kỳ.
Ablation giữ các hit khác, lấy max theo nhóm như engine và phát lại lịch sử điểm tái diễn 30 ngày; baseline khớp tất cả 300.000 điểm đã lưu.

## Đối chứng logic và ngoại lệ

43/51 tình huống có kết quả khớp kỳ vọng. Các trường hợp lệch được giữ nguyên để chỉ ra việc cần sửa.

| Rule | Tình huống lệch | Kỳ vọng / thực tế |
| --- | --- | --- |
| A2 | Ba đợt hợp lệ cùng hóa đơn 27 triệu, cách nhau 7 ngày | False / True |
| A3 | Hai NCC chung SĐT, hai khoản 9 triệu/3 ngày theo nhánh A1 | True / False |
| A4 | Ba khoản qua hai tháng lịch; không tháng nào đủ ba | False / True |
| A5 | Khoản tròn thấp hơn baseline trên 2 sigma theo độ lệch tuyệt đối | True / False |
| B1 | Chi thuê NCC có TK trùng nhân viên, kiểm tra master theo mô tả | True / False |
| B3 | NCC mới đã có giao dịch mua hàng trước khoản chi lớn | False / True |
| B7 | Đổi TK quan sát trước hiệu lực; có giao dịch ở giữa hai mốc | True / False |
| E1 | Nghỉ hưởng lương đã duyệt 22 ngày, hợp đồng và hồ sơ đầy đủ | False / True |

Đối chứng là tình huống có kiểm soát, nằm ngoài ba dataset; không trộn vào prevalence hay số liệu hiệu quả phát hiện.

## Chồng lặp và chất lượng dữ liệu

| Hai rule | Hit chung test 0,3% | Jaccard | Hit nhãn 0 chung |
| --- | ---: | ---: | ---: |
| B5 / E4 | 1154 | 100.00% | 1144 |
| B1 / B2 | 3 | 33.33% | 0 |
| C1 / E3 | 5159 | 28.80% | 5144 |
| C2 / F1 | 5 | 18.52% | 0 |
| B2 / B3 | 3 | 12.50% | 0 |
| B5 / E3 | 1154 | 9.11% | 1144 |
| E3 / E4 | 1154 | 9.11% | 1144 |
| A1 / A4 | 67 | 8.28% | 63 |

Tên NCC có tiền tố chung 'Công ty mô phỏng đối tác': 2043/2043. Cần đối chứng E3 trên tên thật/fixture đa dạng; không sửa bộ sinh để làm đẹp precision.

## P1/T1/T2 — phụ lục ngoài 31

| Rule | Hit test | TP | FP | Precision gian lận |
| --- | ---: | ---: | ---: | ---: |
| P1 | 13 | 13 | 0 | 100.00% |
| T1 | 63 | 12 | 51 | 19.05% |
| T2 | 6 | 6 | 0 | 100.00% |

Các rule phụ lục không được cộng vào con số 31. Baseline ablation vẫn gồm chúng vì đó là cấu hình hàng đợi hiện tại.

## Cách đọc và giới hạn

- Một seed tổng hợp; ba tỷ lệ là các kịch bản liên quan, không phải ba mẫu độc lập.
- Nhãn ý đồ gian lận chưa phải nhãn độc lập về điều kiện/vi phạm từng rule; precision gian lận không chứng minh predicate đúng/sai.
- Wilson theo dòng chưa hiệu chỉnh tương quan theo vụ/NCC.
- Không có hit thì precision N/A; thiếu kịch bản dương không đủ cơ sở kết luận sensitivity.
- Các rule D và rule thiếu nguồn không được gán TP/FP/accuracy giả.
- Test đã được xem trước đó; tối ưu trên validation và dùng test mới giữ kín để nghiệm thu.
- Ablation dùng ngưỡng vận hành cố định và hit đã lưu; không chọn ngân sách/ngưỡng theo nhãn.
- Fixture kiểm tra kỳ vọng nghiệp vụ cụ thể, không đo precision/recall thực tế.
- Replay đối chiếu tổng điểm; chưa tái chạy toàn bộ predicate trên 300.000 dòng.

Accuracy tổng thể có trong CSV/JSON để đối soát, không dùng xếp hạng vì tỷ lệ gian lận thấp. 
Nguồn định nghĩa chỉ số: [precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_score.html), [recall](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.recall_score.html). Mã audit tính bằng Python chuẩn, không gọi mô hình.

Chi tiết từng rule: bấm mã trong bảng. [Ma trận CSV](rule_metrics.csv), [ví dụ TP/FP/bỏ sót](examples.csv), [đối chứng loại rule](ablation.csv), [đối chứng logic](controlled_cases.csv), [JSON đầy đủ](audit.json).
Thứ tự việc tiếp theo: [ưu tiên sửa và tiêu chí kiểm tra](../rule_audit_priorities.md).
