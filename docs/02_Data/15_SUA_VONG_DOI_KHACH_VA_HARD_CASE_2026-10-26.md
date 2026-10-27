# Sửa vòng đời khách hàng và hai hard case (26/10/2026)

## Phạm vi

Báo cáo [kiểm toán trước sửa](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md) phát hiện doanh thu và số khách suy giảm ngay cả khi không thêm episode sốc; `heterogeneity` chỉ đạt 0,303 so với dải kiểm tra 0,55–0,65; `lumpy_customer` đọc tổng doanh thu của cả kỳ rồi sửa hóa đơn đã sinh. Các thư mục kiểm toán cũ được giữ nguyên. Bản sửa này tạo thế giới mới và không khóa bộ train cuối cùng.

## Cơ chế đã sửa

1. `make_customers` tạo một pool khách tiềm năng, khoảng 72% có thể mua từ đầu. `customer_activity` quyết định theo từng tuần: khách mới vào, khách tạm rời, khách quay lại. Xác suất chuyển trạng thái phụ thuộc thanh khoản hiện tại, tăng trưởng doanh nghiệp và stress cầu hiện tại. Các mức nền 0,25%/tuần rời đi và 0,8%/tuần gia nhập/quay lại **là giả định synthetic**, chưa phải ước lượng Việt Nam. Đơn hàng chỉ được sinh khi khách đang hoạt động và không bị giữ tín dụng. Trọng số doanh thu được chuẩn hóa một lần theo nhóm hoạt động ở tuần đầu; không dùng số khách hoặc doanh thu tương lai để chuẩn hóa từng tuần. Event ghi `customer_acquired`, `customer_churned`, `customer_returned`.
2. Vỡ nợ nay có thể tái diễn sau ít nhất 26 tuần hồi phục. Người bán dừng cấp tín dụng 26 tuần sau mỗi sự kiện; tín hiệu tín dụng xấu có thể giữ lâu hơn và hồi phục khi tín hiệu tốt. Hóa đơn chỉ chịu ảnh hưởng của **sự kiện vỡ nợ kế tiếp sau ngày lập**, nên lần vỡ nợ đã qua không làm nợ xấu mọi hóa đơn mới. Sự kiện sau ngày kết thúc quan sát bị loại. `customers.default_week/default_date` lưu **lần đầu** để tương thích; `events.parquet` là nhật ký đầy đủ các lần. `idio_sd` của khách nay tham gia phương trình thanh khoản.
3. `heterogeneity` chia khách thành bốn nhóm kỷ luật trả khác nhau, thay đổi logit đúng hạn, trung vị thanh toán trễ và lịch sớm nhất có thể thực hiện thanh toán muộn (0, 10 hoặc 30 ngày). Lịch này được gán trước khi sinh hóa đơn và chỉ đi vào thời điểm bắt đầu quá trình thanh toán theo tuần; không sửa kết quả sau khi biết ngày tiền về.
4. `lumpy_customer` gán anchor và trọng số trước khi sinh đơn. Anchor có hợp đồng mua dài hạn, các khách khác vẫn vào/ra. Xóa hẳn bước ép tỷ trọng dựa trên tổng doanh thu toàn kỳ. `weekly_booked_orders`, mua vào và tồn kho dùng cùng đơn đặt được sinh theo tuần. Dải 40–60% là kiểm tra trên nhiều công ty, không là cam kết cứng cho mọi lần rút ngẫu nhiên.

## Kết quả đo lại

Đối chứng không episode, dùng cùng cấu hình calibration/OxCGRT/WDI như phép kiểm tra trước, 24 công ty/seed, 2019–2025, RNG v2. Tất cả bộ mới qua `validate_world`, có manifest và hash. Các tỷ số dưới đây là doanh thu hóa đơn thuần năm 2025 chia 2019.

| Seed | Trước sửa, chỉ seed 94317 | Sau sửa | Khách có hóa đơn 2019 → 2025 | Nợ xấu theo giá trị bán chịu đã có kết cục, gộp kỳ |
|---|---:|---:|---:|---:|
| 94317 | 0,338 | 1,173 | 1.017 → 958 | 2,9% |
| 94318 | — | 1,443 | 1.215 → 1.277 | 5,4% |
| 94319 | — | 0,886 | 1.109 → 889 | 5,5% |

Seed 94317 ghi 383 khách mới, 1.085 lần rời tạm, 723 lần quay lại và 2.096 sự kiện vỡ nợ qua cả kỳ. Các seed khác cũng có cả ba luồng khách. Trên seed này, sự kiện vỡ nợ còn xuất hiện trong 2025 (285), thay vì giảm gần hết do giới hạn một lần/khách. Tỷ lệ nợ xấu của hóa đơn **phát hành trong 2025** vẫn bị kiểm duyệt phải và độ trễ xóa nợ, nên không dùng nó để hiệu chỉnh trực tiếp.

Hai hard case được sinh lại trên **12 công ty/case** với cùng mã vòng đời cuối:

| Case | Trước sửa | Sau sửa | Kết luận |
|---|---:|---:|---|
| `heterogeneity`: tỷ phần phương sai trễ giữa khách | 0,303 | **0,614** | Trong dải kiểm toán nội bộ 0,55–0,65. |
| `lumpy_customer`: số công ty có anchor chiếm 40–60% doanh thu | Có ép toàn kỳ | **12/12**, min 44,09%, median 47,82%, max 58,32% | Đạt trên mẫu kiểm; không đọc doanh thu tương lai. |

Mã tái lập: `scripts/audit_lifecycle_fix.py`. Kết quả có cấu trúc: `outputs/data/v5_lifecycle_audit_20261026.json` (ba đối chứng) và `outputs/data/v9_lifecycle_audit_20261026.json` (hai hard case). Dữ liệu và manifest ở `data/synthetic/v5_lifecycle_control_*`, `hc_heterogeneity_v9_lifecycle_20261026`, `hc_lumpy_customer_v9_lifecycle_20261026`. Các bản thử v4–v8 là lịch sử tuning, không dùng làm đầu vào train.

## Giới hạn và bước tiếp theo

Vòng đời không còn ép doanh thu giảm mạnh qua mọi seed, nhưng pool khách vẫn hữu hạn và các hazard gia nhập/rời/quay lại chưa ước lượng từ vi dữ liệu B2B Việt Nam. Tỷ lệ nợ xấu gộp giữa ba seed dao động 2,9–5,5%, còn phụ thuộc ngành, cửa sổ và kiểm duyệt; cần hiệu chỉnh theo cohort/năm/ngành và đo độ nhạy nhiều seed trước khi phát hành train. Cổng `build_final_train.py` còn yêu cầu một họ sốc chỉ xuất hiện trong test; thiết kế train/validation/test hiện chưa đáp ứng. Báo cáo này hoàn thành hai mục sửa mã được yêu cầu, **không xác nhận bộ train cuối cùng sát phân phối thị trường Việt Nam**.
