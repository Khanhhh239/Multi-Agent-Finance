# Sửa trường thiếu — vòng 2, PLAN_06

Ngày: 14/10/2026. Trạng thái: TECHNICAL_SELF_CHECK; chưa chốt real-data/statistical gate. [Kết quả tổng hợp](missing_fields_round_02.json).

## Thay đổi đã đưa vào extractor

1. Nhận nhãn tiếng Anh bị OCR dính khoảng trắng, ví dụ `(VATamount)`. Chỉ bỏ phần dịch trong nhãn, không xóa phần trong ngoặc của giá trị doanh nghiệp. Sửa được trường tổng thuế VNPT vốn đã đọc đúng số.
2. Tách điều kiện xác định vùng tên bên bán khỏi việc MST đã parse thành công hay chưa. Cần tiêu đề hóa đơn, ranh giới bên mua, đúng một tax anchor có hình dạng số và tên tổ chức ở gần; nhiều tax anchor thì không chọn. MST có dấu chấm hoặc chữ thừa vẫn bị parser từ chối, không tự sửa thành số đoán. Sửa được tên bên bán Haravan đang có text đúng nhưng chưa bind.
3. Cho phép đúng một dấu `)` sau ngày có đủ nhãn ngày/tháng/năm. Vẫn kiểm lịch; không chấp nhận chữ thừa hoặc số thừa. Sửa được ngày lập Haravan ở output OCR split; output OCR default có lỗi chữ khác nên vẫn thiếu ngày.

## Replay cùng input, cùng nhãn

Không chạy lại OCR để chấm tác động của thay đổi extraction. Mỗi nhánh replay chính normalized input đã đóng băng của nhánh đó; không trộn cache default với split.

| Nhánh trên 3 trang raster / 31 field được chấm | Trước sửa extraction vòng 2 | Sau |
|---|---|---|
| OCR default | 21 đúng / 6 thiếu / 4 điền sai | **23 đúng / 4 thiếu / 4 điền sai** |
| OCR split thử nghiệm | 23 đúng / 6 thiếu / 2 điền sai | **26 đúng / 3 thiếu / 2 điền sai** |

Native public vẫn **80/80 field chọn lọc đúng** nhờ sửa tổng tiền ở vòng trước; nguồn đào tạo báo riêng 10/10. Hybrid giữ 27 đúng/4 ambiguous ở default và 29 đúng/2 ambiguous ở split. Chưa chấm đầy đủ địa chỉ/ô bảng; các mode là cùng chứng từ, không phải mẫu độc lập. Không bật split mặc định hoặc auto-accept.

## Thí nghiệm recovery theo vùng

Chọn 4 vùng lỗi từ evidence box, render trực tiếp vùng PDF tại 150/300/450 DPI, không render toàn trang ở DPI cao. Recognizer chỉ nhận ảnh crop; manifest/nhãn expected không đưa vào model. Xem crop bằng mắt để xác nhận dấu và số được in. So sánh greedy ở cả 3 DPI, rồi beam trên cùng crop 300 DPI.

- 300 DPI đọc đúng ký hiệu VNPT và MST chi nhánh Haravan; 450 DPI không có lợi thêm trên hai vùng này.
- MST người mua VNPT vẫn có dấu `)` dư trong output; parser giữ MISSING.
- Ngày Haravan khi render lại vùng có token nhãn `vear` và/hoặc chữ thừa. Beam bỏ được phần đuôi nhưng strict parser vẫn không nhận `vear`; không thêm alias này chỉ để làm đẹp benchmark.
- Đây là chứng cứ để chọn hướng recovery, **chưa tích hợp tự động recovery vào worker/UI**. Không lấy các kết quả đọc đúng của thí nghiệm cộng vào accuracy CFR hiện hành.

## Kiểm chứng và tái hiện

**116 test PASS trong đợt này:** extraction 50, quality 34, review 32. Các test mới gồm nhãn dịch dính chữ, giữ nguyên giá trị trong ngoặc, tên issuer khi MST đọc lỗi, nhiều tax anchor, ngày có dấu đóng ngoặc, ngày/số/chữ dư và việc không cắt chữ thừa khỏi MST/ký hiệu. Kiểm tra compile và Git diff không lỗi.

```powershell
# Cwd D:\financial; dùng run-id mới để giữ nguyên evidence cũ
agent3_tax_compliance/.venv/Scripts/python.exe scripts/replay_ocr_v2.py --input-run plan06_v20_frozen_01 --run-id my_default_replay
agent3_tax_compliance/.venv/Scripts/python.exe scripts/replay_ocr_v2.py --input-run plan06_v21_split_full_01 --run-id my_split_replay
agent3_tax_compliance/.venv/Scripts/python.exe scripts/benchmark_region_reads_v2.py --run-id my_regions --mode prepare
& 'data invoice/ocr_e2e_workflow/envs/ppocrv6_vietocr/Scripts/python.exe' scripts/benchmark_region_reads_v2.py --run-id my_regions --mode recognize
& 'data invoice/ocr_e2e_workflow/envs/ppocrv6_vietocr/Scripts/python.exe' scripts/benchmark_region_reads_v2.py --run-id my_regions --mode recognize --decode beam --dpi 300
```

Các thay đổi extraction dùng cho capture mới. Job đã hoàn thành không bị sửa ngầm; upload trùng có thể trả job cũ. Cách chạy UI với DB riêng để tự đối chiếu lại cùng PDF có ở [runbook](runbook.md).

Tiếp theo trong PLAN_06: recovery có giới hạn cho MST/ký hiệu, có provenance mới và không tự ghi đè reviewer correction; kiểm tra thêm hóa đơn/bố cục khác trước khi bật mặc định cấu hình OCR thử nghiệm.
