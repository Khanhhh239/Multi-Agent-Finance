# Nhập dữ liệu và xem kết quả — CR-024

Mở **http://127.0.0.1:8800/#agent2** qua [phiên Portal chung](PORTAL_AUTH.md). Khi chạy mode Portal, địa chỉ 8766 trực tiếp sẽ hướng dẫn quay về Portal. Màn hình mới dùng các API snapshot đã có; không dùng giao diện hoặc dữ liệu cũ.

## Dùng thử

1. Đăng nhập/mở khóa Portal, rồi chọn Soát giao dịch. Agent2 tự nhận phiên, không cần mã local. Danh sách doanh nghiệp lấy từ quyền hiện hành; không tự nhập vai trò hoặc doanh nghiệp ngoài quyền.
2. Chọn doanh nghiệp, chọn tệp **JSON UTF-8** theo hợp đồng 1.0 hoặc 1.1, bấm **Kiểm tra tệp**. Hiện chưa nhận CSV/Excel. Tệp tối đa 10 MB.
3. Xem lỗi, cảnh báo và **Phần chưa đủ nguồn**. Lỗi chỉ rõ bảng, dòng bản ghi, trường và cách sửa; dòng JSON là dòng trong văn bản khi có lỗi cú pháp. Lỗi chặn lưu. Thiếu nguồn phân tích có thể được lưu nhưng chưa thể kết luận phần đó. Mở “Cần bổ sung gì?” để xem giao dịch và yêu cầu nguồn.
4. Đánh dấu đã xem kết quả, bấm **Xác nhận lưu**. Hệ thống tạo snapshot bất biến, không ghi đè các bản cũ. Nếu mất phản hồi, thử lại trên chính màn hình này; mã yêu cầu được giữ nguyên để chống trùng.
5. Chọn thời điểm dùng nguồn đã biết đến, theo **giờ Việt Nam UTC+07**, bấm **Xem kết quả kiểm tra**. Mỗi giao dịch có lý do, nguồn đối chiếu và bước tiếp theo. Nhóm thanh toán đồng thời xuất hiện riêng một lần.

Nút **Đổi doanh nghiệp hoặc tệp** quay lại bước nhập và bỏ kết quả kiểm tra cũ. Tệp thay đổi trên máy phải chọn và kiểm tra lại. Nút **Nhập tệp khác** bắt đầu lần nhập khác. Sau tải lại trang, phiên Portal còn hiệu lực tự khôi phục snapshot gần nhất trong tab; kết quả được chạy lại bằng quyền và thời điểm đã chọn. Chế độ local độc lập cần kết nối lại.

## Tệp mẫu

Tải **Tệp mẫu C001** trên màn hình, hoặc dùng `sme_fraud/web/import-demo.json`. Mẫu thuộc tenant `demo`, doanh nghiệp `C001`, chỉ dùng với quyền tương ứng. Chọn thời điểm **30/10/2026 09:00:00** hoặc sau đó.

Có 5 giao dịch mô phỏng: khoản trước OLD 4 triệu; A/B cùng thời điểm, mỗi khoản 4 triệu trên hóa đơn 10 triệu; OVER thêm 1 triệu; MISSING thiếu kênh/liên kết. Danh mục có hai tên NCC tương tự. Khi đủ thời điểm, có đủ 5 dòng kết quả, một kiểm tra nhóm A/B và phần chưa đủ nguồn của MISSING. Không dùng mẫu để chứng minh độ chính xác hoặc gian lận thật.

## Hiểu trạng thái

| Trạng thái | Ý nghĩa và thao tác |
|---|---|
| Cần đối chiếu | Có dấu hiệu theo kiểm tra đang chạy; xem chứng từ trước khi kết luận. |
| Chưa đủ nguồn | Chưa tính được kiểm tra. Bổ sung đúng nguồn; không hiểu là số 0 hoặc không có vấn đề. |
| Chưa thấy tín hiệu | Kiểm tra đã chạy trên nguồn khả dụng và chưa phát hiện dấu hiệu đó. Chưa xác nhận giao dịch hợp lệ. |
| Không áp dụng | Kiểm tra không áp dụng cho loại giao dịch này. |

