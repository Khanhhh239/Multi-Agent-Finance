# Kiểm chứng HE và baseline bốn luật

**Kết quả kỹ thuật trong phạm vi HE hiện có. Baseline P1/E3/B5/E4 tính tại DN; E3/B5/E4 chưa có HE.**

| DN | Luật chọn / tối đa | Kết hợp / tối đa | ML bổ sung | Sai lệch điểm ML lớn nhất |
|---|---:|---:|---|---:|
| C001 | 3/5 | 5/5 | P1_T04, P1_T02 | 0.00005084 |
| C002 | 3/5 | 5/5 | P1_T04, P1_T02 | 0.00005092 |

P1 native FHE: 2/2 ca khớp nguyên số tiền và matched. ML CKKS dùng model đã fit riêng DN, chấm mới; tập lựa chọn không đổi. Có đổi thứ tự các điểm gần nhau trong dung sai, không có đảo cặp vượt dung sai.

Cùng nguồn/kỳ, tối đa 5 lượt mỗi phương án. E3/B5/E4 là master-quality, không tự tăng điểm/ưu tiên giao dịch. Còn 31 luật chưa nối snapshot. Dữ liệu mô phỏng, chưa có đánh giá hữu ích hoặc thời gian rà thực tế; không kết luận tăng độ chính xác.

T06/T07 là nhóm đồng thời, không đếm thành hai vụ gian lận độc lập. T04 là điều chỉnh âm, P1 không áp dụng. Không gửi dữ liệu rõ lên worker, không fit/model/khóa/quyền hay queue live bị thay đổi.
