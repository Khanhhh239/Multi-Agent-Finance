# Hoàn tất kỹ thuật RR09 và làm mới ML v4 — 24/10/2026

**RR09 đã được triển khai và kiểm chứng trong bản app cục bộ mới. Cache/model v4, shadow cùng ngân sách và gói rà mù mới đã hoàn tất. Lợi ích ML vẫn chưa được xác nhận độc lập vì người dùng xác nhận chưa phân công người rà và người phân xử.**

## RR09

Áp dụng phương án đã giải thích trước khi người dùng yêu cầu triển khai: giữ 14 điểm làm bằng chứng vi phạm và giữ hồ sơ trong hàng đợi; phân tầng ưu tiên xử lý riêng. Với hạn mức 2.000.000 đồng, chi 2.000.001 đồng hiện là **14 điểm, ưu tiên thấp, SLA 720 giờ lịch**. Hạn mức phải có nguồn, xác minh đúng công ty, đã biết và còn hiệu lực lúc chi.

| Mức | Điều kiện với D = số chi − hạn mức L |
|---|---|
| Cao | D ≥ 1.000.000 đồng hoặc D/L ≥ 10% |
| Thấp | 0 < D < 100.000 đồng và D/L < 1% |
| Trung bình | Các khoản vượt còn lại |

So tỷ lệ bằng số nguyên; hạn mức 0 và khoản chi dương giữ mức cao, tỷ lệ không áp dụng. Nhánh VAT đủ thông tin giữ sàn trung bình nhưng không cộng thêm 8 điểm vào 14. Ưu tiên cuối lấy mức cao nhất giữa P2 đã phân tầng và tín hiệu độc lập; điểm lặp lại hiện có được giữ, không thêm ngưỡng lặp hoặc cơ chế miễn trừ mới.

Hàng đợi, SLA (cao nhất/cao/trung bình/thấp: 24/48/168/720 giờ lịch), bộ chọn và thông báo dùng cùng trường priority. Thứ tự trong cùng mức vẫn xét điểm. UI phân biệt điểm, mức vượt, tỷ lệ, ưu tiên và phiên bản `rr09-v1`. Mặc định này dùng cho lần phân tích mới có cấu hình hạn mức đủ bằng chứng; phát lại chính sách cũ chọn `legacy_high_v1`. Ngưỡng này là lựa chọn cho bản thử nghiệm, chưa được hiệu chỉnh trên SME thật.

Đã đạt **327 kiểm thử Python**, gồm 16 kiểm thử RR09 mới và 7 kiểm thử dựng cache mới; thêm **25 kiểm tra renderer/UI**. [20 đối chứng RR09](rr09_ml_completion_20261024/rr09_controls/results/summary.json) có kỳ vọng khai báo trước khi chấm: **20/20 đạt**. Bộ 32 đối chứng P2 lịch sử được ghim rõ chính sách cũ và vẫn đạt 73/73 quan sát; không sửa kỳ vọng theo kết quả detector. [Kết quả kiểm thử](rr09_ml_completion_20261024/tests.json).

## ML v4

Dựng lại 194 feature cho 001/003 từ bản sao byte giữ nguyên dữ liệu và timestamp gốc. Không điền ngày biết giả để nâng coverage; bằng chứng chưa có ngày biết tiếp tục được che theo M01. [Độ khả dụng bằng chứng](rr09_ml_completion_20261024/source_availability.json). Model/cache cũ vẫn bị từ chối theo hợp đồng, không nới cổng phiên bản; hai model mới tương thích [theo kiểm chứng](rr09_ml_completion_20261024/compatibility.json).

**Khoảng trống nguồn còn rõ rệt:** trên toàn bộ **41.082 dòng**, cả bốn cờ `support_docs_known`, `invoice_known`, `invoice_components_known`, `linked_input_vat_known` đều bằng 0 theo chính sách thời gian hiện hành. Đây là chưa đủ căn cứ xác nhận khả dụng tại cutoff, không phải kết luận không có chứng từ. Các feature chứng từ/hóa đơn tương ứng được che; model chạy được với phần thông tin còn lại nhưng chưa đủ cơ sở nghiệm thu lợi ích. Cần bổ sung thời điểm biết từ lịch sử nguồn có thể kiểm chứng, không đoán hoặc điền ngược timestamp. [Trạng thái sẵn sàng ML](rr09_ml_completion_20261024/ml_readiness.json).

