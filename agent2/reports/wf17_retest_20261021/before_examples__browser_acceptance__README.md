# Bản nghiệm thu trình duyệt riêng

Chạy từ thư mục gốc dự án:

```powershell
& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe' -B examples/browser_acceptance/run_demo.py --port 8771
```

Mở [hàng đợi 001/003](http://127.0.0.1:8771/) và [đối chứng P2](http://127.0.0.1:8771/p2-controls). [Checklist và tiêu chí](../../reports/browser_acceptance_20261019/checklist.md); [39 mẫu mở nhanh](../../reports/browser_acceptance_20261019/samples.md).

Lần đầu, script phục hồi bản sao đã kiểm chứng sang `.runtime/browser_acceptance_20261019/demo`; các lần sau mở lại bản này và giữ lịch sử nghiệm thu. Bản sao nguồn là `.runtime/backup_restore_20261019/final/backup_live_demo`, phải có và tương thích runtime. Không có chế độ ghi đè hoặc tự xóa để làm lại.

Nhật ký P2 riêng nằm ở `.runtime/browser_acceptance_20261019/p2_uat.sqlite3`. Không kế thừa kết quả “đạt” của lần rà trước; mọi mục trong phiếu browser ban đầu còn chờ. Bộ nguồn/kết quả P2 đã khóa chỉ được đọc. Bản demo giữ đủ 1.211 hồ sơ và 3 yêu cầu/6 sự kiện mô phỏng từ bản sao, không tạo sẵn kết luận để giả nghiệm thu.

Thông báo chỉ dry-run, không có người nhận, cấu hình dịch vụ gửi hoặc worker tự chạy. Các thao tác thử phải gắn `SIM_BROWSER_UAT`; trợ lý không ký thay kế toán độc lập. Ngân sách rà/ngày vẫn áp dụng như sản phẩm.

Nếu cổng đang dùng, chọn cổng khác và cập nhật đường dẫn trong phiếu; không dừng một dịch vụ chưa xác định. Đóng bằng Ctrl+C ở tiến trình chạy script. Khi thay code nằm trong hợp đồng runtime, phải chuẩn bị gói tương thích trước khi khôi phục; script không làm migration hoặc tự sửa manifest để vượt kiểm tra.
