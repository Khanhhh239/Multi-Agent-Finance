# PLAN_04 — Baseline extraction tổng hợp

Ngày chạy: 12/10/2026. Phạm vi đã được chọn ở PLAN_00: technical/functional bằng fixture project. Đây là development evaluation với nhãn do generator tạo, **không phải frozen holdout hay nhãn được chuyên gia kiểm chứng**. Parser được sửa trên các trường hợp development này; không suy ra accuracy hóa đơn thực tế.

| Nhóm | Tài liệu / trang | Field có nhãn khớp | PRESENT sai | Row recall theo description + net |
|---|---:|---:|---:|---:|
| PDF native text | 10 / 11 | 162/162 | 0 | 16/16 |
| Artifact hybrid hiện hành, gồm native + OCR | 5 / 6; 3 tài liệu có nhãn | 37/49 | 6 | 1/5 |
| Riêng tài liệu có OCR và nhãn trong nhóm trên | 2 / 3 | 23/35 | 6 | 0/4 |

Hàng cuối là **subset**, không cộng thêm vào tổng 15 tài liệu/17 trang. Các nhóm còn trùng logical document (syn-00/syn-08); không pool thành bộ accuracy độc lập. Hai tài liệu extra hybrid/rotation chỉ kiểm tra contract/integration, không có nhãn field để đo accuracy. Phần native dùng normalized artifacts lịch sử có model ID Tesseract nhưng toàn bộ route là NATIVE_TEXT, không dùng inference Tesseract. Phần hybrid dùng artifacts đã chạy PP-OCRv6 + VietOCR ở PLAN_03. Không chạy lại model trong PLAN_04.

Metric field chỉ chấm annotation `OBSERVED`. `NOT_ANNOTATED`, `UNREADABLE`, `ABSENT_CONFIRMED` được thống kê riêng, không tính thành correct hoặc sai. Nhiều nhãn KCT/KKKNT có vat_rate không áp dụng; không tăng denominator bằng giá trị không có nhãn. Per-field diagnostics căn theo thứ tự dòng generator; row recall dùng multiset description + net chính xác, không dùng item ID của nhãn làm ID project.

## Kết quả và lỗi còn lại

Có **12 field không khớp**, gồm 6 sai giá trị PRESENT và 6 thiếu giá trị. Chi tiết từng field nằm ở [field_failures.json](field_failures.json); counts từng field/cohort, raw-region diagnostics và hashes nằm ở [baseline_summary.json](baseline_summary.json).

Các lỗi PRESENT cụ thể: tên người mua bị đọc `GIÁ` thay `GIẢ`, tên người bán bị OCR sai ký tự/suffix, số hóa đơn bị đọc `DEMOVOOB` thay `DEMO/008`; hai ô tiền `100000` bị OCR thành `1000000`. Parser giữ các số đã đọc, không tự sửa dựa trên tổng. Đây là các **wrong extraction candidates**, chưa phải kết quả được chấp nhận: cả 15 artifact bắt buộc review.

Nhãn VAT được phục hồi thêm 6 field sau khi parser hỗ trợ merged label/value và khoảng trắng quanh `/`. Description dòng nhiều trang còn thiếu do layout/text; một nhãn KKKNT vẫn thiếu. Cột diagnostic `PARSER` nghĩa là raw value có trong vùng GT hoặc đầu vào native, nhưng chưa đủ để tự khẳng định toàn bộ label/role/context đọc đúng. `OCR_TEXT_OR_LAYOUT_REQUIRES_INSPECTION` cần kiểm tra vùng gốc. Không gán mọi lỗi extraction cho model OCR.

Toàn bộ original fixtures chưa có row-count evidence, vì vậy discovery vẫn **UNKNOWN**, kể cả 16 dòng native khớp nhãn. Derived totals không tự cộng tập items chưa chứng minh đầy đủ. Các fixture chức năng riêng có explicit row count để kiểm chứng nhánh COMPLETE, total mismatch và derivation; không trộn chúng vào accuracy denominator.

## Giới hạn hỗ trợ và bàn giao

| Hạng mục | Hỗ trợ trong PLAN_04 | Phần cần làm tiếp |
|---|---|---|
| Header/parties | Nhãn Việt/Anh rõ ràng, cùng block hoặc block bên phải cùng dòng; generic MST cần section context | Layout mới/mất nhãn/party role không rõ → review, bổ sung fixture |
| Bảng | Item sections có nhãn; column header rõ, spatial rows, repeated headers mỗi trang, continuation cùng trang | Bảng gộp ô, nested headers, dòng bắt đầu tiếp ở trang mới thiếu header → chưa chứng minh, giữ UNKNOWN/review |
| Completeness | COMPLETE chỉ với số dòng khai báo, rows khớp và mọi trang đọc được | PDF nguồn bị thiếu trang nhưng không có chỉ báo chưa phát hiện được; không claim completeness |
| VAT | KCT/KKKNT/0%, Decimal, groups partition item IDs | Legal category MISSING; cần taxonomy evidence ở chặng pháp lý |
| Identity | UUID cấp một lần; replay/correction/reorder giữ ID; explicit re-extraction mapping và lineage | Review UI và lưu revision split/merge ở PLAN_06 |
| Quality | Raw score giữ semantics detector; không field confidence giả; mọi artifact review | PLAN_05 đánh giá validity, cross-field mismatch, calibration và risk policy |
| Dataset | Fixture tổng hợp; chỉ development evaluation | DQ-01–05: nguồn hợp lệ, hóa đơn thuế Việt Nam, người review độc lập, freeze splits trước nghiệm thu thực tế |

PLAN_05 nhận CFR/candidates, bảng lỗi và observed/derived totals. Ưu tiên bắt sai số tiền/OCR, mô tả dòng thiếu, phạm vi review và giữ UNAVAILABLE khi chưa đủ calibration. PLAN_06 nhận evidence resolver, dependency DAG, pure rederive và identity mapping. Chưa bật auto acceptance hoặc compliance verdict.
