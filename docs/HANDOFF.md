# Bàn giao Agent1 · 07-11-26

## Chạy từ repo

Đọc README ở thư mục gốc để tạo `.venv`, cài `requirements-service.txt` và chạy `scripts/start-business.ps1`. Cổng 8011 dùng cho SME, cổng 8012 dùng cho DEMO_DAIPHAT với `-DemoTraining`. Script tạo CSDL và khóa theo doanh nghiệp trên máy nhận.

Bộ thực hành có 12.780 hóa đơn, 120 khách, 17.642 giao dịch, 16.258 phân bổ, 142 kỳ sao kê, 27 lịch chi và 5.001 sự kiện. Nạp theo thứ tự tên sáu CSV trong `pilot/demo_dai_phat/`. Chọn ngày trong CSV là `yyyy-mm-dd`, số tiền là `plain`. Form và Excel dùng `dd-mm-yy`. [PDF thực hành](06_Pilot/pdf/So-tay-Agent1.pdf).

## Luồng mã

```text
agent1_service/main.py → create_app() trong agent1_service/api.py
  ├─ /workspace                 → giao diện local
  ├─ /v1/imports/preview        → ghép cột và kiểm tra
  ├─ /v1/imports/{id}/commit    → lưu snapshot dữ liệu mã hóa
  ├─ /v1/training              → worker → train/validation/audit → phiên bản
  ├─ /v1/models/{id}/activate   → chọn phiên bản phục vụ
  ├─ /v1/predict               → dự báo, mô phỏng, lưu kế hoạch
  └─ /v1/forecasts/{id}/xlsx    → Excel của bản đã lưu
```

| Module | Trách nhiệm |
|---|---|
| `agent1/adaptive/data.py` | Schema CSV/XLSX, ánh xạ, kiểm tra, snapshot as-of và hash |
| `agent1/adaptive/methods.py` | T1, lưới cấu hình, ensemble có neo, dự báo và mô phỏng |
| `agent1/adaptive/risk.py` | T2 xóa nợ ghi nhận trong 365 ngày từ phát hành |
| `agent1/adaptive/collections.py` | Chọn quy tắc xếp hạng theo metric giá trị top 10 |
| `agent1/adaptive/operating.py` | Chọn chuỗi tiền từ lịch sử sao kê đã đối soát |
| `agent1/adaptive/new_credit.py` | Thu hóa đơn bán chịu sắp phát hành, tách khỏi công nợ mở |
| `agent1/adaptive/cash_history.py` | Đối chiếu sao kê, phân bổ thu từng phần, hiệu chỉnh dải |
| `agent1/adaptive/training_report.py` | HTML báo cáo AES-GCM, mở bằng mật khẩu |
| `agent1_service/workspace/` | Route workspace, worker tách biệt, xuất Excel và phục hồi |
| `agent1_service/ui/workspace/` | HTML/CSS/JS, thư viện local kèm giấy phép |

Luồng nghiên cứu mới trên `agent1-Khanh` có T0/T9/T1 dùng lịch sử quan sát đã duyệt và lõi đối soát từ nhánh Thắng. Workspace SME hiện lưu bảng dạng `company_*` và dùng các endpoint `/v1/`. Việc nối toàn bộ hàng chờ duyệt nghiên cứu sang workspace là phần còn cần hoàn thiện.

## Quy tắc kiểm định

T1 học đến T−112 ngày. Chọn phương pháp và tỷ trọng trên cohort phát hành trong (T−112, T−84], với nhãn đến T−56. Audit cohort phát hành trong (T−56, T−28], nhãn đến T. Cổng hiện tại chấp nhận khi Brier trung bình không kém lịch sử khách. Sau đó refit bằng dữ liệu đã biết đến T. Khách được gom cụm khi bootstrap khoảng tin cậy.

T2 dùng hóa đơn đã đủ 365 ngày quan sát. Tập học và validation chờ nhãn trước gốc sau. Chọn Brier so prior, audit rồi refit. Nhãn là sự kiện xóa nợ được ghi nhận, không suy từ việc chưa trả.

Chuỗi hoạt động xét ba cửa sổ validation 13 tuần và một cửa sổ audit. Kỳ dự báo có thể 1–52 tuần. Nhánh hoạt động và bán chịu mới chỉ đóng góp tối đa 13 tuần đầu. Các tuần sau tính công nợ mở và lịch chi đã biết. So kịch bản chỉ khi cùng phạm vi và ngày chốt.

## Cấu hình cần biết

