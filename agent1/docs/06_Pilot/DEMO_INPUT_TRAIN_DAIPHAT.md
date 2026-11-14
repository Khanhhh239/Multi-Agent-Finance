# Đại Phát · Đầu vào diễn tập

Dữ liệu synthetic cho kho `DEMO_DAIPHAT`, không là doanh nghiệp thật hoặc benchmark độc lập. Từ thư mục `agent1/`, chạy:

```powershell
.\scripts\start-business.ps1 -Port 8012 -Company DEMO_DAIPHAT -DemoTraining
```

Mở `http://127.0.0.1:8012/workspace`. Dùng khóa do launcher trên máy nhận tạo và in vị trí; không đưa khóa vào tài liệu. Cách thao tác chung nằm trong [sổ tay](SO_TAY_AGENT1.md).

## Nạp sáu file theo thứ tự

Lấy tệp gốc trong `pilot/demo_dai_phat/`. Chọn ngày ISO `yyyy-mm-dd`, số tiền `plain`, kiểm tra rồi xác nhận từng tệp.

| File | Bảng trên Workspace |
|---|---|
| `01_invoices.csv` | Hóa đơn bán hàng |
| `02_bank.csv` | Dòng sao kê ngân hàng |
| `03_payments.csv` | Khoản thanh toán đã nhận |
| `04_statements.csv` | Kỳ sao kê và số dư |
| `05_outflows.csv` | Lịch chi đã biết |
| `06_actions.csv` | Nhật ký thu nợ và lời hứa |

Quy mô/giả định nằm trong manifest đi cùng CSV. `invalid_cases/` chỉ dùng trên kho thử riêng để kiểm thông báo lỗi. Không nhập lại bằng mã mới để thử retry; cùng chứng từ giữ cùng ID.

## Tham số bài thực hành

Ngày dữ liệu tham chiếu `31-10-26`, số dư đầu `425000000 VND`, mức sàn `200000000 VND`, kỳ 13 tuần. Chỉ dùng cutoff nếu mọi thành phần model thực dùng đã học/sẵn sàng không sau ngày đó; catalog hiện tại có thể không đủ điều kiện cho cutoff lịch sử này. Không sửa ngày artifact để ép chạy. Nếu bị chặn, dùng bản lưu đúng phiên bản hoặc lập một ca diễn tập mới với dữ liệu/số dư/cutoff nhất quán.

Trong **Phiên bản & kiểm định**, xem nguồn phục vụ, ngày dữ liệu, ngày tham số và audit; cập nhật không bảo đảm đổi model. Mô tả học tiếp và chờ challenger ở [T1 + partial](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md). Không dùng điểm Brier hoặc số dư chụp từ phiên bản cũ làm đáp án cho engine mới.

Thực hành dự báo → mở lại kế hoạch → đọc bằng chứng partial/T10 → chạy kịch bản cùng snapshot → xuất Excel. Khi so kỳ 26 tuần, lập baseline 26 tuần trước; phạm vi hoạt động vẫn tối đa 13 tuần. Chấm thực tế chỉ khi có sao kê tương ứng; CSV dừng ở cutoff chưa cung cấp nhãn tương lai.
