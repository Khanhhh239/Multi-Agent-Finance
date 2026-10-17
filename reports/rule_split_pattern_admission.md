# Tiếp nhận hồ sơ mẫu chia nhỏ A2/A4 — 17/10/2026

## Kết luận kỹ thuật

Đã tách điều kiện nhận hồ sơ khỏi điểm số tổng hợp: **A2/A4 có hit còn điểm, đã qua các kiểm tra mẫu và không có ngoại lệ hợp lệ được đưa vào hàng đợi rà soát**, ở mức ưu tiên trung bình nếu chưa có tín hiệu mạnh hơn. Giữ nguyên A2 = 4 điểm, A4 = 3 điểm, phép lấy max trong cùng họ A, ngưỡng điểm 7 và hard trigger. Áp dụng cùng chính sách cho dòng giao dịch và sự kiện sau đóng lô.

Chính sách tên `split_patterns_v1`, cấu hình `split_pattern_policy`; có hiệu lực trong chế độ `noise_policy=phase2`. `disabled` chỉ dùng để đối chiếu chính sách tiếp nhận trước sửa. Dòng kết quả và hồ sơ lưu `admission_basis` cùng `review_rule_ids`, phân biệt nhận theo `score_threshold`, `hard_trigger` hay `split_pattern`.

Đây là mẫu cần người rà soát đối chiếu nghĩa vụ chi, không phải kết luận gian lận và không được nâng thành hard trigger. C1/E3 hoặc một khoản cận hạn mức đơn lẻ không có quyền mở hồ sơ theo nhánh này. Những hit bị loại, thiếu định danh ngân hàng hoặc chỉ là information gap không được dùng để tiếp nhận. Hồ sơ nghĩa vụ chi còn thiếu tiếp tục giữ cảnh báo theo chính sách hiện hành; dữ liệu nguồn sai vẫn bị R7 từ chối.

## Phạm vi bằng chứng và tính nhân quả

Predicate A2 vẫn yêu cầu ít nhất ba khoản dưới hạn mức, cùng công ty/người lập/định danh TK nhận trong 30 ngày, tổng đạt hạn mức và không được loại bằng bằng chứng ràng buộc hợp lệ. Predicate A4 vẫn yêu cầu ít nhất ba khoản chi cận hạn mức trong cùng tháng lịch, sau khi loại các khoản có hồ sơ hợp lệ. Tiếp nhận không tạo lại hit đã bị loại và không cộng A2+A4 thành 7 điểm.

Hồ sơ giữ liên kết tới các khoản trước nằm trong `related_transaction_ids`, để người rà soát xem đủ mẫu và chứng từ. Chỉ giao dịch đã phát hiện được tiếp nhận; không ghi ngược điểm/cảnh báo vào những dòng quá khứ. Các khoản được nhận riêng theo mẫu không đưa vào lịch sử cộng điểm tái diễn, nên không làm tăng điểm của giao dịch mạnh hơn về sau. Cơ chế gom hồ sơ theo cụm và cửa sổ 30 ngày của R6 được giữ lại; không chuyển feedback/phân công trên database vận hành cũ.

## Ca A4 qua ranh giới tháng

Ca validation 0,3% `T000081861` ghi ngày **04/06/2025 08:15:13**. Ba khoản mà snapshot cũ dùng để phát A4 là `T000055554` ngày **07/05**, `T000096347` ngày **10/05**, `T000020737` ngày **13/05**. Chúng thuộc tháng 5. Theo tháng lịch, tại thời điểm khoản đầu tháng 6 chưa đủ ba khoản để phát A4. Giữ đúng chính sách này; không chuyển mặc định sang cửa sổ trượt để lấy lại nhãn.

Khoản tiếp theo `T000019496` lúc **13:20:13 ngày 04/06** đã phát A1 và dẫn chiếu `T000081861` làm bằng chứng, trễ **5 giờ 5 phút**. Việc không cảnh báo ngay dòng đầu khác với việc không phát hiện cả chuỗi. [Trace nguồn và hit sau sửa](split_pattern_admission_20261017_v2/sme_fraud_003/a4_boundary_trace.json). Các đối chứng riêng kiểm tra Jan 31 → Feb 1/2, tháng 31 ngày, và tùy chọn `near_period=rolling_30d` khai báo tường minh.

## Kiểm chứng và chấm lại

Ca trước sửa xác nhận A2/A4 có điểm nhưng không vào queue ở cả dòng đơn và đóng lô. Đối chứng mới gồm trả góp đúng hóa đơn, nghĩa vụ độc lập có request/PO/chứng từ, ngoại lệ có nguồn tương lai, khác/thiếu ngân hàng, cùng họ điểm, tái diễn, giới hạn tháng, độc lập nhãn, thứ tự nguồn và nạp lại hồ sơ điểm thấp qua cache/API. E1/T1 chuẩn hóa trường đếm/ngày/cờ về số nguyên trước tạo bằng chứng để hash không đổi khi đọc feature từ CSV; có đối chứng riêng tính trực tiếp và dùng cache.

[Test](../tests/test_split_pattern_admission.py), [log trước sửa](../.runtime/split_pattern_admission_20261017/before_fix_final.log), [log hồi quy](../.runtime/split_pattern_admission_20261017/tests_final.log), [7 probe readiness](../.runtime/split_pattern_admission_20261017/readiness_probes_final.log).

