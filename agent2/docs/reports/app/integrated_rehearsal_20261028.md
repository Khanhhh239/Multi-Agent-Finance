# Chạy tích hợp luật → IF shadow → app → thông báo — 28/10/2026

**Đã hoàn tất kiểm chứng kỹ thuật trên nguồn mô phỏng hiện có trong workspace mới.** Luật hiện tại chấm lại toàn bộ nguồn, IF dùng model/ngưỡng v4, app nạp baseline vừa tạo và thông báo chỉ giả lập. Nghiệm thu thao tác browser của lượt này **chưa thực hiện được** vì kết nối công cụ timeout hai lần.

[Trạng thái](../../STATUS.md) · [Cách chạy](../../../examples/integrated_rehearsal/README.md) · [Kết quả máy](../../../reports/integrated_rehearsal_20261028_v2/summary.json)

## Kết quả theo cohort

| Cohort | Giao dịch nguồn | Hồ sơ app | IF evaluation | Lượt baseline, cấu hình chính | Chứng từ chỉ IF đề xuất được rà mô phỏng | Ngày trễ thêm tối đa |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 001 | 20,559 | 584 | 5,934 | 1186 | 11 | 0 |
| 003 | 20,523 | 627 | 5,877 | 1239 | 29 | 0 |
| Tổng | 41,082 | 1,211 | 11,811 | 2,425 | 40 | 0 |

Cấu hình chính: **5 lượt/120 phút, quota IF tối đa 20%, chi phí IF giả định 20 phút**, theo công ty/ngày/cohort. Lượt baseline là công việc theo scope, gồm rà tiếp/rà lại; không phải số hồ sơ độc lập. Hai cohort là hai phép thử riêng, không cộng thành công suất nhân sự thực tế.

Trên nguồn này, điểm từng giao dịch và phạm vi hồ sơ của cả hai cohort khớp baseline ngày 24/10. Đã tính lại bằng mã mới và đối chiếu từng ID; không sao chép điểm cũ để thay việc chấm luật. Các bản sửa A6/T1/T2 không tạo thay đổi điểm trên bộ nguồn này; các nhánh biên có kiểm chứng riêng trong ma trận luật.

## Đường đi đã kiểm tra

- Sao chép nguyên byte 90 bảng/cache và hai manifest được chứng thực. Nguồn, thời điểm, flag thiếu bằng chứng, feature contract và model gốc giữ nguyên. Cache không được âm thầm gắn provenance mới.
- Chấm luật + graph + rolling A5, đối soát kế toán, xuất queue/evidence và kiểm tra membership. Đồng bộ graph/ngưỡng lần hai không đổi kết quả.
- Kiểm tra lại thời gian train 2024, calibration H1/2025, evaluation H2/2025 từ ID và feature thực tế của nguồn mô phỏng. Model cũ không fit; chỉ chấm 11,811 giao dịch evaluation. Điểm số học từng ID khớp replay v4 trước đó, dù run ID mới.
- Reranking IF được giữ là nhánh chẩn đoán. Discovery có guard chạy **20 cấu hình**, giữ toàn bộ lịch baseline, không mất suất bắt buộc, không vượt trần lượt/phút, 0 ngày trễ thêm. Phần lịch sử không được chấm IF để tăng tỷ lệ phủ.
- Chạy D1–D6 riêng trong `diagnostics/`: tổng 6,718 bản ghi cửa sổ/chẩn đoán. Phần lớn chưa đủ điều kiện đánh giá; chỉ D1/D5 ở 003 có cửa sổ được đánh giá. Không suy thiếu mẫu thành âm tính và không cộng điểm/hồ sơ vận hành từ các chẩn đoán này.
- App nạp đủ **1,211 chi tiết hồ sơ** từ bản sao baseline mới. Không có ID `IFD_` được thêm vào queue vận hành; kết quả nghiên cứu IF giữ riêng.
- **42 kiểm tra HTTP tích hợp đạt**: nguồn/bằng chứng → kế toán viên gửi → kế toán trưởng trả → gửi lại → giám đốc xác nhận thiếu bằng chứng, hồ sơ tiếp tục mở; quyền công ty; bản duyệt cũ bị từ chối; người rà không tự chốt.
- Kiểm tra thêm hồ sơ nguồn thật trong chính bộ mô phỏng: yêu cầu tài liệu → nhận tham chiếu → rà tài liệu → người khác chốt. Đang mở và mới nhận đều chặn kết luận cuối; chỉ sau rà mới chốt được. Không thay điểm hoặc bằng chứng detector khi nhận tài liệu.
- Thông báo giả lập đúng người/vai trò trong C001; kiểm tra gửi lại preview không thêm job/lần thử, ngân sách và chuỗi hash lịch sử. Cuối hai câu chuyện test có **50 job giả lập, 150 mốc lịch sử gửi, 12 sự kiện duyệt**, mỗi job đúng một lần thử. Không gọi transport Email/Zalo thật.

## Kiểm thử và bằng chứng

**208 test Python đạt, 0 lỗi/skip; 92 kiểm tra JavaScript đạt.** Chín test mới kiểm tra cách ly workspace, checksum/provenance, nguồn kế toán bổ sung, loại trừ nhãn/holdout và danh tính mô phỏng. Các test regression có thể dùng fixture tạm; không dùng kết quả đó làm kết luận nghiệp vụ.

