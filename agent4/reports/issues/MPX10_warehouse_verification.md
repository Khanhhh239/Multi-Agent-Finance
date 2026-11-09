# Nghiệm thu tích hợp kho MPX10

Ngày 09/11/2026. Nguồn là `data_pipeline/` của `platform-Khanh` tại commit
`2991a5354391e7c5174479c8516fa202174d929e`. Dùng DuckDB 2.0.0, profile
`minh_phat_enterprise_x10`, data version `3.0.0`, seed `20261108`. Ngày chốt
là 14/10/2026 và tháng khóa sổ cuối là 08/2026.

Giả thuyết tích hợp là kho mới giữ schema các quan hệ mà catalog M0 sử dụng.
So sánh trực tiếp qua `information_schema.columns` cho thấy cả 114 định nghĩa
cột của `v_gl`, `v_mgmt`, `v_tax` và `budget` khớp với v2.1. Giữ kho v2.1
cho benchmark cố định và chuyển mặc định của `AppConfig` sang kho MPX10.

| Kiểm tra | Kết quả |
| --- | --- |
| Sinh MPX10 đầy đủ | Exit 0 sau 201,3 giây ở bước build. File DuckDB 2.333.618.176 byte. Có 19.784.697 dòng sổ cái, 5.110.372 chứng từ sổ cái, 1.302.000 hóa đơn bán và 183.999 hóa đơn mua. |
| Đối soát nguồn trên kho đầy đủ | Exit 0. Pass 32/32 kiểm tra và 5/5 tình huống. Chênh lệch AR, AP và tồn kho đều bằng 0. Bút toán lệch 1.000 VND có nhãn. |
| SQL catalog M0, cùng phiên bản code và kỳ kiểm tra | v2.1 chạy 29/29 cặp metric/view trong 0,05 giây. MPX10 chạy 29/29 trong 0,49 giây. Thời gian đo một lần tại máy local. |
| Full metric baseline | 56/66 metric trong `CatalogSnapshot` thực thi thành công. 10 metric giữ trạng thái `unsupported_by_existing_engine`: `budget_vs_actual`, `cash_conversion_cycle`, `cash_coverage_days`, `cash_flow_breakdown`, `dio`, `dpo`, `dso`, `expense_spikes`, `unusual_account_movements`, `upcoming_obligations`. Không có metric nào ở trạng thái `error`. |
| Baseline hiệu năng đơn truy vấn | Trên cùng máy và cùng 56 metric được hỗ trợ, v2.1 mất 0,217 giây tổng cộng, p50 3 ms và max 12 ms. MPX10 mất 4,304 giây tổng cộng, p50 45 ms và max 539 ms. Đây là đo smoke một lần, chưa phải benchmark đồng thời. |
| Kiểm tra tái lập | Hai lần chạy profile thu nhỏ đều pass validator. SHA-256 logic của 5 bảng khớp nhau. |
| Hồi quy repo | 275 test pass trước tích hợp. 276 test pass sau tích hợp, gồm một test mới cho override đường dẫn. |
| Static checks | Compile và Ruff trong phạm vi M0/M1 cùng script mới pass. Baseline toàn repo đã có 12 file sai format và 13 lỗi lint ngoài phạm vi tích hợp. |

Lệnh xác minh chính, chạy từ `agent4` với `PLATFORM_CHECKOUT` trỏ đến
checkout riêng của commit nguồn.

```bash
.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/enterprise.py" --out data/enterprise-x10-v3
make test-warehouse PYTHON=.venv/bin/python
make test-warehouse PYTHON=.venv/bin/python AGENT4_DB=data/cfo_warehouse.duckdb
.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/validate.py" data/enterprise-x10-v3
make typecheck test-core test-selection test-security PYTHON=.venv/bin/python
PYTEST_ADDOPTS='-o addopts=' make test PYTHON=.venv/bin/python
make format-check lint PYTHON=.venv/bin/python \
  CHECK_PATHS='agent4/core agent4/metric_selection scripts/check_warehouse.py tests/contracts/test_intake_auth_catalog.py tests/contracts/test_metric_selection_e0.py tests/contracts/test_retrieval_and_fewshot.py tests/contracts/test_selection_and_metric_validation.py tests/contracts/test_metric_selection_recovery.py'
git diff --check
```