```powershell
python -B -m unittest discover -s tests
python -B -m sme_fraud.run_split_pattern_review --output reports/split_pattern_admission_20261017_v2
```

Lượt chấm lại dùng **225.000 dòng train/validation** của ba dataset dẫn xuất đã khóa. Baseline trực tiếp là lượt [đồng bộ 17/10](rule_feature_model_sync.md), nên đây là đối chiếu riêng bản sửa tiếp nhận, không so lại với snapshot nhiều phase cũ. Bộ chấm chạy lại engine từ nguồn/cache, buộc điểm, hard trigger và toàn bộ hit/bằng chứng phải khớp baseline theo giá trị số; chỉ sau khi khóa queue mới nối nhãn. Không chấm test; không fit lại IF hoặc hiệu chỉnh ensemble vì feature, điểm rule và model tương thích vẫn giữ nguyên.

**373/373 test hồi quy đạt**, gồm **21 test mới**; **7/7 probe readiness đạt**. Đã chấm lại engine trên 225.000 dòng, kiểm tra bất biến điểm/hit/bằng chứng và dựng/nạp lại ba cache rà soát mới. Model IF và cache feature cũ vẫn tương thích và giữ nguyên hash. [Kế hoạch khóa](split_pattern_admission_20261017_v2/evaluation_plan.json), [kết quả máy đọc](split_pattern_admission_20261017_v2/summary.json), [kiểm tra artifact](../.runtime/split_pattern_admission_20261017/artifact_verification.json).

Baseline dưới đây là trạng thái sau đồng bộ feature/model, trước sửa tiếp nhận:

| Bộ | Kỳ | TP trước → sau | FP trước → sau | Precision sau | Recall sau |
| --- | --- | ---: | ---: | ---: | ---: |
| 0.1% | train | 45 → 45 | 841 → 1552 | 2.82% | 90.00% |
| 0.1% | validation | 20 → 22 | 398 → 780 | 2.74% | 88.00% |
| 0.3% | train | 128 → 131 | 839 → 1563 | 7.73% | 87.33% |
| 0.3% | validation | 64 → 65 | 405 → 782 | 7.67% | 86.67% |
| 0.5% | train | 218 → 222 | 843 → 1571 | 12.38% | 88.80% |
| 0.5% | validation | 110 → 113 | 405 → 785 | 12.58% | 90.40% |

Tải validation ở 3 hồ sơ/công ty/ngày, trần 135 phút/ngày:

| Bộ | Hồ sơ trước → sau | Phút trước → sau | Đỉnh tồn việc trước → sau | Việc chuyển ngày trước → sau |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.1% | 335 → 569 | 7105 → 12495 | 3 → 7 | 0 → 34 |
| 0.3% | 374 → 608 | 7945 → 13310 | 5 → 7 | 2 → 42 |
| 0.5% | 408 → 641 | 8685 → 14060 | 3 → 7 | 0 → 42 |

Validation gộp ba bộ cùng seed: **TP 194 → 200; FP 1208 → 2347**. Chính sách khôi phục tiếp nhận ngay **5/6** dòng đã mất cảnh báo trong phép so sánh nhiều phase trước; ca còn lại là A4 qua ranh giới tháng đã phân tích ở trên. [Đối chiếu từng dòng cũ](split_pattern_admission_20261017_v2/previous_losses_review.json). Không mất cảnh báo đã có từ baseline trực tiếp.

**Đánh đổi rõ ràng:** thu hồi mẫu chia nhỏ làm tăng FP, số hồ sơ và thời gian rà soát; không tuyên bố chất lượng vận hành đã đạt. Đây là chính sách tiếp nhận theo điều kiện nghiệp vụ, không dùng nhãn để chọn rule/ngưỡng. Chưa hiệu chỉnh lại ngưỡng hoặc IF sau khi nhìn kết quả. Cần quyết định khả năng tiếp nhận dựa trên nguồn hồ sơ đầy đủ và kết luận reviewer độc lập.

Ước lượng tải dùng 20–45 phút/hồ sơ và cấp năng lực mỗi ngày lịch, kể cả cuối tuần; chưa đo thời gian làm việc thực tế. JSON từng bộ có tải ở 1/3/5 hồ sơ/công ty/ngày, hard negatives, loại gian lận, chế độ kế toán, từng công ty và ID giao dịch mới được nhận.

Lượt thử đầu đã bị loại tại [REJECTED.md](split_pattern_admission_20261017/REJECTED.md); chỉ các artifact trong thư mục `_v2` được dùng cho kết luận này.

## Việc còn lại

Tiếp nhận mẫu A2/A4 có thể làm tăng FP và tải rà soát khi nguồn hồ sơ nghĩa vụ chi còn thiếu. Cần nghiệm thu nguồn thật, kết luận độc lập và khả năng xử lý theo công ty/ngày trước khi chốt vận hành. Không dùng việc các ca gian lận mô phỏng quay lại queue làm bằng chứng rằng mọi hồ sơ mới đều đáng ngờ hoặc lớp tất định đã đạt nghiệm thu.

Cache SQLite trong lượt này được tạo riêng; khi áp dụng vào bộ rà soát đang có phải chạy [migration R6](rule_case_identity.md) và rà lại các hồ sơ đổi phạm vi. Model/cache của lượt đồng bộ trước vẫn giữ nguyên; snapshot kiểm chứng mã cũ tiếp tục là bằng chứng lịch sử.
