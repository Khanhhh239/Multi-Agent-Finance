# Đối chiếu độc lập BCTC doanh nghiệp niêm yết

Đọc ngày 20/10/2026. Chỉ dùng mô tả, không dùng để chỉnh máy phát.
Đầu vào chép từ trang PDF đã render trong `vn_listed_inputs.json`; mã tính
trong `scripts/run_vn_listed_check.py`. Kết quả và hash PDF ở
`outputs/data/vn_listed_accounting.csv`, so máy phát ở
`outputs/data/vn_listed_DSO_comparison.csv`. Chưa có người kiểm tra thứ hai.

- [SMC, BCTC hợp nhất 2024 tiếng Anh](https://smc.vn/wp-content/uploads/2025/05/BCTC-HOP-NHAT-SAU-KIEM-TOAN-2024-ENG.pdf):
  trang PDF 7/9/11 (trang in 5/7/9), đơn vị VND. Dùng bản lập 28/04/2025
  sau thông báo đính chính, lưu cả [hồ sơ đính chính](https://smc.vn/dinh-chinh-bao-cao-tai-chinh-nam-2024/).
  Trang PDF 6 có đoạn nhấn mạnh về khoản phải thu Novaland và bất định hoạt
  động liên tục; không coi đây là doanh nghiệp điển hình ngành thép.
- [TCM, BCTC hợp nhất kiểm toán 2022](https://www.thanhcong.com.vn/wp-content/uploads/2023/03/20230324-TCM-BCTC-hop-nhat-nam-2022-da-kiem-toan_VN.pdf):
  trang PDF 7/9/10 (trang in 5/7/8), VND, ý kiến kiểm toán ở trang PDF 6.
  Báo cáo thường niên 2024 tải được chỉ có ý kiến kiểm toán và dẫn đến
  website, không kèm đầy đủ các bảng. Vì vậy không gắn số năm 2022 thành 2024.
- [BMP, công bố báo cáo 2024](https://binhminhplastic.com.vn/co-dong/bctc/bctc-hop-nhat-nam-2024-da-kiem-toan):
  cả liên kết BCTC và báo cáo thường niên chính chủ trả HTTP403 khi tải.
  Chưa có số của ngành nhựa; không suy từ kết quả tìm kiếm.
  Sau đó bổ sung [báo cáo thường niên NTP 2024 chính chủ](https://admin.nhuatienphong.vn/img/posts/1_f2284364f5cd0dd5e057ecb4e3e165f0BCTN%202024.pdf),
  đọc bảng hợp nhất tại trang PDF 59–60, trang in 117–119, VND; ý kiến
  kiểm toán KPMG ở nửa trái trang PDF 59. NTP là mẫu nhựa độc lập,
  không được gắn số của NTP thành số của BMP.

DSO proxy = 365 × trung bình phải thu khách hàng ngắn hạn đầu/cuối năm /
doanh thu thuần. Phải thu là số gộp trước dự phòng, không phải tổng các
khoản phải thu bao gồm tạm ứng/cho vay. DPO proxy thay tử số bằng phải trả
người bán ngắn hạn và mẫu số bằng giá vốn; giá vốn khác giá trị mua chịu.
Chưa có bảng AP tổng hợp cùng định nghĩa để so DPO của máy phát.

Máy phát dùng số dư cuối năm, trừ tiền nhận thực tế đến ngày đó; tất toán
và xoá nợ đã xảy ra đưa về không, không trừ kết quả tương lai. Mẫu số gồm
doanh số net của mọi hoá đơn trong năm, kể cả COD, để gần định nghĩa BCTC.
Vẫn còn khác biệt VAT trong phải thu so doanh thu net, tỷ trọng tín dụng,
xoá nợ, mùa vụ và số dư chỉ hai thời điểm. Đây không phải DSO từ tuổi từng
hoá đơn hoặc thời gian trả trung bình.

Ba DN-kỳ ở hai năm khác nhau, một DN mỗi ngành, báo cáo hợp nhất của DN
lớn không đại diện SME. Không bootstrap ba DN này thành CI theo ngành,
nên không đặt cổng dung sai sau khi thấy số. Còn mẫu nhiều DN,
nhiều kỳ trước khi nghiệm thu WP-D4.4 đầy đủ. Dữ liệu thô giữ trong
`data/raw/vn_listed/`, có MANIFEST/SHA-256, không đưa vào Git.
