# PLAN_11 — Excel và bank statement, không suy diễn đối soát

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_10](PLAN_10_INVOICE_XML.md) · Sau: [PLAN_12](PLAN_12_RAG_EXPLANATION.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Nhập dữ liệu bảng và giao dịch ngân hàng vào CFR theo đúng nguồn; chuẩn bị evidence cho đối soát nhưng chưa tự gắn payment vào invoice.

- Phụ thuộc bắt buộc: PLAN_09–10 đạt gate; có tabular/bank fixtures.
- Ước lượng: **5–8 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 3, 4.3, 4.5, 5.6, 7, 15.
- Đầu vào: Format registry, tenant/taxpayer authorization, CFR bank schema, mapping/version policy.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Detector phải nhận cả ZIP/XLSX và OLE2/XLS. Không dùng invoice parties schema để nhét account owner/counterparty ngân hàng. Không tự nhận counterparty bank là seller/buyer.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/adapters/{excel,bank}/; configs/mappings/; tests/adapters/tabular/`

Bank CFR: record_type BANK_TRANSACTION, bank_transaction.account_owner/counterparty/account/date/amount/currency/reference; parties={} hợp lệ theo schema bank. Excel mapping có template/profile version, sheet/cell coordinates, formula/raw/display value policy. Row identity khác số thứ tự hiển thị.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P11-T01 — Chọn template support matrix

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn ít nhất một Excel invoice template và một bank export có mẫu; generic Excel chỉ mapping/review, không auto nhận semantics.
- Đầu ra: tabular_support_matrix.
- Kiểm chứng: EXCEL_TABULAR/EXCEL_GENERIC detector labels map về enum/profile thống nhất.

### P11-T02 — Đọc XLSX/XLS có giới hạn

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chặn macros/external link execution, giới hạn sheets/rows/cells/zip expansion. Phân biệt cached formula, raw formula và displayed value; không giả Excel formula đã recalculated.
- Đầu ra: workbook_reader.py.
- Kiểm chứng: OLE2 .xls có route rõ; zip bomb/external link không được chạy.

### P11-T03 — Mapping bảng có version

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn sheet/header/columns/merged cells, normalize money/date và preserve coordinates. Preview mapping trước import với mẫu chưa biết.
- Đầu ra: template_mapper.py + mapping manifests.
- Kiểm chứng: Hai cột tiền/thuế không đảo; ambiguous date/currency ra candidates/review.

### P11-T04 — Bank parser chuyên biệt

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Parse owner/counterparty/debit/credit/reference, time zone/value date policy; amounts signed hoặc direction enum nhất quán.
- Đầu ra: bank_mapper.py.
- Kiểm chứng: Debit/credit không đảo; không dùng bank date làm invoice issue date.

### P11-T05 — Identity và dedupe

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Hash raw file và row source identity; duplicate imports không gộp các giao dịch thật trùng amount/date. Tách source row ID khỏi business transaction candidate matching.
- Đầu ra: row_identity.py.
- Kiểm chứng: Hai payment cùng tiền/ngày khác reference vẫn là hai records.

### P11-T06 — Capability và quality

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Bank profile cung cấp payment observations riêng, không invoice VAT; Excel tùy template, không tất cả source đều một profile.
- Đầu ra: capability/quality profiles.
- Kiểm chứng: Missing invoice MST trên bank không bị coi completeness failure của bank.

### P11-T07 — API batch và lỗi từng dòng

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Batch job trả success/error theo row record, stable cursor và retry chỉ dòng lỗi khi phù hợp. Không silently drop dòng khó parse.
- Đầu ra: batch result API.
- Kiểm chứng: Row lỗi không làm biến mất audit; tổng rows processed/skipped/error khớp input scope.

### P11-T08 — Nghiệm thu đa nguồn

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy fixtures sheet/row/format/locale/duplicate; giữ bank và invoice records độc lập. UI chỉ đưa candidate evidence chưa có match assertion.
- Đầu ra: tabular_bank_report + gate_11.md.
- Kiểm chứng: Không tuyên bố invoice đã thanh toán chỉ từ bank có amount giống; đối soát dành PLAN_15.

## 5. Tiến độ bên trong chặng

- Ngày 1–2: support matrix + readers/security.
- Ngày 3–4: mapping và bank semantics.
- Ngày 5–6: identity/batch/capability/quality.
- Ngày 7–8: edge cases, API pagination và gate.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] XLS OLE2 bị đặt extension .xlsx.
- [ ] Formula không có cached value; không tự tính bằng eval.
- [ ] Bank có credit/debit cùng template nhưng khác account currency.
- [ ] Hai rows cùng ngày/tiền không được dedupe bừa.
- [ ] Bank không có seller/buyer vẫn qua bank schema.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** M3: OCR/XML/Excel/bank đưa về cùng typed pipeline; source capability đúng, bank semantics không bị ép vào invoice; chưa có auto reconciliation.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_11.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_15 nhận bank/invoice records + evidence để thiết kế match; PLAN_14 nhận batch/resource constraints.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