Train 2024, calibration nửa đầu 2025, evaluation nửa cuối 2025; **0 dòng evaluation tham gia fit/calibration**. IF 300 cây, max_samples 2048, random_state 20261022, quantile calibration 0,3%, cùng giao thức đã cố định. Chấm **11.811 dòng evaluation**; phát lại batch 2048 và 257 cho cùng hash. Không đọc nhãn, splits, oracle hoặc chấm 005.

Baseline rules + graph + A5 được dựng lại theo cùng code/nguồn mới trước khi so IF; không so kết quả v4 với baseline cũ rồi quy thay đổi cho IF. Ngân sách 5 hồ sơ/120 phút và độ nhạy 10/240, giữ suất bắt buộc; thử phần còn lại 0%, 20%, 40% cho IF với chi phí giả định 20 hoặc 30 phút/hồ sơ.

| Bộ | Dòng evaluation | Hồ sơ chỉ IF chọn, kịch bản chính | Lấn suất bắt buộc | Vượt ngân sách |
|---|---:|---:|---:|---:|
| 001 | 5934 | 11 | 0 | 0 |
| 003 | 5877 | 29 | 0 | 0 |

Tổng **40 đầu mối ngoài baseline** là kết quả lựa chọn trong shadow; chưa xác nhận là hồ sơ hữu ích hoặc gian lận. Chi phí trên là giả định, chưa phải phút người thật. [Kết quả chính](rr09_ml_completion_20261024/primary_shadow_summary.json).

**Chi phí đối với baseline:** ở kịch bản chính, một lượt rà giao dịch A4 ưu tiên trung bình của bộ 003 bị chậm **26 ngày**, từ 07/07 sang 02/08/2025. Giữ suất bắt buộc và không vượt ngân sách không bảo đảm các lượt rà còn lại không bị chậm. Cần xử lý hoặc chốt mức chậm chấp nhận được trước khi bật phần khám phá IF trong vận hành; hiện vẫn giữ shadow. [Chi tiết và độ nhạy](rr09_ml_completion_20261024/shadow_tradeoffs.private.json).

Độ phủ lượt rà giao dịch baseline ở ngân sách 5: 001 có 63/116 lượt đủ IF; 003 có 69/164. Các phần còn thiếu được phân loại theo lịch sử/mixed trong audit; lỗi nguồn và lỗi dữ liệu lượt rà đều bằng 0. Không chấm lại train/calibration để nâng tỷ lệ. Không dùng lại mẫu số 515/1.659 của nghiên cứu cũ cho nghiên cứu mới.

## Phần cần người thực hiện

Gói v4 có **74 phiếu**: 40 đầu mối IF, 2 lượt baseline chọn khác và 32 mẫu tham chiếu ngẫu nhiên. Đây là census phần khác nhau cùng mẫu tham chiếu theo giao thức, nên không ép thành 128. Bộ 128 cũ giữ nguyên cho nghiên cứu cũ.

**0/74 rà độc lập; phút thực tế và actionable_gain vẫn null.** Người dùng xác nhận “chưa phân công”; không tự đặt người ký hoặc coi rà của trợ lý là độc lập. [Gói bàn giao và cách kiểm định](rr09_ml_completion_20261024/HANDOFF_REVIEW.md), [ZIP cho người rà](rr09_ml_completion_20261024/ml_v4/review/reviewer_packet.zip). Các nguồn đều mô phỏng; cả review người thật trên gói này cũng chưa chứng minh lợi ích tại SME thật.

## Mở app

- [Bản đã sửa](http://127.0.0.1:8774/).
- [Ca vượt 1 đồng](http://127.0.0.1:8774/p2-controls#control=RR09_ONE_DONG): xem mức vượt, 14 điểm, ưu tiên thấp và hàng đợi.
- Khởi động lại bằng [.runtime/rr09_ml_completion_20261024/run_app.ps1](../.runtime/rr09_ml_completion_20261024/run_app.ps1).

Đây là instance cục bộ với snapshot mới và database rà riêng. IF tiếp tục ở shadow; chưa đổi xếp hạng vận hành theo IF. Thông báo ở dry-run, không gửi ra ngoài. [Kiểm tra HTTP và renderer](rr09_ml_completion_20261024/app_verification.json) đạt; kiểm tra trực quan bằng trình duyệt chưa thực hiện được do CUA lỗi tải request-header policy sau một lần thử lại.

[Biên bản bảo toàn](rr09_ml_completion_20261024/verification.json) xác nhận các đầu vào, model, báo cáo và phiếu cũ không đổi. [Quyết định phần mềm RR09](rr09_ml_completion_20261024/rr09_policy_decision.json) ghi đủ ngưỡng, phạm vi và cách áp dụng phiên bản cho lần chạy mới.
