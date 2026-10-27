# Kiểm toán chỉ số trên ba World v5 đã có (26/10/2026)

> Báo cáo này giữ kết quả của ba World v5. Kiểm toán mở rộng trên đủ 10 World v5/v6, cùng định nghĩa chỉ số và bảng năm/ngành, nằm ở [báo cáo 19](19_KIEM_TOAN_CHI_SO_10_WORLD_2026-10-26.md). Các mục “chưa hoàn thành” bên dưới phản ánh thời điểm lập báo cáo ba World.

## Phạm vi và mẫu số

Chỉ đọc `v5_lifecycle_control_94317`, `94318`, `94319` (mỗi World 24 doanh nghiệp, 2019–2025, không có episode shock mới). Không sinh dữ liệu, chỉnh máy phát hay train. Mỗi World được kiểm manifest/hợp đồng dữ liệu trước khi tính. Mã: `scripts/audit_existing_world_metrics.py`; toàn bộ 147 dòng World × năm × ngành, gồm cả `ALL`, nằm trong `outputs/data/v5_existing_world_metrics_20261026.csv`.

- Doanh thu thuần, khách có hóa đơn và tỷ lệ bán chịu: **năm phát hành hóa đơn**; tỷ lệ bán chịu dùng giá trị gốc, không dùng số dòng.
- Thời gian trả: hóa đơn **bán chịu đã thu đủ trong năm**; ngày từ phát hành đến thu đủ, P50/P90 tính theo số hóa đơn. Tỷ lệ trả trễ theo **giá trị hóa đơn đã thu đủ trong năm**. Các khoản còn mở không đi vào phân phối này.
- Nợ quá hạn: **số dư công nợ còn mở và đã qua hạn tại 31/12**, sau các khoản thanh toán, credit note và xóa nợ có ngày không muộn hơn ngày chốt. Tuổi nợ tính từ ngày đến hạn; P50/P90 có trọng số theo số dư. Tỷ lệ nợ quá hạn dùng mẫu số là **toàn bộ công nợ còn mở**, khác tỷ lệ hóa đơn cuối cùng trả trễ.
- Số dư tiền: phân vị trên **ngày × doanh nghiệp** của `daily_cash.balance`, là tài khoản ngân hàng vận hành mô phỏng, không phải tổng tiền và tài sản thanh khoản của doanh nghiệp. Mỗi năm/World/ngành được tính riêng; không gộp mọi hóa đơn thành các quan sát độc lập.

Tái lập: `python scripts/audit_existing_world_metrics.py`. Công nợ tại 31/12/2025 được đối soát với `invoices.remaining_amount` (sai khác tối đa cho phép 1,01 VND mỗi hóa đơn).

## Kết quả tổng thể năm 2025

| Seed | Doanh thu thuần, nghìn tỷ VND | Khách có hóa đơn | Bán chịu theo giá trị | Kỳ hạn bình quân theo giá trị | Ngày phát hành → thu đủ P50/P90 | Trả trễ trong hóa đơn đã thu đủ, theo giá trị | Nợ quá hạn / công nợ mở 31/12 | Tuổi nợ quá hạn P50/P90 | Số dư tiền P10/P50, tỷ VND | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 94317 | 3,503 | 958 | 71,4% | 42,8 ngày | 42 / 120 ngày | 37,1% | 33,6% | 69 / 259 ngày | −2,47 / 6,46 | 19,3% |
| 94318 | 2,364 | 1.277 | 67,7% | 45,3 ngày | 43 / 118 ngày | 40,5% | 41,1% | 80 / 234 ngày | 0,41 / 6,63 | 6,6% |
| 94319 | 1,049 | 889 | 68,5% | 37,9 ngày | 44 / 176 ngày | 48,5% | 55,6% | 190 / 424 ngày | −1,26 / 4,26 | 13,6% |

