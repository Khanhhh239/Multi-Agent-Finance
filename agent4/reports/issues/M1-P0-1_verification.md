# M1-P0-1 — Bằng chứng xác minh

Cổng xác minh bắt buộc đã qua với **523 test, 0 lỗi**. Lượt tương thích giữ nguyên tám test từng lỗi và nhãn benchmark.

## Phạm vi và quyết định

- `MetricCatalog()` chứa toàn bộ 66 ID trong `REGISTRY`. Compiler có 22 binding canonical và 6 binding ID M0.2. Cả 21 ID kỳ vọng trong 140 ca dev đều có binding. Registry thực tế có 45 ID chỉ có metadata vì `budget_amount` thuộc catalog M0.2 và nằm ngoài registry. `free_cash_flow` và `altman_z_score` cũng nằm ngoài registry và được đăng ký thêm dưới dạng metadata theo yêu cầu.
- `MetricCatalog()` giữ 15 định nghĩa M0.2 và liệt kê 13 metric M0.2 đã xác minh. Pipeline production và kiểm tra warehouse khởi tạo `MetricCatalog(canonical=True)`. Cả hai chế độ tra cứu được hai bộ ID và cho phép chỉ định ID cụ thể qua allowlist. Hai alias tỷ suất giữ đơn vị phần trăm và 2 chữ số của hợp đồng M0.2. Chúng dùng cùng tử số và mẫu số với tỷ lệ canonical 6 chữ số.
- Công thức cụ thể của Issue được ưu tiên ở những chỗ registry cũ có tập tài khoản khác, gồm chi phí quản lý/bán hàng, lương, lợi nhuận hoạt động/trước thuế và ba tỷ lệ snapshot. Chủ sở hữu nghiệp vụ cần rà soát các khác biệt này trước khi dùng kết quả để thay thế báo cáo từ engine cũ.
- Warehouse biểu diễn bút toán mở sổ bằng `source_module = 'OPENING'` và vay ngắn hạn bằng tiền tố `34111`. Flow loại mở sổ và kết chuyển. Tỷ lệ snapshot dùng số dư lũy kế tại một ngày chốt và trả NULL khi mẫu số bằng 0. Chuỗi số dư nhiều kỳ chưa được compiler hỗ trợ.
- Kiểm tra MPX10 đối chiếu đủ các ID trong tham chiếu đóng băng. Kiểm tra warehouse chạy toàn bộ binding canonical đã phê duyệt. Cổng SQL safety vẫn xác thực lại truy vấn từ plan đã niêm phong.

## Các lượt triển khai ban đầu

1. Giả thuyết ban đầu là chuẩn hóa ID và binding sẽ sửa được coverage và lọc theo nhà cung cấp. Ruff trên ba file chính và `scripts.check_warehouse` thoát 0 với 44 cặp metric/view. Lượt toàn bộ pytest có 17 fail và 8 error, trong đó metadata `cash_flow` làm bộ kiểm tra nội dung tài liệu từ chối khi tạo index. `scripts.check_mpx10` thoát 1 do tập khóa của catalog mới khác tập khóa đóng băng.
2. Sửa metadata để tạo được index, giữ 6 chữ số tỷ lệ ở executor, ánh xạ allowlist ID cũ trong retrieval và kiểm tra MPX10 theo tập ID đóng băng. Pytest tập trung còn 2 fail, toàn suite còn 9 fail và không có error. Warehouse và MPX10 thoát 0. Chín test mới thoát 0.
3. Dùng kiểm tra quyền trực tiếp tại reranker khi đầu vào nêu ID cụ thể, giữ hợp đồng cho các candidate M0.2 đã được cung cấp. Kiểm thử reranker riêng thoát 0. Hai lệnh pytest bắt buộc được chạy lại và cho kết quả bên dưới.

## Lượt tương thích

Giả thuyết là tám lỗi còn lại đến từ việc dùng catalog canonical làm mặc định cho caller M0.2. Catalog hiện tách bộ định nghĩa dùng để liệt kê khỏi bộ định nghĩa dùng để tra cứu. Retrieval, clarification và recovery sử dụng danh sách của chế độ catalog được truyền vào. Dense retrieval dùng lại vector của ID tương ứng khi allowlist nêu ID ở namespace còn lại và index đã có vector cho metric đó.

Compiler tiếp tục đăng ký binding từ cả hai bộ định nghĩa. Thêm kiểm thử cho allowlist canonical trên catalog mặc định và phân biệt catalog hash theo chế độ. Các test M0.2 được giữ nguyên. Số lỗi giảm từ 8 xuống 0.

## Lệnh và kết quả cuối

