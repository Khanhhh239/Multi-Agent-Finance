# Công suất rà soát dùng chung — 17/10/2026

**Đã tách giới hạn số lượt và số phút, dùng chung hợp đồng với API, bổ sung lịch làm việc và tồn cuối kỳ.** Simulator và API cùng nhận hai hồ sơ 45 phút trong ngày đầu ở cấu hình **5 lượt/120 phút**; ba hồ sơ còn lại chuyển sang hai ngày tiếp theo. Không tăng công suất UI để khớp giả định 225 phút cũ.

## Hợp đồng và cách gọi

[`review_capacity.py`](../sme_fraud/review_capacity.py) là nguồn chung cho cấu hình, kiểm tra lượt/phút và lịch địa phương. [`ReviewStore.admit`](../sme_fraud/review_store.py) và [`budget_review`](../sme_fraud/evidence_evaluation.py) cùng dùng `ReviewCapacity.fits`. Cấu hình phải là số nguyên dương; không chấp nhận boolean, số thực hoặc chuỗi thay cho cấu hình số.

`budget_review` bắt buộc nhận riêng `capacity_minutes`, không tự suy ra bằng cách nhân số lượt:

```python
from sme_fraud.review_capacity import ReviewCapacity, ReviewCalendar
from sme_fraud.evidence_evaluation import budget_review

capacity = ReviewCapacity.ui(5)
load = budget_review(cases, events, transactions, labels=None,
    budget=capacity.slots, capacity_minutes=capacity.minutes,
    calendar=ReviewCalendar(tuple(range(5)), ('2025-01-01',)),
    period_end='2025-06-30')
```

Năm cấu hình được đặt tên riêng trong các runner:

| Nhóm | Lượt/công ty/ngày | Phút/công ty/ngày |
| --- | ---: | ---: |
| Nghiên cứu, giữ đối chứng lịch sử | 1 | 45 |
| Nghiên cứu, giữ đối chứng lịch sử | 3 | 135 |
| Nghiên cứu, giữ đối chứng lịch sử | 5 | 225 |
| UI | 5 | 120 |
| UI | 10 | 240 |

Các dòng nghiên cứu có `profile_kind=research`, không phải cấu hình UI. Các dòng UI lấy trực tiếp từ `ReviewCapacity.ui`; thay đổi chính sách phút tại nguồn chung sẽ đi qua cả simulator/API. Đã cập nhật ba runner gọi `budget_review`; các caller ngoài repo cần bổ sung đối số phút.

## Lịch, cutoff và thời gian xử lý tồn

Mặc định vẫn là mọi ngày lịch. Có thể khai báo tập ngày trong tuần và ngày nghỉ cụ thể, dùng ngày địa phương UTC+7; không tự suy diễn lịch nghỉ lễ. API cho xem thông tin lịch trong metadata, từ chối cấp lượt mới ngoài lịch và giữ tính idempotent cho lượt đã cấp trong ngày.

Có thể chạy server trực tiếp với lịch thứ Hai–thứ Sáu, thêm ngày nghỉ cụ thể:

```powershell
python -m sme_fraud.review_server --working-weekdays 0,1,2,3,4 --non-working-date 2025-01-01
```

Lịch là cấu hình tiến trình, cần truyền lại khi khởi động; launcher mặc định vẫn dùng mọi ngày. Các ngày trong ví dụ là cấu hình minh họa, không phải lịch SME đã nghiệm thu.

Các chỉ số mới:

- `backlog_at_period_end_work_items/minutes`: tồn **sau khi cấp lượt của ngày cuối kỳ**, toàn bộ công ty; `period_end_by_company` giữ từng công ty.
- `reviewed_within_period`, `reviewed_after_period`: phân biệt xử lý trong kỳ và xử lý phần tồn sau kỳ.
- `drain_completion_date`, `drain_calendar_days`: ngày và số ngày lịch để giải phóng phần tồn. Nếu đã hết trước/cuối kỳ, lấy ngày cuối kỳ và 0 ngày.
- `backlog_end_work_items`: tồn sau bước xử lý tiếp, không thay cho tồn cuối kỳ. Hồ sơ không thể vừa trần phút được giữ rõ trong `unschedulable_work_items`, không tự chia việc hoặc bỏ hồ sơ. Nếu chưa giải phóng hết, ngày hoàn thành là `null`.
- `excluded_cases_after_period`, `excluded_rereviews_after_period`: công việc có ngày bắt đầu/hẹn sau cutoff không được cộng vào nhu cầu của kỳ. Bước xử lý tiếp chỉ giải phóng công việc đã đến hạn trong kỳ.