| Biến hoặc file | Tác dụng |
|---|---|
| `AGENT1_STATE_DIR`, `AGENT1_KEY_DIR` | Kho dữ liệu và thư mục khóa riêng |
| `AGENT1_FIRM_ID` | Doanh nghiệp của tiến trình |
| `AGENT1_AGENT4_TOKEN`, `AGENT1_VIEWER_TOKEN` | Quyền đọc dự báo đã lưu |
| `AGENT1_TRAIN_MIB` | Giới hạn RSS worker, mặc định 2048 MiB |
| `AGENT1_ISOLATE_TRAINING=1` | Ép worker riêng cho job nhỏ |
| `AGENT1_NEURAL_MAX_ITER`, `AGENT1_NEURAL_BATCH_SIZE` | Mặc định 100 vòng và batch 128 |
| `AGENT1_DL_DEVICE` | Thiết bị GRU/LSTM, mặc định CPU |
| `AGENT1_CHRONOS_DIR` | Thư mục trọng số Chronos đã có trên máy |
| `AGENT1_REPORT_DIR` | Thư mục báo cáo riêng, mặc định `outputs/private-training-reports/` ở script demo |
| `report-password.txt` trong thư mục khóa | Mật khẩu mở báo cáo, tạo ngẫu nhiên lần đầu nếu thiếu |

Worker cập nhật tiến độ mỗi 15 giây và không cắt theo tổng thời gian. Job lớn cần RAM hệ thống trống ≥3 GiB trước khi chạy. Giữ máy và dịch vụ hoạt động. Khôi phục checkpoint sau mất điện chưa được triển khai.

## Tài liệu và file sinh

- `docs/06_Pilot/SO_TAY_AGENT1.md` là nguồn sổ tay. Ảnh thật nằm trong `agent1_service/ui/workspace/manual/img/`.
- Cài `Markdown` vào môi trường Python rồi chạy `python scripts/business/build_handbook.py` để dựng HTML offline và hướng dẫn trên web. Để in lại PDF, cài Node.js, Microsoft Edge và `npm install --no-save --package-lock=false playwright`, rồi chạy `node scripts/business/print_handbook.cjs`. PDF được lưu tại `docs/06_Pilot/pdf/So-tay-Agent1.pdf`.
- `python scripts/business/check_large_demo.py` kiểm tra sáu bảng, lỗi có chủ đích và các kịch bản xem trước. Chạy từ thư mục repo.
- `python scripts/business/make_large_demo.py` tái tạo dữ liệu synthetic và dữ liệu xem trước. Lưu thay đổi dữ liệu thử trước khi tái tạo.
- `outputs/`, `tmp/` và các thư mục `.state*` chứa file chạy trên máy. Bộ dữ liệu thật, parquet, token, mật khẩu, trọng số đã học và báo cáo riêng không đi kèm bản bàn giao.

## Bằng chứng và phần còn thiếu

Bộ kiểm thử sau khi ghép với nhánh nghiên cứu: 692 đạt, 2 bỏ qua, 0 lỗi với `pytest tests -q`.

Phiên bản minh họa Đại Phát đã đánh giá 16 cấu hình hóa đơn cùng một ensemble, gồm 3 neural, và 6 ứng viên/ensemble chuỗi tiền. Brier audit T1 0,0949 so với mốc 0,1341 trên 82 hóa đơn. Khoảng tin cậy cải thiện chứa 0. Lượt minh họa dùng neural 25 vòng/batch 512 và mất 138,84 giây. Cấu hình mặc định hiện tại đã trở lại 100/128. Mô hình học, token và báo cáo riêng do máy nhận tự tạo.

Rủi ro cần đọc theo phạm vi hiện có là nhãn xóa nợ thiếu, lịch chi chưa đầy đủ và độ phủ dải tiền chưa có bằng chứng trên SME thật. Những việc tiếp theo gồm gợi ý đối soát có duyệt, lịch chi định kỳ, kiểm định rolling-origin số dư và tác động thu hồi sau liên hệ. [Rà soát theo yêu cầu sản phẩm](06_Pilot/RA_SOAT_WORKSPACE_DONG_TIEN.md).

## Checklist nhận bàn giao

1. Cài môi trường và chạy workspace từ checkout mới.
2. Kết nối bằng khóa do máy nhận tạo, nạp đủ sáu CSV Đại Phát.
3. Kiểm tra 6 khoản chờ ghép tổng 42 triệu, giữ lại khi chưa xác định hóa đơn.
4. Tạo phiên bản ngày 31-10-26, đọc điểm audit, kích hoạt phiên bản.
5. Lập gốc 13 tuần với 425 triệu đầu kỳ và ngưỡng 200 triệu.
6. Lập gốc 26 tuần, chạy thu chậm 28 ngày, kiểm tra chênh lệch.
7. Xuất Excel ba sheet và mở báo cáo HTML bằng mật khẩu trong thư mục khóa.
8. Chạy `pytest tests/adaptive -q`, sau đó `pytest tests -q`.
