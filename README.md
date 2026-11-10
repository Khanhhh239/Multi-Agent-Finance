# Văn phòng kế toán số: bốn agent trong một web

Nhánh `platform-Khanh` ghép bốn agent vào một giao diện. Có một hồ sơ doanh nghiệp, một nơi nạp tệp, rồi bốn khung agent. Code của từng agent giữ nguyên trong thư mục riêng.

| Thư mục | Lấy từ nhánh | Việc của agent |
|---|---|---|
| `agent1/` | `agent1-Khanh` | Dòng tiền: dự báo thu chi theo tuần, kịch bản, xuất Excel |
| `agent2/` | `agent2-Khanh-sosoat` | Soát giao dịch: luật cứng, luật xác suất, đồ thị quan hệ, túi phương pháp ML |
| `agent3/` | `agent3-core-adapt` | Thuế GTGT: đọc hóa đơn XML, đối chiếu sao kê và bảng kê, căn cứ điều luật |
| `agent4/` | `Agent4` (thư mục `agent4`) | Hỏi đáp số liệu: câu hỏi tiếng Việt thành truy vấn đã kiểm tra trên kho chỉ đọc |
| `agent4_chat/` | mới | Khung chat cho Agent 4, để riêng cho nhóm Agent 4 tự chỉnh |
| `portal/` | mới | Web chung: cấu hình, nạp dữ liệu, bật tắt và hiển thị các agent |

Commit ghép là một subtree merge có đủ bốn nhánh làm cha, nên lịch sử của từng nhánh vẫn còn. Mỗi nhánh gốc không bị sửa.

## Chạy

Mỗi agent cần môi trường Python riêng như README của agent đó. Portal chỉ dùng thư viện chuẩn của Python.

1. Chép `portal/config.example.json` thành `portal/config.local.json`. Khai báo `python` cho agent nào không có `.venv` trong thư mục của nó.
2. Chạy:

```powershell
python portal/server.py --start-all
```

3. Mở http://127.0.0.1:8800. Nút Ctrl+C dừng portal và các agent do portal bật.

Cổng mặc định: portal 8800, Agent 1 là 8011, Agent 2 là 8766, Agent 3 là 8640, Agent 4 là 8040. Đổi trong `config.local.json`.

## Luồng dùng

1. **Cấu hình doanh nghiệp**: tên, mã số thuế, mã dùng chung, phương pháp thuế, kỳ kê khai, định dạng ngày và số tiền trong tệp. Nhãn bên phải mỗi ô cho biết agent nào dùng ô đó.
   - Agent 1 và Agent 2 dùng mã dùng chung. Đổi mã thì portal khởi động lại Agent 1 với kho của mã mới.
   - Agent 1 nhận mã doanh nghiệp, định dạng ngày và số tiền qua hồ sơ riêng của mã đó. Các giá trị hiện trong Agent 1 và áp dụng cho cả tệp nhập lẫn tệp mẫu; chỉnh tại cấu hình chung rồi kiểm tra lại tệp. Sau khi cập nhật code này, khởi động lại portal và Agent 1 một lần để bật kết nối hồ sơ.
   - Agent 3 tạo doanh nghiệp theo mã số thuế. Lần đầu cần mật khẩu quản trị Agent 3. Portal chuyển mật khẩu cho Agent 3 rồi đăng xuất ngay, không lưu lại.
   - Agent 2 chỉ nhận tệp cho doanh nghiệp đã có trong danh mục của nó. Ô "Mã doanh nghiệp ở Agent 2" dùng khi mã khác mã chung.
2. **Nạp dữ liệu**: thả tệp vào một ô. Portal nhận dạng từng tệp và chạy bước xem trước của agent nhận. Một tệp sao kê chung được chuẩn hóa cho cả Agent 1 và Agent 3. Chưa có gì được ghi ở bước này. Xem [hướng dẫn demo và tệp mẫu](DEMO.md).
   - Bảng mẫu Agent 1 (hóa đơn, tiền về, khoản chi, sao kê, kỳ sao kê, hứa trả) đi tới Agent 1.
   - Sổ giao dịch theo mẫu Agent 2 đi tới Agent 2.
   - Hóa đơn XML, ZIP, sao kê ngân hàng và bảng kê cổng thuế đi tới Agent 3. Agent 3 tự phân loại lại.
