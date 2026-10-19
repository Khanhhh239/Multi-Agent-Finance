# Hướng dẫn cho AI làm việc trong repository

Áp dụng cho toàn repo. Đây là hướng dẫn hành động; kiến thức chi tiết nằm trong các tài liệu được liên kết. Giữ file ngắn, chỉ cập nhật khi quy tắc làm việc thay đổi.

## Trước khi sửa

1. Đọc [tổng quan hiện tại](docs/project-overview.md), [cấu trúc repo](docs/reference/repository-structure.md) và phần liên quan của [Contributing](docs/CONTRIBUTING.md).
2. Kiểm tra working tree; giữ nguyên thay đổi có sẵn của người dùng. Đọc code thực tế trước khi dựa vào báo cáo hoặc output notebook.
3. Xác định nguồn nội dung chính theo bảng trong `docs/CONTRIBUTING.md`. Không tạo báo cáo hoặc README mới nếu có trang phù hợp để sửa.

## Nguyên tắc bắt buộc

- **Thay đổi codebase phải cập nhật tài liệu bị ảnh hưởng trong cùng thay đổi.** Nếu không ảnh hưởng tài liệu, nêu lý do cụ thể khi bàn giao; không sửa hàng loạt file chỉ để thay ngày.
- **Một nội dung chi tiết có một nơi duy trì chính.** Các nơi khác dùng liên kết. Chỉ nhắc lại ngắn các ràng buộc quan trọng cho tính đúng đắn và thao tác.
- **Không dùng thông tin tương lai làm feature.** Xác định thời điểm biết thông tin, cutoff, nhãn và censoring cho từng task; với T1, xem [hợp đồng dữ liệu T1](docs/reference/t1-data-contracts.md).
- **Phân biệt thiết kế, kết quả lịch sử và kết quả đã kiểm chứng.** Không gọi audit gate là tập train hoàn chỉnh, hoặc tự nhận đã train/đạt SOTA khi chưa có bằng chứng.
- Giữ dữ liệu gốc và provenance; không sửa raw để làm đẹp chất lượng. Không đưa credential hoặc dữ liệu riêng tư vào Git. Field công khai không tự xác nhận quyền tái sử dụng dữ liệu.

## Quy ước sửa mã và notebook

- Dùng đường dẫn theo gốc repo hoặc `__file__`; không ghi đường dẫn máy cá nhân. Giữ thay đổi đúng phạm vi yêu cầu, tránh refactor không liên quan.
- Notebook 11/12 có nguồn chính là `.py`; quy trình đồng bộ và trường hợp chưa thể dựng lại nằm ở `docs/CONTRIBUTING.md`. Với 01–10, sửa trực tiếp `.ipynb`.
- Không chạy train hoặc dựng lại output chỉ để kiểm tra tài liệu. Không xóa output/artifact lịch sử ngoài phạm vi công việc.
- Nguồn ngoài phải có URL, ngày kiểm tra và giới hạn sử dụng; số liệu thí nghiệm phải gắn với snapshot/cấu hình/artifact. Đọc hướng dẫn tại `data/`, `notebooks/`, `research/references/` khi chạm vào phần tương ứng.

## Kiểm tra trước khi kết thúc

Chạy từ gốc repo, không cần dependency mô hình:

```powershell
python scripts/checks/check_docs.py
python -m unittest discover -s tests -v
```

Nếu sửa logic dữ liệu hoặc mô hình, chạy thêm kiểm tra phù hợp theo `docs/CONTRIBUTING.md`; hai lệnh trên không xác minh logic tài chính hay chất lượng dự báo.

Bàn giao phải nêu: đã đổi gì, tài liệu đã cập nhật, kiểm tra đã chạy và giới hạn chưa giải quyết. Nếu thiếu dữ liệu/dependency khiến không thể kiểm tra, ghi rõ; không báo đạt thay cho phần chưa chạy.
