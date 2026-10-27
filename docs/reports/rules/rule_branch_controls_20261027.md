# Sinh và kiểm tra nguồn C4, E2, F2, F3, F4 — 27/10/2026

Đã tạo **5 bộ nguồn mô phỏng riêng**, chấm qua bộ nạp CSV/feature của app và kiểm tra cảnh báo, điểm, hard trigger, ưu tiên, hàng đợi và SLA. **196/196 ca khớp kỳ vọng; 708/708 test hồi quy đạt**, gồm 101 test mới. Không sửa lõi luật/model hoặc đổi ngưỡng để làm kết quả khớp.

## Độ phủ trước và sau

Trước đợt này, cả năm luật đã có đủ bảy nhóm trong ma trận: dương, âm, biên, thiếu bằng chứng, dữ liệu muộn, master và ngoại lệ. Không xuất hiện hit trong bộ dữ liệu chính không có nghĩa là chưa được test.

Bộ mới có **98 biến thể**: 38 ca đã có đối chứng/test hoặc rehearsal được tái hiện, cộng 60 ca chi tiết được khai báo bổ sung. Không khẳng định mọi ca chi tiết này chưa từng được chạm gián tiếp bởi test khác. [Ma trận JSON](../../../reports/rule_branch_controls_20261027/coverage_matrix.json) giữ ID test cũ, ID test mới và phân biệt tái hiện với bổ sung.

| Luật | Bảy nhóm trước đợt này | Biến thể trong bộ mới | Ca / hai seed | Khớp | Nhánh kiểm tra chi tiết |
| --- | --- | ---: | ---: | ---: | --- |
| C4 | Đã có | 18 | 36 | 36 | Maker/checker, một người được phép nhưng người còn lại vi phạm, biên bắt đầu/kết thúc, thu hồi quyền, chứng cứ thao tác thiếu/sai người, master sau hành động |
| E2 | Đã có | 19 | 38 | 38 | Lương sau nghỉ việc, truy lĩnh/trợ cấp/thưởng đúng kỳ, lệch quyền lợi 1 đồng, sai nhân sự/kỳ lương, tự duyệt, tái tuyển đến muộn, khoảng thời gian sai |
| F2 | Đã có | 17 | 34 | 34 | Control không bắt buộc, sai vai trò, thăng quyền sau thao tác, đúng/vượt cap 1 đồng, chính sách đến muộn/hết hạn, pending/cancelled, nhiều control với kết quả khác nhau |
| F3 | Đã có | 18 | 36 | 36 | Cùng chứng từ ghi log lặp khác với hai chứng từ trùng số; bản nháp/hủy/khác dải; sổ đến đúng/sau cutoff; dải đảo chiều/quá lớn |
| F4 | Đã có | 26 | 52 | 52 | Đúng 60/61 ngày, thu đủ/một phần, sai khách/hóa đơn/người xác minh, dòng journal/phi tài chính, sai thời điểm xác minh, coverage và giải trình hết hạn/thu hồi |
| **Tổng** | **35/35 ô đã có test trước đó** | **98** | **196** | **196** | Không thay thế kiểm tra nguồn thật |

So với một lượt trace riêng gồm **214 test nguồn hiện có**, các test mới thực thi thêm **6 dòng và 13 chuyển tiếp dòng** trong `evidence_policy.py`, gồm bỏ qua action/override không hợp lệ, gộp override có vi phạm và một số guard hóa đơn/phân bổ. Đây là độ phủ quan sát trên đúng bộ test đã liệt kê, không phải tỷ lệ branch coverage đầy đủ hoặc bằng chứng rằng các dòng chưa từng được chạy ở mọi bộ khác. [Chi tiết trace](../../../reports/rule_branch_controls_20261027/line_transition_coverage.json).

## Dữ liệu đã sinh

[Hướng dẫn và thư mục dữ liệu](../../../data/rule_branch_controls_20261027/README.md). Hai seed là `2026102701`, `2026102702`; cutoff **12/09/2025 11:00 +07:00**.

- **206 giao dịch chuẩn** trong năm cache, mỗi giao dịch có 194 feature hữu hạn. Nguồn có manifest/checksum và đúng whitelist của detector; không có file nhãn/split được nạp.
- **186 ca hợp lệ**, đối soát thêm điểm thực nhận, điểm nội tại và hard trigger từ đầu ra đã lưu, không chấm lại để đổi kết quả.
- **10 ca nguồn sai** được giữ riêng trong `rejected_inputs.json`, không trộn vào cache. Việc bị từ chối đúng schema/định danh/dải số là kết quả đạt của ca kiểm tra nguồn.
- **2 giao dịch sau cutoff** giữ riêng trong `deferred_transactions.json`, không đưa vào cache/chấm; nguồn chứng từ/revision muộn vẫn có để kiểm tra as-of.
- **276 chứng từ sổ cái** cân Nợ/Có. Mỗi control/seed có công ty mô phỏng riêng để tránh nhiễm bằng chứng giữa các ca; không xem chúng là các doanh nghiệp thực độc lập.