| Lệnh | Exit | Kết quả |
| --- | ---: | --- |
| `.venv/bin/python -m ruff check agent4/core/catalog.py agent4/sql/compiler.py agent4/planning/planner.py` | 0 | Qua |
| `make format-check lint typecheck PYTHON=.venv/bin/python CHECK_PATHS='<7 tệp Python của lượt tương thích>'` | 0 | 7 tệp đúng format, lint và compileall qua |
| `.venv/bin/python -m pytest tests/contracts/test_intake_auth_catalog.py tests/contracts/test_compiler_safety_execution.py tests/contracts/test_governed_pipeline.py -v` | 0 | 62 qua |
| `.venv/bin/python -m scripts.check_warehouse` | 0 | 44 cặp metric/view trên MPX10 v3 |
| `.venv/bin/python -m scripts.check_mpx10` | 0 | 29 kết quả catalog, 70 golden case, 5 kịch bản khớp |
| `.venv/bin/python -m pytest -q tests/contracts/test_canonical_metric_bindings.py` | 0 | 10 qua, gồm BM-119/BM-120 với cả ID canonical và M0.2, kết chuyển/mở sổ, quyền alias, làm tròn và mẫu số 0 |
| `.venv/bin/python -m pytest -q tests` | 0 | 523 qua |
| `git diff --check` | 0 | Qua |

Trong lượt triển khai ban đầu, ba lỗi catalog/E0 cố định kích thước danh sách cũ ở 15 định nghĩa hoặc 13 metric hiển thị. Ba lỗi clarification/retrieval kỳ vọng candidate M0.2 khi allowlist không chỉ định alias. Hai lỗi recovery mong mở rộng tập candidate bằng `cash_balance` khi không chỉ định allowlist. Các kỳ vọng M0.2 này hiện đều qua với chế độ tương thích mặc định. Các lượt pytest cuối chạy với quyền kết nối HTTP cục bộ để hoàn tất test tích hợp trong môi trường hiện tại.

## Benchmark

Baseline `M4.3_governed_dev_lexical` dùng preset `config/eval_governed_lexical.yaml`, 140 ca dev từ `contract-benchmark-v2.0`, seed `20261101`, model `qwen2.5:0.5b@a8b0c5157701`, prompt `metric-selection-v1-structured` và warehouse MPX10 v3. SHA-256 dataset `094fb090bff62ee8c83045eed3780c371ec3f4cf38095f274237c02a6b5b88d5`. SHA-256 config `cfc4197eb34a88379d9b68c3dc65175d1e8f2ad3b84c479cdb8f329899c2fa41`.

```bash
AGENT4_WAREHOUSE_TENANT_ID=minh-phat AGENT4_METRIC_SELECTION_CONFIG=config/eval_governed_lexical.yaml \
  make eval PYTHON=.venv/bin/python ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION=qwen2.5:0.5b@a8b0c5157701 PROMPT_VERSION=metric-selection-v1-structured \
  EVAL_CONFIG=config/eval_governed_lexical.yaml OUTPUT_DIR=reports/eval/M1-P0-1_governed_dev_lexical \
  BASELINE=reports/eval/M4.3_governed_dev_lexical/summary.json
```

Runner ghi đủ 140 dự đoán và xác nhận baseline tương thích. Runner thoát 1 do 10 ca được phân loại `runtime_failure`, nên `make eval` thoát 2. Không có ngưỡng chất lượng được cấu hình.

| Chỉ số | Baseline | M1-P0-1 |
| --- | ---: | ---: |
| Invalid metric trong dự đoán được ghi | 72/140 (51,4%) | 0/140 |
| Chọn metric chính xác | 49/140 | 79/140 |
| Plan chính xác | 28/140 | 45/140 |
| SQL thực thi thành công | 50/50 | 53/53 |
| Trạng thái E2E chính xác | 80/140 | 80/140 |
| Ca runtime failure | 15 | 10 |
| P50 / P95 (140 mẫu mỗi lượt) | 1,456 / 2,053 giây | 1,788 / 2,257 giây |
| Token trung bình quan sát được | 607 trên 117 mẫu | 722 trên 116 mẫu |
| Chi phí USD và đối soát độc lập | Chưa đo | Chưa đo |

- BM-119 và BM-120 đều chọn `operating_expenses`, qua SQL safety và thực thi thành công. Cả hai trả `no_data` vì không có dòng khớp trên MPX10 v3, trong khi nhãn chờ `ready`. Hai ca đã được loại khỏi bộ golden v3 vì phụ thuộc dữ liệu v2.1. BM-120 còn sai khoảng thời gian vì plan chỉ lấy tháng 9 thay vì từ đầu năm đến hết tháng 9.
- BM-004, BM-073, BM-106 và BM-132 bị validator từ chối với `unknown_metric` trước khi trả danh sách metric cho bộ chấm. Vì vậy, tỷ lệ invalid metric của dự đoán được ghi là 0, trong khi validator vẫn chặn bốn lựa chọn có ID lạ. BM-025 và BM-033 trộn flow và snapshot. BM-042, BM-050, BM-054 và BM-065 chọn thêm metric làm plan không tương thích.
- Cổng xác minh của lượt tương thích đã qua. Độ chính xác trạng thái E2E và các ca lệch dữ liệu/thời gian vẫn cần được xem xét trước khi dùng kết quả benchmark để quyết định phát hành.

[Baseline](../eval/M4.3_governed_dev_lexical/summary.json) · [Kết quả lượt chạy](../eval/M1-P0-1_governed_dev_lexical/summary.json) · [Kết quả từng ca](../eval/M1-P0-1_governed_dev_lexical/cases.jsonl)
