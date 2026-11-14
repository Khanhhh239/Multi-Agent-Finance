# Kiểm chứng 35 luật tại node doanh nghiệp

Trạng thái: **passed**. 140 đối chiếu ca trúng/đối chứng, 70 kiểm tra thiếu nguồn. Dữ liệu mô phỏng; không phải độ chính xác gian lận.

| Luật | C001: trúng / đối chứng / thiếu nguồn | C002: trúng / đối chứng / thiếu nguồn |
|---|---|---|
| A1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| A2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| A3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| A4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| A5 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| A6 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B5 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B6 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| B7 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| C1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| C2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| C3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| C4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D5 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| D6 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| E1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| E2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| E3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| E4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| F1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| F2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| F3 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| F4 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| P1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| P2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| T1 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |
| T2 | Đạt / Đạt / Đạt | Đạt / Đạt / Đạt |

Nhóm D chấm theo tập/cutoff, F4 theo hóa đơn phải thu, E3/B5/E4 theo chất lượng master. E4 dùng alias B5 của engine, không cộng điểm lần hai. Chưa tính điểm tổng hoặc đưa kết quả vào queue.

Gói nguồn native này chạy tại DN. Hợp đồng snapshot 1.1.0 và phần HE Portal chưa được mở rộng bởi phép thử này. File nguồn/expected tách nhau; manifest ràng buộc checksum; không dùng expected để tạo feature hoặc quyết định luật.
