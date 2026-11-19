# Test tay nghiệp vụ và UI — Đại Phát

Toàn bộ dữ liệu là mô phỏng. Bộ CSV này được khôi phục nguyên vẹn từ bản chụp của phiên `20261118-091832-8e5f`, ngày dự báo 18/11/2026. Các tệp có mã băm và số dòng trong `manifest.json`.

## Chọn điểm bắt đầu

- **Tiếp tục phiên đã khôi phục:** mở http://127.0.0.1:8881. Phiên này đã nạp lịch sử, phát sinh mới và hoàn tất đối soát; bắt đầu ở bước 4, nạp lịch chi.
- **Test lại toàn bộ từ kho rỗng:** chủ động chạy `./agent1/pilot/demo_doanh_nghiep/Start-Demo.ps1 -Fresh` trong PowerShell ở gốc repo. Lệnh tạo phiên mới, giữ thư mục phiên cũ. Không dùng `-Preload` nếu cần test quy trình nạp trên UI.
- **Mở lại phiên hiện tại:** chạy `./agent1/pilot/demo_doanh_nghiep/Start-Demo.ps1` không thêm `-Fresh`.

Mỗi tệp: **Nạp dữ liệu chung → Chọn tệp → Kiểm tra tệp → Xác nhận → Ghi toàn bộ dữ liệu**. Đợi ghi thành công trước khi nạp tệp phụ thuộc tiếp theo. Với gói đã niêm phong, nhập lý do bổ sung ít nhất 10 ký tự.

## 1. Nạp lịch sử một lần

Nạp theo thứ tự trong `01_lich_su/`:

| Tệp | Số dòng | Nội dung |
| --- | ---: | --- |
| `01_invoices.csv` | 12.780 | Hóa đơn lịch sử |
| `02_bank.csv` | 17.642 | Giao dịch ngân hàng |
| `03_payments.csv` | 16.258 | Thanh toán đã phân bổ theo hóa đơn |
| `04_statements.csv` | 142 | Kỳ sao kê, số dư |
| `05_actions.csv` | 5.001 | Nhật ký thu nợ, lời hứa |

Lý do mẫu: `Bổ sung dữ liệu lịch sử Đại Phát đến ngày 31/10/2026.`

Bank dùng chung cần Agent 1 và Agent 3 cùng kiểm tra đạt. Không bỏ qua Agent 3 khi test nạp chung. Các thanh toán lịch sử đã có phân bổ không cần duyệt lại từng khoản.

## 2. Nối chứng từ mới

Nạp theo thứ tự trong `02_phat_sinh_moi/`:

| Tệp | Số dòng |
| --- | ---: |
| `01_invoices.csv` | 6 |
| `02_bank.csv` | 6 |
| `03_statements.csv` | 1 |
| `04_actions.csv` | 2 |

Lý do mẫu: `Bổ sung chứng từ phát sinh mới của Đại Phát ngày 18/11/2026.`

Kiểm tra tổng 12.786 hóa đơn, 17.648 dòng bank, 16.258 thanh toán, 143 kỳ sao kê và 5.003 nhật ký. Chứng từ mới chưa thêm phân bổ thanh toán. Các mã hóa đơn cũ và mới không trùng nhau.

## 3. T9 — đối soát

Vào Dòng tiền → Nạp dữ liệu → tải khoản chờ và tìm đề xuất đối soát. Dưới đây là bằng chứng quy ước của kịch bản mô phỏng, không phải chứng từ xác minh doanh nghiệp thật.