3. Bấm **Ghi vào agent**. Với tệp của Agent 2, nút hỏi xác nhận lần hai vì Agent 2 thay toàn bộ giao dịch cũ. Sau mỗi lần ghi, portal kiểm tra lại các tệp còn chờ. Ví dụ tiền khách trả bị lỗi tham chiếu sẽ qua sau khi hóa đơn đã ghi.
4. Mở **Agent 1 đến 4** ở menu trái. Mỗi agent hiện trong cùng khung. Agent 1 tự nhận khóa kết nối từ portal qua `postMessage`, không cần dán khóa. Bấm **Mở tab riêng** ở Agent 1 cũng tự kết nối đúng doanh nghiệp bằng mã dùng một lần, hết hạn sau 60 giây. Khóa chỉ giữ trong bộ nhớ của tab; nếu tải lại tab riêng thì mở tab mới từ portal hoặc nhập khóa để kết nối lại.

## Thay đổi nhỏ trong code agent

Chỉ ba chỗ, mặc định giữ nguyên hành vi cũ:

| Tệp | Thay đổi |
|---|---|
| `agent1/agent1_service/workspace/api.py` | `frame-ancestors` lấy từ `AGENT1_FRAME_ANCESTORS`; không đặt thì vẫn là `'none'` |
| `agent1/agent1_service/ui/workspace/app.js` | Khi nằm trong khung, nhận khóa từ trang cha (chỉ chấp nhận `127.0.0.1` hoặc `localhost`) và giữ trong bộ nhớ như khóa gõ tay |
| `agent2/sme_fraud/review_server.py` | `frame-ancestors` lấy từ `SOSOAT_FRAME_ANCESTORS`; không đặt thì vẫn là `'none'` |

## Đã kiểm tra trên máy (08/11/2026, dữ liệu mô phỏng)

- Bốn agent bật từ portal và hiện trong khung chung. Agent 1 tự kết nối và thấy 12.780 hóa đơn vừa nạp.
- Nạp 13 tệp một lượt: 6 CSV Đại Phát tới Agent 1, 6 tệp demo Sao Việt tới Agent 3 (Agent 3 ghi nhận 22 tệp: 17 hóa đơn mua vào, 3 bán ra, 1 sao kê, 1 bảng kê), 1 sổ giao dịch 90 dòng tới Agent 2.
- Lần ghi đầu, 3 tệp Agent 1 báo lỗi tham chiếu đúng như dự kiến. Portal kiểm tra lại sau khi ghi hóa đơn và sao kê, lần ghi thứ hai đạt.
- Agent 4 trả lời 5 câu gợi ý có bảng và nguồn.

## Giới hạn

- Agent 4 đọc kho dữ liệu demo sinh bằng `python -m agent4.datagen.build`, chưa nhận tệp và chưa dùng hồ sơ doanh nghiệp.
- Doanh nghiệp tạo ở Agent 3 qua portal chưa có các quy định chi tiêu gợi ý mà trình tạo của Agent 3 đánh dấu sẵn. Thêm trong trang Quản trị của Agent 3 nếu cần.
- Trang Agent 3 chưa tự chọn doanh nghiệp vừa tạo. Chọn ở ô "Chọn doanh nghiệp" trong khung Agent 3.
- Bộ demo lớn của Agent 2 cần thêm cột danh mục (`self_approval_limit_vnd`, `registered_at`...) thì mới nhận tệp nhập. Portal không tự sửa danh mục của Agent 2.
- Portal phục vụ trên máy cục bộ, không có đăng nhập riêng. Không mở ra mạng ngoài.
