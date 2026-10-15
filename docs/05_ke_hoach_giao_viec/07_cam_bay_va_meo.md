# Cạm bẫy và mẹo

## Môi trường
1. **Không chạy `python -I`**: chế độ cô lập bỏ thư mục hiện tại khỏi đường dẫn; thiết lập `PYTHONPATH` là thư mục gốc kho.
2. Hệ thống Python trên máy phát triển đã bị xóa; dùng môi trường ảo riêng.
3. pandas 3: `groupby().rolling()` đổi hình dạng chỉ mục. Mọi mã dùng nó phải kiểm bằng phép tính vét cạn như `test_memory_features_match_bruteforce_and_are_causal`.
4. Đọc tệp CSV có BOM bằng `encoding="utf-8-sig"`.
5. Băm tệp đóng băng phụ thuộc ký tự xuống dòng; đặt `git config core.autocrlf false` hoặc kiểm băm sau khi chuyển hệ điều hành.
6. Trên PowerShell, `Remove-Item` với ký tự đại diện có thể bị chặn; xóa bằng Python.

## Dữ liệu
7. Mã định danh lặp giữa các thế giới (`T000000001`, `C001`); luôn thêm tiền tố khi gộp (xem `eval_v4.prepare`).
8. Hai tập lệnh sinh từ chối ghi đè thư mục không rỗng; xóa thư mục thủ công khi cần sinh lại.
9. `loss_vnd` trong dữ liệu tổng hợp thấp hơn ACFE hàng chục lần; không dùng cho kinh tế.
10. `features.csv` (190 cột) do mã của bạn bạn tính từ `transactions.csv`; nếu sửa giá trị tiền phải tính lại bằng `sme_fraud/rebuild_features.py`.
11. Đừng đọc `labels.csv`/`truth_cases.csv` trong bất kỳ bước chấm điểm nào.

## Phương pháp
12. AP trong cùng phân phối là vòng tròn; hãy nhìn P2, P3, bỏ-một-kịch bản và niêm phong.
13. Autoencoder làm kênh Novelty đẩy báo nhầm trên 20%; dùng làm đặc trưng thì tốt hơn.
14. Mô hình hai tầng chưa có lợi; đừng đưa vào sản phẩm nếu H3 không đổi kết quả.
15. Precision@B3 thấp (khoảng 4,5%) là do tỷ lệ nền và công ty không có vụ; đừng "sửa" bằng cách giảm B mà không xem recall.
16. `ghost_employee` chưa bị bắt khi chưa thấy; không hứa bắt được.
17. Tham số hạn mức tự duyệt, ngưỡng duyệt là giả định; đừng gắn cứng vào đặc trưng.

## Quy trình
18. Chạy thí nghiệm dài bằng tiến trình tách rời (`Start-Process`) và lưu JSON sau mỗi giao thức: phiên làm việc có thể bị ngắt giữa chừng và làm mất tiến trình con.
19. Đặt tiêu chí **trước** khi chạy, ghi vào nhật ký, rồi mới xem kết quả.
20. Khi một ý tưởng thất bại, **ghi lại** (như hai tầng, autoencoder trong Novelty).
21. Khi thấy kết quả "quá tốt" (AP trên 0,8), tìm vòng tròn trước khi ăn mừng.
