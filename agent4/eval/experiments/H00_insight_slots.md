# Step 0a — insight slots

**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở). G0.7 OPEN / CHƯA ĐẠT.

Model chọn 1–2 enum slot từ danh sách tất định (caveat, biggest_group, direction_vs_comparison nếu có). Prompt chọn slot không chứa giá trị, mô tả chứng từ hay tên đối tác. JSON có số hoặc câu tự do bị từ chối. Câu nhận xét được render bằng template và vẫn qua verifier.

| Cấu hình | n | Đúng M1 | Bare-facts fallback | Gọi model | Token vào/ra | p50/p95 giây |
|---|---:|---:|---:|---:|---:|---:|
| M1 diễn giải tự do | 10 | 10/10 | 7/10 | 36 | 31702/1680 | 4.109/6.622 |
| Chọn slot | 10 | 10/10 | 0/10 | 20 | 15129/414 | 1.461/12.958 |

Nguồn: `docs/5_handoff/measurements/m1-third/` và `p2-slots-after/`. Không kiểm soát cold/warm model nên không suy ra cải thiện p95; câu đầu lượt sau có tải model. Target fallback <10% đạt trên **tập dev nhỏ này**; chưa đo trên val. Không dùng 10 câu này trong metric P2. Bootstrap trên n=10 và 0 lỗi cho khoảng suy biến [0,0], không chứng minh rủi ro bằng 0; khoảng Wilson 95% của fallback 0/10 là [0%,27.8%].

Lỗi quan sát: 23 lần NUMERIC_COMMENTARY ở baseline; 2 lần cũng có UNSUPPORTED_NUMBER; lượt slot không có insight_invalid, lỗi khối sự kiện hoặc model unavailable. Không bịa thêm 10 lỗi khi tập này không có đủ: 10 ví dụ lỗi/ca kiểm sẽ được cung cấp trong từng thí nghiệm T2.6 trên val, không phải phép sửa dev này.

Quyết định: dùng slot cho đường hybrid; giữ test JSON độc/khóa lạ/số tự do, và baseline tự do chỉ tồn tại trong nhánh thí nghiệm cô lập. Không có công cụ ghi, không giả lập duyệt kế toán.
