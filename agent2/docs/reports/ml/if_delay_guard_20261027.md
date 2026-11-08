# Giới hạn trì hoãn baseline trong IF shadow — 27/10/2026

**Đã đặt giới hạn 0 ngày chậm thêm so với lịch baseline và chạy lại cùng nguồn, điểm IF, ngưỡng và ngân sách.** Lượt A4 trước đây chậm 26 ngày nay được rà đúng ngày baseline. IF tiếp tục ở shadow.

[Trạng thái dự án](../../STATUS.md) · [Giao thức mới](../../../examples/ml_if_discovery_shadow/delay_guard_protocol.json) · [Kết quả máy](../../../reports/if_delay_guard_20261027/summary.json)

## Chính sách

Ở mỗi cutoff ngày, giữ trước sức chứa cho những lượt baseline được chọn bởi đối chứng tại cùng cutoff, gồm cả các lượt thông thường. Giữ các suất hard trigger/nguồn bắt buộc; chỉ phần suất và phút còn lại mới dùng cho IF. Quota 20%/40% là trần, không phải số suất bắt buộc cấp cho IF.

Giới hạn là **0 ngày trễ thêm vì IF**, không phải 0 ngày chờ từ khi phát sinh hồ sơ. Chỉ lịch baseline của ngày hiện tại được dùng để giữ suất; lịch tương lai không quyết định lựa chọn hôm nay. Nếu một reservation không thể khớp nguồn hoặc không vừa sức chứa, phép thử báo lỗi thay vì bỏ baseline hoặc tăng ngân sách. Chính sách này không hứa một khoảng grace dương chưa được chứng minh khả thi.

Ứng viên, định danh chứng từ, điểm đã tính, ngưỡng calibration và bộ khử trùng giữ nguyên. Hai mức công suất vẫn là 5 lượt/120 phút và 10 lượt/240 phút mỗi công ty/ngày; chi phí IF giả định 20/30 phút, quota 0/20/40%. Mỗi lượt vẫn trả riêng chi phí; IF không tự hoàn tất công việc baseline về sau.

## Kết quả chính: 5 lượt / 120 phút, quota 20%, IF 20 phút

| Chỉ số | Trước guard | Sau guard |
| --- | ---: | ---: |
| Lượt baseline được rà | 2425 | 2425 |
| Lượt baseline chậm thêm | 1 | 0 |
| Trễ thêm lớn nhất | 26 ngày | 0 ngày |
| Chứng từ chỉ IF phát hiện được rà | 40 | 40 |
| Mất suất bắt buộc / vượt ngân sách | 0 / 0 | 0 / 0 |

Hai nhánh sau guard rà đúng cùng tập 40 chứng từ IF như trước: 11 ở cohort 001 và 29 ở cohort 003. Cả 2425 lượt baseline trong đối chứng đều được giữ, không có lượt bị loại để làm đẹp chỉ số trễ. Đây là lượt công việc theo scope, có thể gồm rà tiếp/rà lại, không phải 2425 hồ sơ độc lập.

**Trường hợp cụ thể:** `RC_71f9d98838c10e2c`, cohort 003, work key `abc81666319ef96f088f7128d527ea211c3115430cf37acf6ab9c3d70c363470`. Lịch baseline là **07/07/2025**; nhánh IF cũ chọn **02/08/2025**; nhánh có guard chọn **2025-07-07**. [Đối chiếu từng lượt](../../../reports/if_delay_guard_20261027/baseline_delay_trace.private.csv).

## Đánh đổi

Ở cấu hình chính, guard giảm cơ hội chọn IF trong **4 lượt công ty/ngày**. Những đầu mối này được giữ chờ; cuối kỳ vẫn rà được đủ 40 chứng từ IF. Thời gian chờ IF lớn nhất sau guard là **26 ngày**. [Các ngày giảm quota](../../../reports/if_delay_guard_20261027/primary_quota_reductions.csv), [thay đổi ngày rà IF](../../../reports/if_delay_guard_20261027/if_date_changes.private.csv).

Thời gian chờ baseline tính từ lúc vào hàng đợi mô phỏng vẫn có thể dài: lớn nhất **21 ngày ở 001** và **27 ngày ở 003**, bằng chính đối chứng. Một số SLA trên snapshot lịch sử đã qua hạn trước cửa sổ đánh giá; guard không sửa được giả định tồn đầu kỳ hoặc thiếu công suất vốn có. Các số này tách khỏi phần trễ tăng thêm do IF. Ngày rà có độ phân giải ngày lịch, không phải phút xử lý thực tế.

## Độ nhạy và kiểm chứng

Đã kiểm tra **20 cấu hình** trên hai cohort với các mức ngân sách/quota/chi phí nêu trên. Tất cả đều 0 ngày trễ thêm, không mất lượt baseline đối chứng, không đẩy suất bắt buộc và không vượt số lượt/phút. [Bảng trước/sau đầy đủ](../../../reports/if_delay_guard_20261027/scenario_comparison.csv).

Nhánh v1 vẫn được giữ để tái hiện lịch sử. Trên cùng inputs, **60 file đối chứng** (summary, daily, selections của 20 cấu hình) khớp byte với kết quả đã khoá trước đây. Đây là đối chứng lịch sử, không phải điều chỉnh baseline theo kết quả mới.

**144 kiểm thử đạt**, trong đó **14 test mới**: tái hiện trễ 26 ngày, giữ ngày baseline, thiếu phút dù còn slot, hết slot dù còn phút, giữ suất bắt buộc, scope thay đổi, dữ liệu tham chiếu tương lai, nhánh 0% và tham số không hợp lệ. [Kết quả test](../../../reports/if_delay_guard_20261027/tests.json).

Đối chiếu opaque hash **10225 file**: chỉ mã `sme_fraud/compare_if_discovery.py` thay đổi theo bản sửa này; dữ liệu, model, feature contract, các snapshot/phiếu cũ và database giữ nguyên. [Biên bản](../../../reports/if_delay_guard_20261027/protected_verification.json).

## Chạy lại

Dùng môi trường trong [hướng dẫn phát triển](../../DEVELOPMENT.md) và [lệnh ví dụ cập nhật](../../../examples/ml_if_discovery_shadow/README.md). Giao thức mới là `delay_guard_protocol.json`; `protocol.json` cũ là v1 để tái hiện nghiên cứu trước guard. Kết quả mới phải ghi vào thư mục mới.

Phép thử dùng các điểm evaluation đã khoá của model v4 trên cùng baseline ngày 24/10 để đo riêng tác động thay lịch. Không fit model, không chấm lại train/calibration/evaluation, không dựng lại nguồn hoặc chấm lại rules, không ghi hàng đợi vận hành và không gửi thông báo. Các bản sửa rule ngày 27/10 không được trộn vào đối chứng này.

Guard đã đạt điều kiện kỹ thuật trên dữ liệu mô phỏng. Chưa có rà độc lập hoặc phút thực tế, chưa chứng minh lợi ích ML; gói 74 phiếu cũ giữ riêng theo nhánh trước guard, không tự chuyển kết luận sang nghiên cứu mới.