Các lệnh trên trả exit 0. Đối với kiểm tra tái lập, chạy cùng lệnh build với
`--smoke` ở hai thư mục trống khác nhau rồi chạy validator trên cả hai và so
sánh `logical_hashes`. Kết quả kho đầy đủ nằm trong
`data/enterprise-x10-v3/validation.json`. Script upstream xuất kết quả
ground truth vào báo cáo đó. README có lệnh tách danh sách sang tệp JSON mà
`AppConfig` trỏ tới.

Catalog M0 chạy 13 metric có handler đã xác minh theo các view được cấp quyền.
Catalog đầy đủ của M1 có 66 metric và dùng metadata để chọn và xác thực metric.
Số 56/66 đến từ compiler tham chiếu của `platform-Khanh`. Compiler đó có
56 handler được phê duyệt và đánh dấu 10 metric là chưa hỗ trợ.
Các test end-to-end cũ
dùng fixture v2.1 và test harness. Chất lượng Ollama, SQL từ câu hỏi tự nhiên
và tính tái lập của lần build đầy đủ vẫn nằm ngoài bằng chứng của lần tích
tích hợp kho này. Kích thước kho làm thời gian truy vấn tăng rõ rệt. Với timeout
5 giây hiện tại, số đo đơn truy vấn vẫn dưới ngưỡng, nhưng trước khi bật tải
đồng thời nên có benchmark p95/p99, cold-cache và nhiều nhóm truy vấn. Nếu
những số đo đó vượt ngưỡng sản phẩm, ưu tiên tối ưu view, phân vùng hoặc
materialization trước khi sửa công thức metric.

  ## Bộ tham chiếu và lệnh nghiệm thu M0/M1

`data/eval/mpx10-v3-reference.json` đóng băng kết quả của snapshot MPX10
v3.0.0, seed 20261108, với 19.784.697 dòng GL. Baseline chứa 29 kết quả
metric/view từ code M0. Golden rows chứa 321 dòng từ 70 truy vấn tham chiếu
đã lưu trong fixture v1. Hai bộ benchmark hiện có giữ nguyên nhãn.

Trong 85 ca v1 có SQL, loại 15 ca phụ thuộc sự kiện, mã đối tác, giả định
doanh thu bằng 0 hoặc phạm vi chiều của v2.1. Danh sách ID nằm trong
`scripts/check_mpx10.py`. BM-108 được giữ để kiểm tra dữ liệu quý II/2023
mới có trong MPX10. Truy vấn trả doanh thu thuần 2.436.086.331.033 VND.
Fixture MPX10 ghi kết quả SQL. Chấm độ chính xác kết quả số trên benchmark
v2 vẫn cần review độc lập theo `docs/evaluation.md`.

| Lệnh hoặc phép kiểm tra | Exit | Kết quả |
| --- | ---: | --- |
| `.venv/bin/python -m scripts.check_mpx10 --write-reference data/eval/mpx10-v3-reference.json` | 0 | Sinh baseline M0 và golden rows từ DuckDB chỉ đọc. |
| `.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/validate.py" data/enterprise-x10-v3` | 0 | 32/32 kiểm tra và 5/5 tình huống pass. Đã xuất lại ground-truth JSON từ báo cáo theo README. |
| `.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/metric_baseline.py" data/enterprise-x10-v3` | 0 | Tạo lại baseline tham chiếu platform. 56 thực thi, 10 chưa hỗ trợ và 0 lỗi. |
| `make test-mpx10 PYTHON=.venv/bin/python` | 0 | 15 test M0, 92 test M1, 29 kết quả catalog, 70 ca SQL và 5 tình huống khớp. |
| `AGENT4_DB=data/cfo_warehouse.duckdb .venv/bin/python -m scripts.check_mpx10` | 1 | Từ chối đúng snapshot v2.1. |
| `make format-check lint typecheck CHECK_PATHS='scripts/check_warehouse.py scripts/check_mpx10.py' PYTHON=.venv/bin/python` | 0 | Ruff và compile pass sau khi sửa cách nối chuỗi SQL trong tuple. |
| `make test PYTHON=.venv/bin/python PYTEST_ADDOPTS='-o addopts='` | 0 | 276 test pass, bao gồm fixture v2.1. |

Lệnh nghiệm thu chạy offline. M1 dùng phản hồi LLM giả lập. Phần kiểm tra
SQL phát lại truy vấn tham chiếu trên warehouse. Phép đo này chưa bao gồm
chất lượng mô hình, chi phí LLM hoặc độ chính xác end-to-end.
