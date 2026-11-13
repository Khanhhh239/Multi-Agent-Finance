# M1-P0-2 — Bằng chứng xác minh

## Thay đổi

- Time parser nhận khoảng có đầu mút, FY/YTD theo năm dương lịch, kỳ con có điểm cắt, tháng dạng `T1/2026`, ngày đơn cho flow và ngày chốt snapshot. Kỳ thay thế mơ hồ, ngày không hợp lệ và FY có tháng bắt đầu khác tháng 1 yêu cầu làm rõ. Mặc định FY theo đặc tả và cấu hình bộ sinh dữ liệu. `company_info` trong MPX10 v3 đang dùng không có khóa `fiscal_year_start_month`.
- Planner phân biệt cụm chỉ view với chiều phân nhóm, nhận biên lợi nhuận đã định danh và hỏi lại khi chỉ nêu “margin”. Breakdown/ranking không nhóm theo thời gian dùng grain tháng, kể cả sau lượt làm rõ. Câu yêu cầu xem giá trị theo từng kỳ trong một khoảng rõ ràng dùng timeseries. Yêu cầu tính chênh lệch riêng vẫn ngoài hợp đồng.
- Validator chấp nhận grain ngày cho range. Adapter E2E chuyển mã warning sang tên của benchmark. API production tiếp tục dùng `partial_data_watermark` và `ratio_undefined`.

## Lượt triển khai

1. Giả thuyết ban đầu là phần lớn lỗi deterministic do parser loại nhiều mốc và planner nhận sai cụm nhóm. Lệnh `.venv/bin/python -m pytest -o addopts='' -q tests/contracts/test_planner_time_regressions.py` tái hiện 33 lỗi trên 42 ca trước khi sửa. Sau khi thêm quy tắc parser/planner, grain ngày và ánh xạ warning, 44 ca hồi quy, 122 contract test tập trung và 567 test toàn suite qua. Benchmark lượt 1 có 64 plan đúng và 104 trạng thái đúng, so với 45 và 80 ở baseline.
2. Đối chiếu từng ca phát hiện BM-122 chưa nhận “Quý 2 năm 2026”. Bổ sung cú pháp này, giữ hành vi chấp nhận hai cách ghi đồng nhất cùng kỳ và dùng cùng quy tắc grain khi tiếp tục lượt làm rõ. Một kỳ vọng ranking trong test cũ đổi từ `quarter` sang `month` theo yêu cầu mới. Kiểm tra planner với metric đã biết khớp trạng thái và thời gian ở 33/35 ca được nêu trong Issue. BM-037 yêu cầu phép so sánh chênh lệch ngoài hợp đồng. BM-059 là aggregate có bộ lọc, với nhãn grain tháng dù yêu cầu chuẩn hóa grain chỉ áp dụng cho breakdown/ranking. Đối chiếu có metric đầu vào cố định chỉ là kiểm thử planner, tách khỏi benchmark E2E bên dưới.

## Cổng xác minh

| Lệnh | Exit | Kết quả |
| --- | ---: | --- |
| `.venv/bin/python -m ruff check agent4/planning agent4/eval_adapter.py` | 0 | Qua |
| `make format-check lint typecheck PYTHON=.venv/bin/python CHECK_PATHS='agent4/planning agent4/eval_adapter.py tests/contracts/test_clarification_mode.py tests/contracts/test_planning_and_plan_validation.py tests/contracts/test_planner_time_regressions.py'` | 0 | 10 tệp đúng format, lint và compileall qua |
| `.venv/bin/python -m pytest tests/contracts/test_planning_and_plan_validation.py tests/contracts/test_clarification_mode.py tests/contracts/test_result_answer_response.py -v` | 0 | 123 qua |
| `.venv/bin/python -m pytest -o addopts='' -q tests/contracts/test_clarification_mode.py tests/contracts/test_planner_time_regressions.py` | 0 | 54 qua |
| `.venv/bin/python -m pytest -q tests` | 0 | 570 qua |
| `git diff --check` | 0 | Qua |

## Benchmark E2E

