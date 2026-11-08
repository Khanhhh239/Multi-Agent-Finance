# PLAN_15 — Đối soát invoice–payment–ledger — sau MVP

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_14](PLAN_14_PRODUCTION_HARDENING.md) · Sau: Kết thúc backlog hiện tại

## 1. Kết quả cần đạt và điều kiện bắt đầu

Tạo evidence liên kết nhiều nguồn có thể kiểm chứng để mở rộng non-cash/daily aggregate; không gộp các record chỉ vì giống amount/date.

- Phụ thuộc bắt buộc: PLAN_11 và/hoặc PLAN_13 đạt gate; PLAN_14 baseline đủ cho phạm vi thử.
- Ước lượng: **8–15 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 1.4, 9.3, 15, 16.
- Đầu vào: Invoice/bank/ERP records, taxpayer/entity master, period completeness, labeled matches và owner nghiệp vụ.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Đây là phần mở rộng trong NEW_PLAN, không thuộc capture/compliance MVP. Ước lượng 8–15 ngày chỉ cho lát cắt được chọn, phải ước lượng lại sau inventory đặc thù payment/ledger.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/reconciliation/; src/evidence_graph/; tests/reconciliation/; configs/matching/`

MatchAssertion immutable có invoice/payment/ledger refs + revisions, match_type, amount_allocations Decimal, evidence, status CANDIDATE/CONFIRMED/REJECTED, actor/policy version. PeriodCompletenessAssertion có taxpayer/supplier/date range/source coverage/freshness; thiếu assertion không có bằng chứng full daily aggregate.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P15-T01 — Chọn bài toán đối soát nhỏ

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn one-to-one trước hoặc dạng nghiệp vụ có dữ liệu; liệt kê partial/split/batch/refund/fees chưa hỗ trợ. Lập dataset labeled matches và quyền sử dụng.
- Đầu ra: reconciliation_scope.md.
- Kiểm chứng: Có negative pairs gần giống để đo false match, không chỉ positive examples.

### P15-T02 — Mô hình evidence graph

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Giữ records nguyên bản; links/assertions tham chiếu revision, allocation và provenance. Quan hệ chi nhánh/pay-on-behalf cần chứng cứ riêng.
- Đầu ra: evidence graph schema.
- Kiểm chứng: Source revision đổi làm link stale, không tự chuyển CONFIRMED sang revision mới.

### P15-T03 — Candidate generation

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Dùng references, identity, currency, date window, amount với normalization version; giới hạn candidate set, không biến similarity thành chứng cứ pháp lý.
- Đầu ra: candidate generator.
- Kiểm chứng: Hai payment cùng tiền/ngày không tự chọn một; lưu candidate rationale.

### P15-T04 — Confirmation và allocation

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Reviewer xác nhận/reject, phân bổ partial/batch theo Decimal và ràng buộc tổng không vượt payment. Hỗ trợ undo bằng event mới.
- Đầu ra: match review + allocation validator.
- Kiểm chứng: Không dùng cùng khoản tiền chứng minh hai invoice vượt amount; audit trước/sau đủ.

### P15-T05 — Period completeness

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Xác định nguồn ledger đủ supplier/day, ingestion range, late updates và freshness; daily aggregate chỉ tính khi có completeness assertion phù hợp.
- Đầu ra: period coverage service.
- Kiểm chứng: Single invoice dưới 5 triệu không tự kết luận khỏi non-cash nếu aggregate chưa biết.

### P15-T06 — Tạo composite evaluation context

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Định nghĩa capability profile composite, provenance từ links confirmed và versions; re-plan khi assertion/record thay đổi. Không sửa capability của raw OCR/XML để giả đã có bank.
- Đầu ra: composite context builder.
- Kiểm chứng: Unknown/stale evidence vẫn unresolved; payment ref có thực nhưng không liên quan không được dùng.

### P15-T07 — Đánh giá precision và legal cases

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Đo false match/recall, review load, allocation correctness; nghiệp vụ xác nhận ca thanh toán hộ, bù trừ, trả chậm theo căn cứ áp dụng.
- Đầu ra: reconciliation_eval_report.
- Kiểm chứng: Không claim legal payment proof chỉ vì matching score cao.

### P15-T08 — Pilot và gate riêng

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy trên phạm vi tenant/period được chọn, theo dõi stale links và correction cascades; không bật auto-confirm ngoài supported policy.
- Đầu ra: pilot_report + gate_15.md.
- Kiểm chứng: Re-evaluation có snapshot đầy đủ, gate fail thì giữ manual confirmation, core MVP vẫn hoạt động.

## 5. Tiến độ bên trong chặng

- Ngày 1–2: scope, labels và evidence graph.
- Ngày 3–5: candidates/confirmation/allocation.
- Ngày 6–8: period completeness và composite planning.
- Ngày 9–15 dự phòng: legal edge cases, pilot và đánh giá lại ước lượng.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Một payment trả nhiều invoice và ngược lại.
- [ ] Phí ngân hàng/ngoại tệ/refund không khớp total đơn giản.
- [ ] Bên thứ ba thanh toán hộ không có authorization evidence.
- [ ] Ledger thiếu một ngày hoặc cập nhật muộn.
- [ ] Reviewer sửa invoice sau khi link đã confirmed.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** M5: matches/allocations/period completeness có evidence, audit và metrics trên phạm vi pilot; chưa đạt precision target thì manual-only. Không gọi đây là coverage pháp luật đầy đủ.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_15.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: Bản mở rộng composite-source có release manifest riêng; quay lại PLAN_14 cho feature này trước release vận hành.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