Doanh thu 2025/2019 lần lượt là **1,173; 1,443; 0,886**. Số khách có hóa đơn 2019→2025 lần lượt **1.017→958; 1.215→1.277; 1.109→889**. Vì vậy lỗi suy giảm đồng loạt trước sửa không lặp ở cả ba seed, nhưng seed 94319 vẫn có giảm khách và đuôi thanh toán/nợ quá hạn đáng chú ý. Ba seed không đủ để ước xác suất suy giảm hoặc khoảng tin cậy.

Khoản quá hạn tại 31/12/2025 là **186,3; 153,9; 125,6 tỷ VND** tương ứng ba seed. Trong số dư quá hạn, tỷ phần đã quá hạn trên 60 ngày là **55,8%; 65,4%; 73,6%**. Đây là tồn kho công nợ tại ngày chốt, không phải tỷ lệ hóa đơn phát hành năm 2025 rốt cuộc trở thành nợ xấu.

## Phân tách theo ngành

Trung vị của ba kết quả theo seed trong năm 2025 (mỗi ngành chỉ có khoảng 2–5 doanh nghiệp/seed; xem CSV để kiểm từng seed):

| Ngành | Bán chịu theo giá trị | Thu đủ P50, ngày | Trả trễ theo giá trị đã thu đủ | Nợ quá hạn / công nợ mở | Tuổi nợ quá hạn P90, ngày | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|
| Thực phẩm | 65,5% | 30 | 35,1% | 31,4% | 278 | 0,5% |
| Nhựa, cao su | 69,9% | 57 | 51,5% | 43,1% | 251 | 5,6% |
| Dịch vụ | 62,1% | 41 | 42,4% | 44,7% | 243 | 0,8% |
| Thép, kim loại | 63,7% | 43 | 38,9% | 31,6% | 388 | 21,5% |
| Dệt may | 68,6% | 36 | 29,1% | 49,9% | 252 | 9,4% |
| Bán buôn | 73,1% | 45 | 38,2% | 34,3% | 284 | 3,6% |

## Đối chiếu và giới hạn

[Báo cáo 14](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md) dẫn khảo sát Atradius Việt Nam 2025 làm **neo gần đúng**: 65% doanh số bán chịu, kỳ hạn 45 ngày, 39% giá trị hóa đơn quá hạn và 3% nợ xấu. Dải 2025 của ba World là 67,7–71,4% bán chịu và 37,9–45,3 ngày kỳ hạn. Tỷ lệ **đã thu đủ nhưng trả trễ** 37,1–48,5% có mẫu số/cửa sổ khác tỷ lệ khảo sát; tỷ lệ **số dư đang quá hạn** 33,6–55,6% cũng khác định nghĩa. Không dùng sự gần nhau về con số để xác nhận phù hợp thị trường Việt Nam.

Khảo sát nói trên chỉ bao phủ một số ngành và người trả lời, không cung cấp phân phối vi mô hóa đơn/công nợ để kiểm P90 tuổi nợ hoặc số dư ngân hàng. Không có mốc Việt Nam cùng định nghĩa cho doanh thu/khách của 24 doanh nghiệp giả lập hay tỷ lệ ngày tài khoản vận hành âm. Tham số vòng đời và thanh toán vẫn do máy phát giả định; kết quả này là kiểm toán **nội bộ synthetic**. Các hóa đơn còn mở cuối kỳ bị kiểm duyệt phải, nên phân phối ngày thu đủ thiên về khoản đã tất toán; không được dùng để khẳng định toàn bộ hóa đơn trả nhanh.

Chưa hoàn thành: nhiều seed độc lập hơn, đối chiếu vi dữ liệu AR/AP Việt Nam, hiệu chỉnh theo cohort/ngành, kiểm tra shock held-out và cổng train cuối cùng. Kết quả audit này không thay đổi trạng thái **NO-GO** cho tuyên bố bộ train đã sát thị trường Việt Nam.