Cùng adapter production, 140 ca dev, model `qwen2.5:0.5b` với digest `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`, prompt `metric-selection-v1-structured`, seed `20261101`, preset `config/eval_governed_lexical.yaml` và warehouse MPX10 v3. SHA-256 của dataset là `094fb090bff62ee8c83045eed3780c371ec3f4cf38095f274237c02a6b5b88d5`. SHA-256 của config là `cfc4197eb34a88379d9b68c3dc65175d1e8f2ad3b84c479cdb8f329899c2fa41`.

```bash
AGENT4_WAREHOUSE_TENANT_ID=minh-phat AGENT4_METRIC_SELECTION_CONFIG=config/eval_governed_lexical.yaml \
  make eval PYTHON=.venv/bin/python ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION=qwen2.5:0.5b@a8b0c5157701 PROMPT_VERSION=metric-selection-v1-structured \
  EVAL_CONFIG=config/eval_governed_lexical.yaml OUTPUT_DIR=reports/eval/M1-P0-2_governed_dev_lexical \
  BASELINE=reports/eval/M1-P0-1_governed_dev_lexical/summary.json
```

Lượt cuối dùng cùng lệnh với `OUTPUT_DIR=reports/eval/M1-P0-2_governed_dev_lexical_final`.

Cả hai lượt ghi đủ 140 dự đoán và được runner xác nhận so sánh được với baseline. Runner thoát 1 do 11 ca được phân loại `runtime_failure`. `make eval` thoát 2 ở cả hai lượt. Cấu hình này không có ngưỡng chất lượng riêng.

| Chỉ số | M1-P0-1 | Lượt 1 | Lượt cuối |
| --- | ---: | ---: | ---: |
| Chọn metric chính xác | 79/140 | 79/140 | 79/140 |
| Plan chính xác | 45/140 | 64/140 | 67/140 |
| Trạng thái E2E chính xác | 80/140 | 104/140 | 107/140 |
| Ca thiếu warning bắt buộc | 14 | 8 | 8 |
| SQL thực thi thành công | 53/53 | 77/77 | 80/80 |
| Ca kiểm tra safety đạt | 13/15 | 13/15 | 13/15 |
| Ca runtime failure | 10 | 11 | 11 |
| P50 / P95, 140 mẫu mỗi lượt | 1,788 / 2,257 giây | 1,605 / 2,152 giây | 1,590 / 2,169 giây |
| Token trung bình quan sát được | 722 trên 116 mẫu | 722 trên 116 mẫu | 722 trên 116 mẫu |

Chi phí USD và độ chính xác số liệu độc lập chưa đo. 22 plan và 27 trạng thái E2E chuyển từ sai sang đúng so với baseline. Không có ca chuyển từ đúng sang sai ở hai chỉ số này.

- BM-014 chốt đúng 2025-12-31. BM-023 trả timeseries tháng 8–9 và warning `partial_data`. BM-040 giới hạn Q4 ở tháng 10. BM-002, BM-103 và BM-122 khớp plan sau khi nhận “Quý 2 năm 2026”.
- BM-120 dùng đúng 2026-01-01 đến 2026-09-30, qua SQL safety và trả `no_data`. BM-119 cũng trả `no_data` vì thực thể không có dòng khớp trên MPX10 v3. Hai ca thuộc dữ liệu v2.1 trong tham chiếu MPX10.
- BM-105 qua luồng ngày đơn và trả tỷ lệ 0,231484 từ MPX10 v3, nên warning mẫu số 0 mà nhãn kỳ vọng không được phát. BM-017 và BM-109 dừng ở LLM metric selection, trước khi gọi planner.
- Ca runtime tăng thêm là BM-037. Runner đếm việc từ chối phép tính chênh lệch ngoài hợp đồng là runtime failure. Các ca còn lại gồm bốn `unknown_metric`, hai lựa chọn trộn flow/snapshot và bốn plan có metric hoặc chiều không tương thích.

[Baseline](../eval/M1-P0-1_governed_dev_lexical/summary.json) · [Lượt 1](../eval/M1-P0-2_governed_dev_lexical/summary.json) · [Lượt cuối](../eval/M1-P0-2_governed_dev_lexical_final/summary.json) · [Kết quả từng ca](../eval/M1-P0-2_governed_dev_lexical_final/cases.jsonl)