Các kỳ vọng cuối được khóa cùng kế hoạch và checksum nguồn trước lượt chấm toàn bộ. Khi dựng fixture đã phát hiện hai ca sai thứ tự thời gian phải xếp vào **từ chối nguồn**, và template kế toán đã đổi dòng journal thành bank; đã sửa mô tả kỳ vọng/fixture theo schema và ý định test trước khi khóa. [Probe ban đầu và lý do sửa](../../../reports/rule_branch_controls_20261027/preflight_validation.json) được giữ để không che quá trình chuẩn bị.

## Kết quả thử

| Kiểm tra | Kết quả |
| --- | --- |
| Nạp CSV + contract + chấm + đối chiếu | **196/196** khớp, gồm cả không phát hiện, thiếu căn cứ và từ chối nguồn; không chỉ đếm ca có cảnh báo |
| Điểm/hard trigger | **186/186** ca hợp lệ khớp; E2 xác nhận có hard trigger, các ngoại lệ/thiếu căn cứ không tự thành hard trigger |
| Queue/SLA | C4/F2 khi đủ điều kiện: trung bình, 168 giờ; E2 xác nhận: cao nhất, 24 giờ. F3/F4 nguồn dương: trung bình, 168 giờ; thiếu coverage: thấp, 336 giờ và có lịch tái rà |
| F3 trùng số | Là tín hiệu ngữ cảnh theo cấu hình hiện hành: có thể có điểm nội tại nhưng không tự mở hồ sơ vận hành. Khoảng trống dải số đi qua hồ sơ nguồn riêng |
| Hồi quy | **708/708** đạt, không lỗi/skip; gồm bộ 607 trước đó và 101 test mới |
| App/SQLite | Nạp cả năm nhóm và đọc chi tiết **120/120 hồ sơ test**. Không có lượt nhận hoặc kết luận của người dùng; không đụng database demo |

Số hồ sơ app gồm cả các yêu cầu bằng chứng do luật khác tạo ra, ví dụ P2 trong nhóm chi tiền mặt F2; **không coi mọi hồ sơ trong một nhóm là vi phạm của luật mục tiêu**. So sánh kiểm tra đúng rule, giao dịch/scope và công ty. Các ca C4/F2 không có chứng cứ thao tác không bị gọi là “âm tính gian lận”; chúng chỉ không đủ căn cứ để tạo tín hiệu tương ứng.

## Dùng lại và bằng chứng

Sinh lại phải chọn đường dẫn mới, không ghi đè bộ này:

```powershell
& $projectPython -B -m sme_fraud.rule_branch_controls `
  --data-root data/rule_branch_controls_next --output reports/rule_branch_controls_next
```

[Kế hoạch](../../../reports/rule_branch_controls_20261027/evaluation_plan.json) · [kỳ vọng](../../../reports/rule_branch_controls_20261027/expectations.json) · [checksum nguồn](../../../reports/rule_branch_controls_20261027/source_commitment.json) · [so sánh từng ca](../../../reports/rule_branch_controls_20261027/comparisons.json) · [hồi quy](../../../reports/rule_branch_controls_20261027/regression_results.json) · [đối soát điểm/sổ cái](../../../reports/rule_branch_controls_20261027/downstream_verification.json) · [tích hợp app](../../../reports/rule_branch_controls_20261027/app_integration.json) · [mã nguồn đã dùng](../../../reports/rule_branch_controls_20261027/source_snapshot.zip) · [bảo vệ file cũ](../../../reports/rule_branch_controls_20261027/protected_verification.json) · [hash đầu ra](../../../reports/rule_branch_controls_20261027/commitment.json).

**Không phát hiện lỗi mới cần sửa trong lõi năm luật qua bộ ca này.** Kết quả là kiểm chứng phần mềm trên nguồn mô phỏng đã biết cấu trúc, không phải precision/recall gian lận thực địa. Model không được fit/chấm; reviewer độc lập vẫn 0. Cổng nghiệm thu nguồn thật tiếp tục **`awaiting_real_data`**; dữ liệu mới không đóng phần còn thiếu này. Holdout, model và các báo cáo đã khóa trước đây được giữ nguyên.
