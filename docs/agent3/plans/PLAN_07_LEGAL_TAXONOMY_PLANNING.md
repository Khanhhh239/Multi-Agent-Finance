# PLAN_07 — Legal Registry, VAT taxonomy và Rule Planning

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_06](PLAN_06_REVIEW_CAPTURE_MVP.md) · Sau: [PLAN_08](PLAN_08_ZEN_RULES_AGGREGATION.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Chọn đúng rule version và evaluation units; tách applicability, capability và eligibility; có legal/taxonomy evidence trước khi chạy engine.

- Phụ thuộc bắt buộc: PLAN_01, PLAN_05–06 đạt gate.
- Ước lượng: **6–9 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 1.7, 7, 9.3–9.5, 11.
- Đầu vào: Legal PDFs/source map, CFR contracts, quality signals, capability profiles và danh mục luật MVP.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

PDF và source links tại docs/references/legal; NEW_PLAN chỉ là thiết kế có ví dụ lịch sử, không là gói rule đã duyệt. Scope nguồn và điều kiện non-cash phải bám đúng dữ liệu có, không thêm bank evidence vào OCR/XML bằng suy đoán.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/legal_registry/; src/taxonomy/; src/planning/{selector,applicability,capability,eligibility,units}.py; rules/registry/; tests/planning/`

RulePlanEntry key=(evaluation_id, rule_id, rule_version, unit_type, unit_id); pin CFR revision + profile/ruleset/legal/taxonomy/master versions. Applicability MATCH/NO_MATCH/UNKNOWN, capability SUPPORTED/UNSUPPORTED/UNKNOWN; required_fields khác required_observations. Missing/ambiguous date giữ selection.rule_version=null.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P07-T01 — Tạo Legal Registry có lịch sử

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Nhập document ID, official URL, hash, effective interval, article/appendix, supersedes có scope, transitional policy. Rà PDF Điều 10 NĐ254 và Điều26 NĐ181; TT91 replacement clause cần kiểm bản gốc trước publish.
- Đầu ra: legal_registry_v1 + evidence map.
- Kiểm chứng: Mọi rule trỏ legal basis được đối chiếu, không dựa citation rác hay nguồn thứ cấp.

### P07-T02 — Đóng rule-version timelines

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tách invoice rules 2022-07-01→2025-05-31, 2025-06-01→2026-06-30 và từ 2026-07-01 theo registry. Không dùng ngày invoice cho mọi loại nghĩa vụ; ghi date policy mỗi rule.
- Đầu ra: version timeline fixtures.
- Kiểm chứng: Test trước/đúng/sau boundary; gap/overlap trong vùng hỗ trợ là planning error; ngoài historical support có lý do rõ.

### P07-T03 — Capability profiles immutable

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Khai field/evidence capability theo adapter/profile version. Tách source không thể cung cấp payment evidence khỏi record đơn lẻ đang thiếu field.
- Đầu ra: capability_profiles/*.yaml.
- Kiểm chứng: Record missing không thành OUT_OF_SCOPE; OCR không được quảng bá chứng minh thanh toán.

### P07-T04 — VAT taxonomy deliverable

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tạo taxonomy version, legal category definitions, effective intervals, mapping hàng hóa/dịch vụ và evidence độc lập observed rate. Cho human confirmation và UNKNOWN khi chưa phân loại.
- Đầu ra: taxonomy_v1 + mapping provenance.
- Kiểm chứng: Không map category từ rate 8%; KCT/KKKNT/0% giữ semantics; thiếu taxonomy evidence phải review, không đoán.

### P07-T05 — Applicability tri-state

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Cài predicates kiểm status trước value; direction unknown/null trả UNKNOWN. Đưa ngưỡng 5 triệu vào planning duy nhất, tính cả daily same-supplier aggregate khi đủ chứng từ/kỳ dữ liệu.
- Đầu ra: applicability evaluator + traces.
- Kiểm chứng: <5 triệu một invoice không tự NO_MATCH nếu chưa biết tổng cùng ngày; thiếu ledger/evidence để UNKNOWN.

### P07-T06 — Date selector có early return

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Missing/ambiguous date không truy cập rule_version null; known date gap/overlap trả NOT_EVALUATED_PLANNING_ERROR. Không gọi engine khi selection bất định.
- Đầu ra: selector.py.
- Kiểm chứng: Null date chạy branch riêng; log selection rationale/effective interval; không silently dùng latest.

### P07-T07 — Tạo evaluation units

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn RECORD/ITEM/VAT_GROUP mỗi rule; immutable item refs, strategy chống double count, discovery blockers khi thiếu hàng.
- Đầu ra: units.py + unit manifests.
- Kiểm chứng: items=[] với discovery UNKNOWN không dẫn vacuous PASS; reorder không đổi evaluation unit identity.

### P07-T08 — Eligibility và observations

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Phân required usable values với CONFIRMED_ABSENT/PRESENT_VALUE. OCR không thấy field chỉ UNKNOWN; source/profile hoàn chỉnh mới cho chứng minh vắng. Map thiếu/low-confidence/invalid/planning lỗi sang status/next_action.
- Đầu ra: eligibility.py + decision table.
- Kiểm chứng: Unknown applicability trên unsupported source vẫn unresolved; không lẫn REVIEW_REQUIRED và tax REVIEW.

### P07-T09 — Nghiệm thu planning matrix

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy tổ hợp date/capability/status/observation/unit discovery; ghi scope exclusions và blockers cùng version. Đối chiếu từng rule MVP với owner nghiệp vụ được chỉ định.
- Đầu ra: planning_matrix_report + gate_07.md.
- Kiểm chứng: Không có engine call cho non-eligible; mọi exclusion có lý do và evidence/version; rule pháp lý chưa xác minh không publish.

## 5. Tiến độ bên trong chặng

- Ngày 1–2: legal registry/version/date policies.
- Ngày 3: capability profiles và unit strategies.
- Ngày 4–5: taxonomy/mapping và unknown pathways.
- Ngày 6–7: selector/applicability/eligibility.
- Ngày 8–9: boundary matrix, legal evidence review và gate.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Invoice date missing → rule_version null, no dereference.
- [ ] Direction UNKNOWN legacy được migrate trước predicate.
- [ ] Một invoice 4 triệu, cùng supplier/ngày chưa đủ ledger.
- [ ] XML thiếu bank evidence: scope exclusion hoặc unresolved đúng policy, không FAIL.
- [ ] Quan sát thiếu nội dung đáng tin mới cho rule xác định vi phạm.
- [ ] Rule interval overlap/gap; taxonomy version hết hiệu lực.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Rule metadata có căn cứ kiểm chứng và date policy; tri-state/units/eligibility matrix qua. Chưa có taxonomy/ledger thì bảo toàn UNKNOWN và hướng dẫn bổ sung, không chặn toàn bộ các rule độc lập đủ dữ liệu.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_07.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_08 nhận immutable RulePlan, selected legal basis và eligible units; PLAN_09 nhận blockers/scope explanations.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
