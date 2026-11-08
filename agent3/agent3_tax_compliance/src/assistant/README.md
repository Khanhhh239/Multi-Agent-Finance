# Agent 3: trợ lý rủi ro thuế (bản chạy được)

Cài đặt theo pipeline ở `DIGITAL_ACCOUNTING_PART11_AGENT3_PIPELINE.md`: một khung cố định chạy trên gói thích ứng của từng doanh nghiệp. Mọi bước là tất định; gói này không gọi mô hình ngôn ngữ.

## Chạy thử với doanh nghiệp mô phỏng

```
python -m src.assistant.cli synth    --out ../demo_ws          # sinh doanh nghiệp mô phỏng và nhãn đáp án
python -m src.assistant.cli run      --workspace ../demo_ws    # báo cáo ở demo_ws/out/report.html
python -m src.assistant.cli evaluate --workspace ../demo_ws    # chấm theo nhãn
python -m src.assistant.cli ask      --workspace ../demo_ws "Tháng 8 có bao nhiêu thuế có nguy cơ bị loại?"
python -m src.assistant.cli impact   --workspace ../demo_ws --ruleset-after configs/assistant/examples/ruleset_hypothetical_10m.json
```

## Thư mục làm việc của một doanh nghiệp

| Đường dẫn | Nội dung | Bắt buộc |
|---|---|---|
| `pack.json` | Gói thích ứng: hồ sơ, định dạng sao kê từng ngân hàng, ngưỡng (chỉ được chặt hơn), chính sách nội bộ (chỉ thêm cờ), danh sách tham chiếu (phải có ngày) | Có |
| `invoices/purchase/*.xml` | Hóa đơn mua vào | Có |
| `bank/*.csv`, `bank/*.xlsx` | Sao kê tự xuất từ internet banking | Nên có |
| `portal/purchase_list.csv` | Bảng kê hóa đơn mua vào tải từ cổng hóa đơn điện tử (tên cột khai trong `portal_columns`) | Không |
| `decisions.json` | Quyết định của người duyệt (đã đính kèm chứng từ, không kê khai) | Không |

## Các bước và luật đang có

| Bước | Tệp | Nội dung |
|---|---|---|
| Tiếp nhận, chuẩn hóa | `sources.py` | Đọc XML bằng bộ đọc của khung cố định (kèm lá chắn), sao kê CSV và XLSX theo ánh xạ cột, bảng kê cổng |
| Ghép | `matching.py` | Đúng số tiền và có tín hiệu người bán (tài khoản, tên hoặc mã số thuế, số hóa đơn); trả nhiều lần; một lần cho nhiều hóa đơn; chỉ trùng số tiền thì chuyển người |
| Luật theo ngày | `rules.py`, `configs/assistant/ruleset_2026_11_draft.json` | R01 chứng từ thanh toán; R02 cộng dồn trong ngày; R03 ghép mơ hồ; R04 toàn vẹn tệp; R05 trùng; R06 hóa đơn thay thế, điều chỉnh; R07 người mua; R08 danh sách rủi ro; R09 đối chiếu bảng kê; R11 lệch thông lệ |
| Tiền và lịch | `rules.totals`, `pipeline.filing_calendar` | Thuế có nguy cơ (mỗi hóa đơn tính một lần), ước tính phạt 20%, hạn tờ khai |
| Giao tiếp | `report.py`, `qa.py` | Báo cáo HTML, Markdown, JSON; hỏi đáp ba nhánh |
| Luật đổi | `impact.py` | Chạy lại với bộ luật khác và liệt kê thay đổi |
| Đánh giá | `evaluate.py`, `synth.py` | Chấm trên dữ liệu mô phỏng có nhãn |

## Giới hạn

- Bộ luật ở trạng thái nháp; căn cứ ghi kèm mức kiểm chứng; cần chuyên gia thuế duyệt.
- Chưa nối vào cơ sở dữ liệu và giao diện duyệt của khung caoban; quyết định của người duyệt đang ghi bằng tệp `decisions.json`.
- Chưa có: thời điểm lập hóa đơn bán ra, đối chiếu tờ khai, sổ chi tiết, tự chấm theo Thông tư 31/2021.
- Dữ liệu mô phỏng chỉ đo phần mềm với đáp án biết trước; mã số thuế sinh ra có thể trùng doanh nghiệp thật.
