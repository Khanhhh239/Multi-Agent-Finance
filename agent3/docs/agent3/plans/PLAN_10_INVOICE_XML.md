# PLAN_10 — Bổ sung Invoice XML trên cùng pipeline

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_09](PLAN_09_COMPLIANCE_MVP.md) · Sau: [PLAN_11](PLAN_11_EXCEL_BANK.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Thêm đường ingest deterministic cho XML mà không rẽ thành hệ luật riêng hoặc giả định có payment evidence.

- Phụ thuộc bắt buộc: PLAN_09 đạt gate; có XML fixtures có quyền sử dụng.
- Ước lượng: **3–5 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 3, 4.2, 5, 7, 9.
- Đầu vào: CFR contracts, parser profiles, XML schema families, legal history fixtures.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

NEW_PLAN có ví dụ XML confidence 1.0 mang tính minh họa; implementation dùng DETERMINISTIC + fidelity policy nếu đáp ứng điều kiện. Prototype/XML files phải kiểm kê profile thực tế trước khi tuyên bố hỗ trợ.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/adapters/invoice_xml/; configs/capabilities/xml/; tests/adapters/xml/`

XML parse evidence gồm source hash, namespace/schema/profile version, XPath và raw lexical value. Required observation CONFIRMED_ABSENT chỉ có khi parser/profile kiểm đầy đủ vùng/schema tương ứng. Invoice XML không cấp bank payment chứng minh giao dịch.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P10-T01 — Inventory XML families

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Ghi namespace, vendor version, signed/unsigned, missing/extra nodes, line-item representation. Xác định profile hỗ trợ và UNKNOWN_XML fallback.
- Đầu ra: xml_profile_matrix.
- Kiểm chứng: Không gán mọi XML thành invoice chỉ vì extension .xml.

### P10-T02 — Parser an toàn

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Disable DTD/external entities/network fetch, limit size/depth/node count. Lưu raw XML/hash, không thực thi signature verification giả.
- Đầu ra: parser.py + security fixtures.
- Kiểm chứng: XXE/billion-laughs bị chặn; signature status UNKNOWN nếu chưa có verifier thật.

### P10-T03 — Mapping canonical fields

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Map XPath→seller/buyer/date/amount/items/treatment; giữ lexical evidence và Decimal. Derive bằng module chung Layer 5.
- Đầu ra: mapper.py + XPath evidence.
- Kiểm chứng: KCT/KKKNT/null/rate0 đúng semantics; item IDs immutable, không index-dependent.

### P10-T04 — Deterministic fidelity policy

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tách đọc đúng XML khỏi tính đúng pháp lý/nội dung; unknown schema/profile không tự tin 1.0. Absence observation chỉ khi vùng được parse đầy đủ.
- Đầu ra: fidelity_policy_v1.
- Kiểm chứng: Source ghi sai MST vẫn có extraction fidelity nhưng validation issue riêng.

### P10-T05 — Capability và planner integration

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Publish profile version cùng schema families; non-cash ngoài capability nếu không có evidence phù hợp. Kiểm historical invoice boundaries.
- Đầu ra: capability profile + integration tests.
- Kiểm chứng: XML đủ header có thể chạy content rule; không blanket review chỉ do không có probabilistic score.

### P10-T06 — Parity với OCR đã review

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tạo cặp XML/PDF cùng hóa đơn có quyền dùng, so canonical semantics, không tự merge evidence giữa records.
- Đầu ra: parity_report.md.
- Kiểm chứng: Sai khác source giữ issue, không ép sửa PDF cho khớp XML.

### P10-T07 — Nghiệm thu XML adapter

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy valid/invalid/unknown namespaces, version/date/tax treatment và incomplete table. Lưu profile support matrix.
- Đầu ra: gate_10.md + adapter card.
- Kiểm chứng: Hỗ trợ chỉ các profile đã thử; errors giữ typed contracts, không ảnh hưởng OCR pipeline.

## 5. Tiến độ bên trong chặng

- Ngày 1: profiles + parser security.
- Ngày 2–3: mapping, fidelity và capability.
- Ngày 4–5: parity/integration/history boundaries và gate.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Unknown namespace không bị parse theo profile gần giống.
- [ ] XML xác nhận thiếu required node khác OCR không thấy.
- [ ] Signature có node nhưng chưa verify phải UNKNOWN.
- [ ] Invoice trước 01/07/2026 chọn đúng rule lịch sử.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** XML pass cùng CFR/planning/outcome contracts; parser security và deterministic fidelity được kiểm; không vượt capability payment.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_10.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: M3 bắt đầu đa nguồn; PLAN_11 thêm tabular/bank mà không thay đổi semantics XML/OCR.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