[Python](../../../reports/integrated_rehearsal_20261028_v2/python_tests.json) · [JavaScript](../../../reports/integrated_rehearsal_20261028_v2/javascript_tests.json) · [HTTP](../../../reports/integrated_rehearsal_20261028_v2/app/api_checks.json) · [Luồng chứng từ](../../../reports/integrated_rehearsal_20261028_v2/app/document_flow_checks.json) · [Đối soát nguồn/điểm/guard](../../../reports/integrated_rehearsal_20261028_v2/verification.json) · [Trạng thái browser](../../../reports/integrated_rehearsal_20261028_v2/browser_status.json).

[Trạng thái cuối của app/outbox](../../../reports/integrated_rehearsal_20261028_v2/app/final_state.json) · [Health bốn cổng app](../../../reports/integrated_rehearsal_20261028_v2/served_instances.json). Số 26 job trong biên bản API đầu là snapshot của câu chuyện thứ nhất; trạng thái cuối 50 job bao gồm thêm câu chuyện chứng từ, không thay lịch sử cũ.

Lần preflight đầu thiếu ba bảng chỉ dùng cho đối soát kế toán; runner đã bổ sung kiểm tra manifest của chúng, có test hồi quy và chạy mới vào `_v2`. Không đổi lõi luật, model hoặc tiêu chí IF để đạt kết quả. [Biên bản preflight](../../../reports/integrated_rehearsal_20261028_v2/preflight.json).

Sau khi detector/IF đã khóa, lượt quét chi tiết tuần tự được dừng ở pha chỉ đọc để chuyển sang bốn tiến trình SQLite `mode=ro`. Giữ nguyên mã sản xuất và kiểm tra đủ 1.211 hồ sơ; không giảm mẫu hoặc thay tiêu chí đạt. Mỗi phản hồi detail có SHA riêng để đối chiếu về sau. [Kế hoạch đọc song song](../../../reports/integrated_rehearsal_20261028_v2/app/parallel_validation_plan.json), [kết quả từng hồ sơ](../../../reports/integrated_rehearsal_20261028_v2/app/detail_checks.json). Sau đó dùng chính hàm verifier API của runner trên cùng database mới.

Probe hiệu năng chỉ đọc trên một hồ sơ mất **3,441 giây có tính overhead của cProfile và trong lúc chạy batch**; phần lớn thời gian nằm ở `review_support.case_support`, đọc/giải mã lặp nguồn hỗ trợ. Đây không phải P95, cam kết SLA hay phút rà của con người. [Profile](../../../reports/integrated_rehearsal_20261028_v2/app/detail_profile.txt). Cần tối ưu cách đọc theo khóa/bảng hoặc cache gắn fingerprint nguồn, giữ đúng công ty/cutoff và đối chiếu phản hồi trước/sau; không cần đổi model/luật để xử lý điểm này.

## Mở bản app mới

```powershell
$env:PYTHONPATH = "$PWD;.runtime/site-packages"
& $projectPython -X utf8 -B -m sme_fraud.integrated_rehearsal serve `
  --output reports/integrated_rehearsal_20261028_v2 --base-port 8821
```

Mở `http://127.0.0.1:8821/` cho kế toán viên, `8822` cho kế toán trưởng, `8823` cho giám đốc, `8824` cho chưa đăng nhập. Danh tính C001 cố định ở máy chủ và đều có nhãn **MÔ PHỎNG**; không phải hệ thống đăng nhập. Clock test **28/10/2026 10:00 +07:00** trên nguồn 2024–2025; không diễn giải SLA quá hạn của replay thành độ trễ ingestion thực tế. Dùng đúng tiến trình đã chạy nếu cổng đang có app, không tạo writer thứ hai vào cùng database.

Database và kết quả duyệt nằm riêng dưới `app/`. Detector/study được khóa độc lập; app còn có thể tiếp tục thao tác nên SQLite/nhật ký vận hành không nằm trong commitment các bằng chứng tĩnh. Demo cũ cổng 8774 và các snapshot/nghiên cứu/phiếu cũ giữ nguyên.

## Giới hạn chưa đóng

IF tiếp tục **shadow**, rà độc lập **0**, phút thực tế **chưa có**, lợi ích ML **chưa chứng minh**. Các lý do/kết luận/phút trong app và trace là mô phỏng kỹ thuật. Không chuyển chúng vào gói reviewer ML hoặc nghiệm thu nguồn thật.

Nguồn vẫn thiếu căn cứ thời điểm biết chứng từ; feature tương ứng tiếp tục bị che. Guard chỉ chặn trễ tăng thêm vì IF; thời gian chờ/SLA tồn đầu kỳ của baseline vẫn còn. Email/Zalo chưa được xác nhận gửi–nhận thật. Không tạo tài khoản thật.

Computer-use `cua.getState()` timeout hai lần, không có thao tác browser thành công. HTTP thực tế và kiểm tra renderer không thay thế nghiệm thu Chrome/thiết bị trên bản tích hợp này; bằng chứng Chrome 27/10 vẫn là lượt riêng.
