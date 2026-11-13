# Bộ kiểm thử Agent 1

Chạy từ thư mục gốc repo, nơi chứa `agent1/` và `.venv/`:

```powershell
.\.venv\Scripts\python.exe -m pytest agent1/tests -q
.\.venv\Scripts\python.exe -m pytest agent1/tests/adaptive -q
node --test agent1/tests/adaptive/portal_connect_ui.test.cjs agent1/tests/adaptive/t1_explanations_ui.test.cjs agent1/tests/adaptive/t6_cash_ui.test.cjs
```

Pytest chạy các file `test_*.py`; ba file `.test.cjs` chạy bằng Node.js. Các test trình duyệt Python tự bỏ qua nếu thiếu Playwright hoặc Chrome. Test PowerShell cần PowerShell 7; một số nhánh mô hình dùng phụ thuộc tùy chọn như Torch. Test XML trên world `tgt` bỏ qua khi chưa sinh dữ liệu đó.

`conftest.py` ở gốc cung cấp đường dẫn import, giới hạn CPU và fixture tài khoản ngân hàng. `adaptive/conftest.py` cung cấp phần kiểm tra môi trường trình duyệt, proxy qua `TestClient` và cách nạp Portal có hỗ trợ import các mô-đun cạnh `server.py`. Mỗi test vẫn dùng app, client và kho dữ liệu riêng; Portal đọc cấu hình mẫu và ghi vào thư mục tạm.

## Các file đã gộp ngày 11/11/2026

Các ca kiểm thử được chuyển nguyên nội dung vào nhóm tương ứng, bỏ file nhỏ và import lặp:

| File cũ | Nơi chạy hiện tại |
| --- | --- |
| `test_cluster_ratio.py` | `test_cluster.py` |
| `test_pchip_reference.py` | `test_t1_math.py` |
| `test_promise_outcome_visibility.py` | `test_features.py` |
| `test_ingest_dates.py` | `test_ingest_service.py` |
| `test_rules_business_cases.py` | `test_rules_regression.py` |

Hai ca short-pay dừng do default và hết thời gian quan sát dùng chung một test tham số hóa trong `test_short_pay_lifecycle.py`, vẫn kiểm riêng hai kết quả `writeoff`/`open`. Bốn ca trình duyệt dùng chung fixture thay cho bốn bản sao proxy và kiểm tra Chrome.

Hai đoạn nạp Portal trong test kết nối và hồ sơ công ty cũng đã gộp vào fixture `portal_module`, thay cách nạp thiếu đường dẫn cho `bank_intake`. Dữ liệu test stress dòng tiền có `expense_id`; test xuất Excel kiểm cả hai sheet T5 theo đầu ra hiện tại.

Các test cho phiên bản v4/v5/v6, nghiên cứu và script lịch sử vẫn kiểm tra mã còn tồn tại, nên được giữ. Tên phiên bản cũ hoặc file chỉ có một test chưa đủ để kết luận không còn dùng. `__pycache__/` và `.pyc` là cache có thể xóa; không phải ca kiểm thử.

Kiểm tra ngày 11/11/2026: 165 ca Python liên quan và 51 ca Node.js đạt. Lượt chạy toàn bộ trước đó thu thập đủ 896 ca trong khi workspace đang thay đổi song song; tất cả các ca lỗi ở lượt đó đã được kiểm tra lại và đạt sau khi sửa phần thiết lập test hoặc cập nhật kỳ vọng T5. Chưa chạy lại toàn bộ sau các sửa cuối.