| Bank | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| `DP-B-DUNG` | Duyệt đề xuất 10 triệu vào `DP-HD-DUNG` | Hóa đơn hết nợ |
| `DP-B-GOP` | Duyệt 3 triệu vào `DP-HD-GOP1` và 7 triệu vào `DP-HD-GOP2` | Cả hai hết nợ |
| `DP-B-MOTPHAN` | Duyệt 8 triệu vào `DP-HD-MOTPHAN` | Hóa đơn còn 12 triệu |
| `DP-B-KIEMTRA` | Ghép thủ công 6 triệu vào `DP-HD-KIEMTRA2` | Không chọn `DP-HD-KIEMTRA1`; không duyệt cả hai |
| `DP-B-CHUARO` | Sửa dòng sao kê, đặt `cash_flow_class=other_external`, xem trước rồi xác nhận | 5 triệu được phân loại thu khác, rời hàng chờ công nợ |

Ghép thủ công KIEMTRA: mã thanh toán `DP-TT-KIEMTRA`; ghi chú `Bảng kê mô phỏng Đại Phát xác nhận thanh toán DP-HD-KIEMTRA2`.

Sửa CHUARO: lý do `Theo bảng kê xác minh mô phỏng Đại Phát, khoản thu 5.000.000 VND này là thu khác ngoài công nợ khách hàng.` Giữ nguyên ngày, tài khoản và số tiền. Xem trước phải hiện 0 phân bổ bị đảo.

Sau mỗi lần duyệt, kiểm tra chỉ bank vừa chọn được phân bổ; các bank còn lại vẫn cần xử lý riêng. Kết thúc: **16.263 phân bổ thanh toán, 0 khoản chờ, 0 đồng chưa phân bổ**. Ngoài công nợ không phải hàng chờ duyệt và không có nghĩa giao dịch bị xóa khỏi dòng tiền. Không suy ra ngoài công nợ chỉ vì thiếu thanh toán liên kết.

## 4. T5 — nạp lịch chi

Nạp theo thứ tự trong `03_lich_chi/`:

1. `01_outflows.csv`: 28 nghĩa vụ chi.
2. `02_expense_payments.csv`: 1 chứng từ đã trả 40 triệu tiền thuê, liên kết `DP-B-THUE` và nghĩa vụ `DP-THUE-DEMO`.

Lý do mẫu: `Bổ sung lịch chi và chứng từ đã thanh toán của Đại Phát.`

Kiểm tra tiền thuê tổng 100 triệu, đã chi 40 triệu, còn phải chi **60 triệu**; không ghi thêm lần nữa 40 triệu đã trả vào chi tương lai.

## 5. T1 → T6 → T10

Vào Dự báo, dùng:

- Ngày dự báo: `18-11-26`.
- Số dư đầu kỳ: `424000000` VND; ngưỡng cảnh báo: `200000000` VND.
- Số tuần: `13`; kịch bản: Kế hoạch gốc.
- Các tuần đã rà soát đủ lịch chi: `1,2,3,4,5,6,7,8,9,10,11,12,13` sau khi kiểm tra bộ lịch chi mô phỏng.
- Tắt ước lượng dòng tiền hoạt động cho lượt demo này.
- Chỉ xác nhận đã nạp đủ thanh toán sau khi kiểm tra đối soát hoàn tất.

Lập dự báo, trình bày T1 (thu dự kiến), rồi T6 (số dư và các tuần có nguy cơ thiếu tiền). Tiếp theo T10: thử khách hàng thu chậm hoặc dời lịch chi, so sánh với kế hoạch gốc, lưu và mở lại phương án, xuất Excel. Kiểm tra thao tác thử phương án không sửa dữ liệu nguồn hoặc các kế hoạch đã lưu trước đó.

## Tệp phụ

- `00_nap_thu_khong_trung.csv`: một hóa đơn đã có; chỉ dùng để kiểm tra nạp lại cùng mã, theo dõi số lượng không tăng thành hóa đơn trùng.
- `99_chi_xem_truoc_loi.csv`: hóa đơn có số tiền âm; chỉ xem trước để kiểm tra báo lỗi và chặn ghi.
- Các CSV ở gốc là **bản gộp dự phòng**. Không nạp chúng cùng bộ theo giai đoạn trong một lượt test.
- `verification.json` là kết quả diễn tập API trước đây, không thay thế kết quả test tay UI trên code vừa merge.
