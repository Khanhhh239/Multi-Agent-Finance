# Agent1 · Trợ lý dòng tiền cho doanh nghiệp

Workspace local để nạp sổ kế toán, chọn mô hình theo lịch sử doanh nghiệp và lập kế hoạch thu chi. Kỳ dự báo tùy chọn **1–52 tuần**, mặc định **13 tuần**. Có kịch bản thu chậm, biến động chi, rủi ro theo khách và xuất Excel ba sheet.

## Bắt đầu

Yêu cầu Git, Python 3.12 và PowerShell. Nếu đã clone nhánh `agent1-Khanh`, bắt đầu từ lệnh tạo `.venv`.

```powershell
git clone --branch agent1-Khanh --single-branch https://github.com/Khanhhh239/Multi-Agent-Finance.git
cd Multi-Agent-Finance
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-service.txt
.\scripts\start-business.ps1 -Port 8011 -Company SME
```

Mở **http://127.0.0.1:8011/workspace**. Khóa kết nối nằm trong `.state-business-keys/api-token.txt`. Với doanh nghiệp có mã khác, script in đúng đường dẫn thư mục khóa trên màn hình khởi động.

## Thử toàn bộ luồng bằng Đại Phát

```powershell
.\scripts\start-business.ps1 -Port 8012 -Company DEMO_DAIPHAT -DemoTraining
```

Mở **http://127.0.0.1:8012/workspace#data** và kết nối bằng khóa trong `.state-business-firm-DEMO_DAIPHAT-data-keys/api-token.txt`. Nạp sáu CSV từ [pilot/demo_dai_phat](pilot/demo_dai_phat) theo thứ tự số. Chọn ngày trong file `yyyy-mm-dd` và số tiền `plain`. Giao diện và Excel hiển thị `dd-mm-yy`.

| Thao tác | Giá trị diễn tập |
|---|---|
| Ngày chốt kiểm định và dự báo | `31-10-26` |
| Số dư đầu kỳ | `425000000` VND |
| Ngưỡng cảnh báo | `200000000` VND |
| Chạy gốc | 13 tuần, Kế hoạch gốc |
| So sánh | Chạy gốc 26 tuần rồi chọn Thu chậm thêm 28 ngày |

Hướng dẫn có **12 bước và 13 ảnh web**, gồm nhập file, xem điểm, chọn phiên bản, thử kịch bản và xuất Excel. [Đọc PDF mới nhất](docs/06_Pilot/pdf/So-tay-Agent1.pdf) · [Bản Markdown](docs/06_Pilot/SO_TAY_AGENT1.md).

Dữ liệu Đại Phát là synthetic. Bản huấn luyện minh họa có Brier 4 tuần 0,0949 so với mốc 0,1341 trên 82 hóa đơn audit. Khoảng tin cậy cải thiện chứa 0. Xem [bằng chứng và giới hạn](docs/HANDOFF.md).

## Người nhận bàn giao

| Nơi đọc | Nội dung |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | Kiến trúc, luồng dữ liệu, cấu hình, kiểm tra và phần còn thiếu |
| [agent1_service/README.md](agent1_service/README.md) | API, phân quyền, phục hồi và dịch vụ nghiên cứu |
| [docs/06_Pilot/pdf/So-tay-Agent1.pdf](docs/06_Pilot/pdf/So-tay-Agent1.pdf) | Thực hành cho kế toán và người vận hành |
| [pilot/demo_dai_phat](pilot/demo_dai_phat) | Sáu CSV mô phỏng, manifest và file lỗi để thử nhập liệu |
| [docs/06_Pilot/RA_SOAT_WORKSPACE_DONG_TIEN.md](docs/06_Pilot/RA_SOAT_WORKSPACE_DONG_TIEN.md) | Đối chiếu yêu cầu sản phẩm và các tính năng còn thiếu |

## Kiểm tra

```powershell
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
.\.venv\Scripts\python.exe -m pytest tests/adaptive -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

GRU/LSTM và Chronos dùng phụ thuộc tùy chọn trong `requirements-forecast.txt`. Chỉ cài khi cần kiểm định nhánh chuỗi tiền mở rộng. MLP hóa đơn dùng scikit-learn. `AGENT1_DL_DEVICE` mặc định `cpu`. Chronos cần thư mục trọng số local `AGENT1_CHRONOS_DIR`.

## Cấu trúc

```text
agent1/adaptive/          Học, kiểm định và dự báo riêng theo doanh nghiệp
agent1_service/workspace/ API workspace, worker, xuất Excel, phục hồi
agent1_service/ui/        Giao diện và tài nguyên dùng local
scripts/start-business.ps1 Điểm khởi động trên Windows
scripts/business/        Sinh demo, kiểm tra và dựng tài liệu
pilot/demo_dai_phat/      Dữ liệu diễn tập đã gắn mã DEMO_
docs/06_Pilot/pdf/        PDF bàn giao mới nhất
tests/adaptive/          Kiểm thử luồng SME
agent1/models/           Mô hình và thí nghiệm nghiên cứu
```

Các tài liệu nghiên cứu nằm trong thư mục `docs/01_…` đến `docs/05_…`. Đọc [chỉ mục nghiên cứu](docs/00_INDEX.md) và [cổng nghiệm thu](docs/03_Evaluation/GATES_CURRENT.md) khi làm việc với pipeline nghiên cứu.

## Vận hành và dữ liệu riêng

Tác vụ lớn cần ít nhất **3 GiB RAM hệ thống trống** trước khi bắt đầu. Worker giữ giới hạn RSS mặc định 2 GiB. Huấn luyện không giới hạn tổng thời gian, tiến độ cập nhật mỗi 15 giây. Để máy và dịch vụ hoạt động trong lúc học.

Workspace demo tự tạo mật khẩu báo cáo ngẫu nhiên trong thư mục khóa nếu chưa có. Báo cáo HTML mã hóa được lưu dưới `outputs/private-training-reports/`. Có thể đổi thư mục bằng `AGENT1_REPORT_DIR`. Khóa API, mật khẩu, CSDL và trọng số do máy nhận tạo riêng. `.gitignore` loại các file này khỏi Git.

Luồng nghiên cứu T0/T9/T1 đã tích hợp lõi đối soát từ agent1-Thắng cùng lịch sử quan sát có duyệt. Xem mục “Luồng T0–T9 thống nhất” trong [tài liệu dịch vụ](agent1_service/README.md). Workspace SME dùng các endpoint `/v1/` riêng và cùng kho lưu mã hóa.
