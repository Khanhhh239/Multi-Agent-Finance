# Chương trình chạy thử "Trợ lý Dòng tiền" — Dữ liệu cần doanh nghiệp cung cấp

> **Bản đề xuất chuẩn bị pilot, chưa phải chương trình đã được chấp thuận hoặc triển khai.** Trạng thái pilot thật hiện là [NO-GO](../03_Evaluation/GATES_CURRENT.md); rà soát lại điều kiện trước khi gửi bản này cho doanh nghiệp.

> Tài liệu gửi doanh nghiệp tham gia chạy thử. Bản 1.0, 24/10/2026. Đi kèm: **Cam kết bảo mật dữ liệu** (`02_CAM_KET_BAO_MAT.md`).

## 1. Chương trình là gì (một đoạn)

Chúng tôi đang thử một công cụ dự báo **13 tuần tới, tuần nào doanh nghiệp có thể thiếu tiền**, xác suất bao nhiêu, và **nên đòi khoản nào trước**.
Trong chạy thử, công cụ **chỉ ghi lại dự báo**, không gửi gì cho khách hàng của quý doanh nghiệp, không can thiệp vào phần mềm kế toán hay ngân hàng.
Sau 8 tuần, chúng tôi so dự báo với thực tế và gửi quý doanh nghiệp báo cáo.

**Quý doanh nghiệp nhận được (miễn phí trong chạy thử):**
- Báo cáo hằng tuần: dải số dư dự kiến 13 tuần (kịch bản tốt / giữa / xấu) và các hoá đơn nên ưu tiên thu.
- Báo cáo cuối chương trình: dự báo đã đúng/sai thế nào so với thực tế, tình trạng công nợ phải thu, khách trả chậm.
- Báo cáo chất lượng dữ liệu kế toán (hoá đơn trùng, thiếu, lệch số tiền...).

**Chúng tôi cần:** dữ liệu lịch sử để học thói quen trả tiền của khách, và dữ liệu cập nhật hằng tuần trong 8 tuần chạy thử.

## 2. Dữ liệu cần — mức tối thiểu (bắt buộc)

| # | Dữ liệu | Khoảng thời gian | Định dạng nhận được | Dùng để |
|---|---|---|---|---|
| 1 | **Hoá đơn điện tử đầu ra** (bán hàng) | **12–18 tháng gần nhất** | File **XML** gốc của hoá đơn điện tử (xuất từ hệ thống hoá đơn điện tử của nhà cung cấp hoặc cổng tra cứu) | Biết ai nợ bao nhiêu, hạn nào |
| 2 | **Sao kê tài khoản ngân hàng** (tất cả tài khoản nhận tiền khách hàng) | **Cùng kỳ với #1** | Excel/CSV xuất từ ngân hàng điện tử. Đọc sẵn mẫu của **Vietcombank, BIDV, Techcombank, ACB**; ngân hàng khác gửi kèm 1 dòng mô tả cột | Biết tiền về ngày nào, từ ai |
| 3 | **Số dư tài khoản ngân hàng đầu kỳ** | Ngày đầu của #2 | Một con số cho mỗi tài khoản | Điểm xuất phát dòng tiền |
| 4 | **Các khoản chi cố định đã biết** (lương, thuê, trả nợ vay, thuế...) | 12 tháng tới (nếu có) | Excel đơn giản: ngày, số tiền, loại | Dự báo tiền ra |

Mỗi file tối đa **10 MB**; nếu lớn hơn, chia theo tháng.

## 3. Dữ liệu nên có (giúp dự báo tốt hơn rõ rệt)

| # | Dữ liệu | Định dạng | Vì sao quan trọng |
|---|---|---|---|
| 5 | **Sổ chi tiết công nợ phải thu** (từ phần mềm kế toán) | Excel; tối thiểu các cột: số hoá đơn, mã khách, ngày hoá đơn, hạn thanh toán, số tiền | Biết hoá đơn nào đã được kế toán gạch nợ, giúp ghép tiền về với hoá đơn chính xác hơn |
| 6 | **Lời hứa trả tiền của khách** (nếu có ghi lại) | Excel: khách, hoá đơn, ngày hứa trả | Lời hứa giúp dự báo chính xác hơn khoảng 10–20% (đo trên dữ liệu mô phỏng) |
| 7 | **Hoá đơn điều chỉnh / thay thế / huỷ** | XML như #1 | Tránh tính nhầm công nợ |

## 4. Trong 8 tuần chạy thử

| Việc | Tần suất | Thời gian ước tính phía doanh nghiệp |
|---|---|---|
| Gửi sao kê ngân hàng tuần vừa qua + hoá đơn mới phát hành | 1 lần/tuần | 10–15 phút |
| (Không bắt buộc) Xác nhận 2–3 giao dịch mà hệ thống không tự ghép được | 1 lần/tuần | 5 phút |

Theo mô phỏng của chúng tôi, việc kế toán xác nhận **khoảng 3 giao dịch mỗi tuần** giúp giảm đáng kể cảnh báo nhầm. Đây là kết quả mô phỏng, chạy thử sẽ cho con số thật.

## 5. Không cần gửi

- Mật khẩu ngân hàng, mã OTP, quyền truy cập phần mềm kế toán — **không bao giờ yêu cầu**.
- Hợp đồng, hồ sơ nhân sự, bảng lương chi tiết theo người (chỉ cần **tổng** chi lương theo kỳ).
- Thông tin cá nhân của nhân viên.

## 6. Có thể che bớt trước khi gửi (nếu quý doanh nghiệp muốn)

Công cụ **không cần biết tên thật của khách hàng**, chỉ cần một mã nhất quán để nhận ra cùng một khách.
Quý doanh nghiệp có thể thay tên khách bằng mã (ví dụ KH001) **trên cả hoá đơn và sao kê, cùng một cách thay**.
Lưu ý: nội dung chuyển khoản (ví dụ "TT HD 0345") **nên giữ nguyên** vì đó là tín hiệu ghép tiền quan trọng nhất; chỉ che tên người nếu có.

## 7. Danh sách kiểm tra trước khi gửi

- [ ] XML hoá đơn đầu ra 12–18 tháng
- [ ] Sao kê tất cả tài khoản nhận tiền, cùng kỳ
- [ ] Số dư đầu kỳ từng tài khoản
- [ ] Danh sách chi cố định 12 tháng tới (nếu có)
- [ ] (Nên có) Sổ chi tiết công nợ phải thu
- [ ] Đã ký **Cam kết bảo mật dữ liệu** hai bên
- [ ] Đã thống nhất người liên hệ và kênh gửi file (khuyến nghị: thư mục chia sẻ có mật khẩu hoặc trao tay; **không** gửi qua email không mã hoá)

## 8. Thời gian

| Bước | Thời gian |
|---|---|
| Ký cam kết, gửi dữ liệu lịch sử | Tuần 0 |
| Chúng tôi nạp dữ liệu, gửi báo cáo chất lượng dữ liệu và dự báo đầu tiên | Trong 3 ngày làm việc |
| Chạy thử, báo cáo hằng tuần | Tuần 1–8 |
| Báo cáo tổng kết, xoá dữ liệu (nếu quý doanh nghiệp yêu cầu) | Tuần 9 |

Liên hệ: **[Họ tên, số điện thoại, email người phụ trách]**
