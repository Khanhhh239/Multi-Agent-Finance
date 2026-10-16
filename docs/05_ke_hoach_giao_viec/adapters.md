# Bộ nhận dữ liệu: phạm vi đã kiểm chứng

Ngày 2026-10-16, chủ dự án xác nhận **chưa có tệp mẫu thật**. Chưa xây hoặc xác nhận bộ nhận riêng cho MISA hay bất kỳ hãng kế toán nào.

## CSV chung

`agent2.adapters.csv_generic.CSVAdapter` nhận tệp YAML với ánh xạ **cột nguồn sang cột chuẩn**, kiểu cần đổi và múi giờ nguồn. Mã được đọc dưới dạng chuỗi để giữ số 0 ở đầu. Các kiểu hỗ trợ: `string`, `integer`, `number`, `datetime`.

```yaml
timezone: Asia/Ho_Chi_Minh
tables:
  transactions:
    file: so_chi_tiet.csv
    columns:
      CongTy: company_id
      MaGiaoDich: transaction_id
      NgayTao: created_at
      NgayDuyet: approved_at
      NgayDang: posted_at
      Loai: txn_type
      SoTien: amount_vnd
    types:
      created_at: datetime
      approved_at: datetime
      posted_at: datetime
      amount_vnd: integer
```

Có thể khai báo `encoding`, `separator`, `thousands_separator`, `decimal_separator` cho từng bảng. Không tự đoán dấu phân cách số hoặc múi giờ. Ngày giờ chưa có múi giờ được hiểu theo `timezone`; thời gian đã có múi giờ được chuyển sang giờ Việt Nam.

```powershell
.venv\Scripts\python.exe -m agent2.adapters.csv_generic --input DUONG_DAN_THU_MUC --mapping mapping.yaml --out work/normalized
.venv\Scripts\python.exe scripts/adapter_smoke.py
```

CLI xuất CSV chuẩn và `input_report.json`. Nếu có lỗi bắt buộc, dừng trước khi xuất. Nếu báo `reduced`, pipeline v4 chỉ chạy tập con C2/C3 có đủ bằng chứng, ghi rõ các luật và mô hình bị tắt; pipeline tổng hợp v3 cũ chưa hỗ trợ việc này. YAML được đọc bằng `safe_load` theo [tài liệu PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation).

## XML hóa đơn điện tử

`EInvoiceXMLAdapter(company_id).load(path)` trả bảng `invoices` và `invoice_lines`. Trích thông tin hóa đơn và dòng hàng, giữ số thập phân chính xác. Công ty do người vận hành khai báo; khóa hóa đơn gồm mã số thuế bên bán, ký hiệu, số và ngày. Chỉ hỗ trợ tiền tệ ghi rõ VND.

Đối chiếu tên thẻ với tài liệu kỹ thuật gốc kèm Quyết định 1271/QĐ-CT ngày 30-05-2025, phần II, mục II, các trang về định dạng hóa đơn, dòng hàng và thanh toán: [bản PDF của cơ quan thuế được lưu tại Thư Viện Pháp Luật](https://cdn.thuvienphapluat.vn/phap-luat/2022-2/NTMH/30052025/Quyet%20%C4%91inh-1271.pdf). [Trang công bố của Cục Thuế](https://gdt.gov.vn/wps/portal/home/documents) cần đối chiếu thêm trước khi vận hành.

**Chưa kiểm chứng với tệp xuất thật.** Không xác minh chữ ký, tính hợp lệ về thuế, nghiệp vụ điều chỉnh hoặc thay thế. Không suy diễn người lập, người duyệt hay thời điểm đăng sổ từ ngày hóa đơn. Đầu ra XML chưa đủ để chạy pipeline sổ kế toán; báo cáo luôn ghi `unverified` và `missing_ledger=true`.

## Đầu vào cần bổ sung

Nhận tại chỗ tệp CSV hoặc XML đã ẩn danh từ hai đến ba doanh nghiệp, kèm tên và phiên bản phần mềm, mô tả từng cột, múi giờ, cách biểu diễn số, hóa đơn điều chỉnh và chứng từ hủy. Chỉ nhận sau quy trình pháp lý và thỏa thuận dữ liệu của pha E. Không đưa dữ liệu thật lên Git. Kiểm thử hiện tại chỉ dùng mẫu tổng hợp.
