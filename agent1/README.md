# Agent 1 · Trợ lý dòng tiền doanh nghiệp

Workspace local cho nhập/đối soát sổ, dự báo thu chi 1–52 tuần (mặc định 13), giải thích, kịch bản và xuất Excel. Luồng hiện tại: T0/T9 → snapshot theo ngày biết → T1 global/học tiếp + partial → T5/T6 → forecast bất biến → T10 → đối chiếu thực tế.

Catalog mặc định là `outputs/t1/settlement_partial_catalog_v3_20261114/catalog.json`; có thể cấu hình bằng `AGENT1_T1_GLOBAL_CATALOG`. Cập nhật model và lập dự báo là hai thao tác riêng; chỉ đổi bundle khi qua audit hợp lệ. Synthetic và test phần mềm chưa chứng nhận chất lượng trên SME thật.

## Khởi động từ repository hiện tại

Từ thư mục gốc repository, dùng Python 3.12 và môi trường riêng:

```powershell
py -3.12 -m venv agent1/.venv
.\agent1\.venv\Scripts\python.exe -m pip install -r agent1/requirements-service.txt
.\agent1\scripts\start-business.ps1 -Port 8011 -Company SME
```

Launcher dùng `agent1/.venv/Scripts/python.exe`; nếu môi trường này đã có thì dùng lại. Mở `http://127.0.0.1:8011/workspace`. Launcher in đường dẫn khóa truy cập; khóa, DB và mật khẩu báo cáo được tạo riêng trên máy nhận. Với DN khác, dùng `-Company TEN_DN`, cổng/kho/khóa riêng.

Khi mở qua Portal, Workspace nhận kết nối từ trang cha; tab riêng dùng mã một lần rồi phiên cookie HttpOnly. Không lưu token vào localStorage/sessionStorage hoặc URL. Quy trình nạp chung của Portal và nạp trực tiếp Agent 1 là hai đường nhập; tránh nạp cùng chứng từ bằng ID khác.

## Sử dụng

1. Nạp và kiểm hóa đơn, bank, payments, statements, nghĩa vụ/thực trả T5 và actions khi có. T9 cần duyệt trước khi giảm công nợ; sửa/đảo giữ lịch sử.
2. Xác nhận đúng tài khoản và phạm vi thanh toán/lịch chi. Thiếu dữ liệu không coi là bằng 0.
3. Xem bundle đang dùng, nguồn global/học tiếp và audit. Cập nhật có thể giữ incumbent hoặc chờ nhãn challenger 91 ngày.
4. Lập kế hoạch, đọc kỳ vọng/P50/dải và nguy cơ thiếu tiền cùng giả định. Hoạt động tùy chọn chỉ tối đa 13 tuần; thu hóa đơn mới mặc định tắt.
5. Mở bằng chứng T10, chạy kịch bản từ snapshot đã lưu, xuất Excel và chấm khi có đủ thực tế.

[Sổ tay thao tác](docs/06_Pilot/SO_TAY_AGENT1.md) giữ hướng dẫn chi tiết. Để diễn tập, dùng kho riêng:

```powershell
.\agent1\scripts\start-business.ps1 -Port 8012 -Company DEMO_DAIPHAT -DemoTraining
```

Nạp sáu CSV theo [hướng dẫn Đại Phát](docs/06_Pilot/DEMO_INPUT_TRAIN_DAIPHAT.md); kiểm cutoff hợp lệ với ngày sẵn sàng của bundle. Không lấy kết quả demo cũ làm đáp án engine hiện tại.

## Đọc và phát triển

| Cần biết | Tài liệu |
|---|---|
| Pipeline và các hợp đồng hiện tại | [Pipeline đầu-cuối](docs/04_AI_Methods/01_pipeline_he_thong.md), [mục lục docs](docs/00_INDEX.md) |
| API/schema, bảo mật, Docker, phục hồi | [Dịch vụ](agent1_service/README.md) |
| Vị trí mã phục vụ | [Adaptive](agent1/adaptive/README.md), [mã nguồn](agent1/README.md) |
| Phát triển và kiểm chứng | [Quy trình](docs/05_Coding_Agent_Plan/README.md), [tests](tests/README.md), [scripts](scripts/README.md) |
| Dữ liệu và artifact | [Data](docs/02_Data/README.md), [outputs](outputs/README.md) |
| Pilot, UAT và nghiệm thu | [Chuẩn bị pilot](docs/06_Pilot/README.md), [bộ UAT](pilot/t0_t9_uat_20261110/README.md), [nghiệm thu](docs/03_Evaluation/03_cong_nghiem_thu.md) |

`agent1/adaptive/` và `agent1_service/workspace/` phục vụ `/v1`. `agent1/models/`, `experiments/` và các runner nghiên cứu còn caller riêng; không tự là model active. Dùng [bản đồ thí nghiệm](experiments/README.md) trước khi tái lập vì nhiều artifact/dữ liệu cũ đã dọn.

Không đưa kho doanh nghiệp, khóa, báo cáo riêng hoặc trọng số riêng vào Git. Job lớn và phụ thuộc tùy chọn theo cấu hình dịch vụ; kiểm tài nguyên trên máy đích. Việc đọc tài liệu không kích hoạt train, gửi nhắc nợ hoặc triển khai pilot.