Một giao dịch có thể vừa cần đối chiếu ở một kiểm tra, vừa thiếu nguồn ở kiểm tra khác. Bộ lọc “Đủ nguồn, chưa thấy tín hiệu” loại các dòng còn cảnh báo/thiếu nguồn. Căn cứ ghi rõ mô phỏng hay bản xuất nguồn; bản xuất chưa tự là chứng từ gốc đã xác minh.

Mã snapshot/checksum xác định bản dữ liệu đã lưu; mã lần kiểm tra và thời điểm xác định kết quả đang xem. Phân tích có thể chưa thấy giao dịch nếu chọn thời điểm trước khi nguồn đó được biết.

## Phạm vi hiện tại

- Màn hình dùng view=review cho bốn nhánh theo [CR-027](FOUR_BRANCH_ANALYSIS.md). Hai đối chiếu luật P1/E3 hiện có giữ nguyên; thống kê/ML chỉ dùng artifact đã fit và ghim riêng DN, graph trả quan hệ có căn cứ. Chưa đánh giá toàn bộ luật, tạo hồ sơ hoặc gửi vào hàng đợi.
- Phân tích đồng bộ tối đa **200 bản ghi giao dịch / 1.000 bản ghi nguồn**. Preview cảnh báo nếu vượt; backend từ chối phân tích, không tự cắt lịch sử. Tệp vẫn có thể được lưu nếu hợp lệ.
- Đã nối phiên workspace Portal theo CR-025. Portal dùng X-Session hiện hữu từ sessionStorage; Agent2 không trả secret bridge xuống browser. Tham chiếu snapshot/thời điểm ở agent2.workbench không chứa dữ liệu giao dịch. Portal chưa có tài khoản cá nhân riêng. Chế độ local độc lập vẫn chỉ giữ mã truy cập ở bộ nhớ trang.
- Không có quyền mặc định. Nếu chưa được cấp mã/quyền hoặc backend chưa có auth policy/kho snapshot, màn hình báo lỗi và không lưu.

## Vận hành local độc lập (tùy chọn)

Từ `D:\agent22\agent2`, dùng **policy do quản lý cấp** và **kho snapshot mới riêng**:

```powershell
& .venv/Scripts/python.exe -X utf8 -u -B start_review.py --port 8766 --auth-file <policy.json> --snapshot-db <snapshots.sqlite3>
```

Khi chạy độc lập bằng --auth-file, policy/kho/mã phía client nằm riêng trong `.runtime/live_check_20261111/` (bị gitignore). Người vận hành đã được phép có thể sao chép mã mà không in ra terminal:

```powershell
(Get-Content .runtime/live_check_20261111/client.json -Raw | ConvertFrom-Json).token | Set-Clipboard
```

Dán vào ô **Mã truy cập**, bấm **Kết nối**. Mã có hạn; không đưa các tệp này lên Git. Mã này chỉ dùng với --auth-file. Chế độ Portal đang chạy không nhận mã local làm fallback; dùng hướng dẫn PORTAL_AUTH.md ở trên.

## Kiểm thử

Backend: `scripts/run_r1_tests.py --report <report.json>`. UI acceptance dùng Chrome thật, HTTP và SQLite tạm, chỉ dữ liệu mô phỏng:

```powershell
& .venv/Scripts/python.exe -m pip install -r requirements-ui-test.txt
& .venv/Scripts/python.exe -X utf8 -B scripts/test_import_workbench_ui.py --output-dir <thu-muc-evidence>
```

`playwright` chỉ là dependency kiểm thử tùy chọn; backend không cần cài để chạy. Cần Chrome đã cài. Không dùng hồ sơ Chrome cá nhân khi kiểm thử.