Có giới hạn số ngày xử lý tiếp; nếu chạm giới hạn vẫn báo tồn và `drain_limit_reached`, không kết luận đã xử lý hết. Cùng hồ sơ không dùng hai lượt trong một ngày khi có cả công việc ban đầu và tái rà đã khai báo.

## Tính lại tải từ queue đã khóa

[`replay_review_workload.py`](../sme_fraud/replay_review_workload.py) chỉ đọc hai lượt báo cáo trước/sau tiếp nhận A2/A4 và dữ liệu train/validation đã khóa, tạo thư mục kết quả mới; không chạy detector, đọc nhãn để tính chất lượng hoặc fit IF. Mỗi bộ có 40 tổ hợp: hai snapshot × hai kỳ × hai lịch × năm cấu hình. Tổng **120 tổ hợp**, cùng **225.000 quan sát**, không phải 120 tập quan sát độc lập.

Đối chiếu **36 tổ hợp nghiên cứu theo mọi ngày lịch** khớp chính xác các chỉ số tải đã lưu. Đã kiểm tra **236 file bảo vệ** trước/sau, gồm nguồn, feature, model, báo cáo/queue cũ và SQLite; hash giữ nguyên. Hợp đồng feature vẫn tương thích. Các report đã khóa và database vận hành không bị dựng lại/migration. [Kế hoạch](review_capacity_20261017/evaluation_plan.json), [kết quả](review_capacity_20261017/summary.json).

Trên **validation sau tiếp nhận A2/A4**, cấu hình UI **5 lượt/120 phút**:

| Bộ | Hồ sơ | Lượt phải chuyển ngày, mọi ngày lịch | Lượt phải chuyển ngày, T2–T6 | Tồn 30/6 khi làm T2–T6 | Xử lý hết tồn |
| --- | ---: | ---: | ---: | ---: | --- |
| 001 | 569 | 6 | 113 | 4 hồ sơ / 80 phút | 01/07/2025 |
| 003 | 608 | 7 | 124 | 2 hồ sơ / 40 phút | 01/07/2025 |
| 005 | 641 | 9 | 134 | 3 hồ sơ / 60 phút | 01/07/2025 |

Theo mọi ngày lịch, cả ba bộ đều không còn tồn tại cuối 30/6; đổi từ 225 xuống 120 phút không tăng carryover trên chính queue hiện tại. Lịch T2–T6 là **phân tích độ nhạy**, chưa phải lịch vận hành đã được chọn. Ngày 01/07 chỉ là ngày xử lý backlog của kỳ trước, không nạp/chấm giao dịch tập test. Không diễn giải các thay đổi tải này thành thay đổi TP/FP hoặc năng lực reviewer thực tế.

## Kiểm chứng và giới hạn còn lại

Bộ test đối chiếu API/simulator bao phủ hai mức UI, đủ lượt nhưng thiếu phút, hết lượt nhưng còn phút, lấp phần phút còn lại, tách công ty/ngày, nghỉ cuối tuần/ngày nghỉ cụ thể, cutoff, tái rà cùng ngày, hồ sơ vượt trần phút và giới hạn xử lý tiếp. [Test](../tests/test_review_capacity.py).

**390/390 test hồi quy đạt**, gồm **17 test mới**, 101,696 giây; **7/7 probe readiness đạt**, 0,746 giây. [Log hồi quy](../.runtime/review_capacity_20261017/tests_final.log), [log probe](../.runtime/review_capacity_20261017/readiness_probes_final.log), [checkpoint/hash](../.runtime/review_capacity_20261017/result.json). Các probe chạy từ bản sao mới để giữ nguyên artifact kiểm chứng cũ.

Mức ưu tiên vẫn lấy từ sự kiện mở, công sức vẫn là ước lượng theo snapshot cuối; cập nhật ưu tiên theo sự kiện sau mở và đo thời gian SME thực tế là việc tiếp theo, không được coi là đã hoàn tất nhờ bản sửa này. Cách gom hồ sơ A4, export lý do dòng/lô và nghiệm thu nguồn thật vẫn còn mở. Điểm rule, ngưỡng, hard trigger, hit, định danh hồ sơ và chính sách thiếu hồ sơ nghĩa vụ chi giữ nguyên.
