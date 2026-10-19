# T1 — Dữ liệu nghiên cứu thời điểm thanh toán hóa đơn

T1 trả lời: **một hóa đơn sẽ được trả vào lúc nào, và trễ hạn bao nhiêu ngày?** Dữ liệu ở đây phục vụ kiểm tra nguồn và chuẩn bị benchmark; chưa được dùng để train lại notebook.

## 1. Cấu trúc hiện có

```text
T1/
  raw/
    czech/2026-10-18/
      finance/faktury.csv            # Toàn bộ CSV Bộ Tài chính Séc
      finance/usage_metadata.html    # Thông tin điều kiện sử dụng từ nguồn
      health/pages/page_0001.json …  # 290 trang hóa đơn ngành y tế
      health/imports_before.json     # Các đợt nhập và ngày công bố
      health/organizations_before.json
      download_manifest.json        # URL, thời điểm tải, headers, SHA256, kiểm tra tải
    source_samples/
      bpi_prefix.xml.part            # Mẫu log quy trình, không phải file tải lỗi
      dc_sample_2020.json            # 1.000 dòng năm tài khóa 2020
      dc_sample_2024.json            # 1.000 dòng năm tài khóa 2024
      dc_sample_2026.json            # 1.000 dòng năm tài khóa 2026
  interim/czech/2026-10-18/
    finance_invoice_audit.csv
    health_invoice_audit.csv
    finance_monthly_coverage.csv
    health_monthly_coverage.csv
    health_by_organization.csv
```

`2026-10-18` là ngày tải, không phải kỳ phát sinh của toàn bộ hóa đơn. `raw` giữ nguồn để đối chiếu; `interim` đã chọn cột và làm phẳng dữ liệu, kèm cờ thiếu ngày, sai thứ tự, trùng và mâu thuẫn. Các cờ `gate_*` chỉ biểu thị điều kiện kiểm tra cụ thể, không chứng nhận một record đã sẵn sàng train.

## 2. Hai bộ Séc là dữ liệu gì?

Đây là **dữ liệu hóa đơn nhà cung cấp gửi cho các cơ quan công tại Cộng hòa Séc**. Đơn vị công là bên mua/trả tiền; nhà cung cấp là bên bán/nhận tiền. Nguồn nhìn từ phía khoản phải trả của cơ quan công; nếu nghiên cứu góc nhìn phải thu của nhà cung cấp, phải giữ đúng vai trò này.

| Nguồn | Nội dung | Mục đích với T1 |
|---|---|---|
| Bộ Tài chính Séc | Hóa đơn mua hàng/dịch vụ của bộ: định danh, nhà cung cấp, ngày phát hành/nhận/hạn trả/ngày trả, số tiền và tiền tệ | Benchmark thời gian từ phát hành đến ngày trả được ghi nhận, và số ngày sớm/trễ so với hạn |
| Ngành y tế Séc | Hóa đơn của 27 đơn vị công bố trong ngành y tế với nhà cung cấp; có thêm thông tin paid amount ở một phần dữ liệu | Benchmark cùng mục tiêu trên nhiều bên mua; so sánh hành vi giữa các đơn vị và kiểm tra độ bền khi đổi nhóm |

**Bộ tài chính không phải báo cáo chứng khoán hay dữ liệu SEC Mỹ. Bộ y tế không phải hồ sơ bệnh nhân:** đối tượng dự báo vẫn là hóa đơn và thanh toán.

Bộ tài chính gồm dòng tổng và dòng ngân sách, không thể coi mọi dòng là một hóa đơn. Bộ y tế có độ đầy đủ field khác nhau giữa các đơn vị. Quy mô, số dòng qua từng gate và vấn đề trùng được duy trì trong [báo cáo audit đầy đủ](../../research/notes/t1_czech_full_dataset_audit.md).

## 3. Vì sao phù hợp T1?

- **Đúng đơn vị nghiệp vụ:** có hóa đơn, bên mua/bán, số tiền và các mốc thanh toán để nghiên cứu, thay vì suy thời gian trả từ dữ liệu doanh số hoặc khoản vay.
- **Có thể tạo nhãn thời gian:** từ phát hành đến trả, hoặc sớm/trễ so với hạn. Định nghĩa nhãn và benchmark riêng từ ngày tiếp nhận nằm tại [hợp đồng dữ liệu T1](../../docs/reference/t1-data-contracts.md).
- **Có lịch sử theo thời gian và các quan hệ mua/bán lặp lại:** có thể tạo đặc trưng hành vi từ quá khứ và đánh giá bằng cách train giai đoạn trước, test giai đoạn sau. Chỉ dùng thông tin đã biết tại thời điểm dự báo; ngày trả và paid amount tương lai dùng cho nhãn/kiểm tra, không đưa vào feature của invoice đang dự báo.
- **Quy mô đủ để bắt đầu so sánh phương pháp:** có thể thử baseline lịch sử/điều khoản và mô hình dự báo thời gian; số dòng qua gate không phải bảo đảm chất lượng mô hình.

Mức phù hợp hiện tại là **benchmark thời gian trả trên cohort có nhãn hợp lệ**, chưa phải bằng chứng dự báo đầy đủ danh mục phải thu của SME Việt Nam. Nguồn B2G Séc khác khách hàng B2B Việt Nam; ngày trả được công bố chưa xác nhận ngày tiền khả dụng trong ngân hàng bên bán. Thiếu ngày trả không tự động có nghĩa chưa trả/vỡ nợ. Chưa chứng minh nguồn chứa toàn bộ hóa đơn đang mở để dựng risk set survival đại diện; kiểm duyệt nhân tạo trên cohort đã chọn không bổ sung được các hóa đơn bị thiếu.

API công khai thường có thông tin sau khi thanh toán. Backtest từ ngày phát hành chỉ hợp lý dưới giả định hệ thống ERP nội bộ đã biết các feature đầu vào ở thời điểm đó; không dùng ngày công bố muộn để giả vờ dự báo trước thanh toán.
