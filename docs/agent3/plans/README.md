# Lộ trình triển khai Agent 3 — OCR/PDF trước

Ngày lập: **11/10/2026**. Nguồn thiết kế: [NEW_PLAN.md](../NEW_PLAN.md).

Bộ này chia thiết kế thành **16 kế hoạch triển khai**, theo hướng OCR/PDF trước: đọc chứng từ → CFR có evidence → quality → người dùng sửa → luật thuế → mở rộng nguồn. Mỗi PLAN có task IDs, đầu ra, kiểm chứng, lịch nội bộ và gate bàn giao. **PLAN_00 DONE kỹ thuật; PLAN_01 DONE nền móng; PLAN_02 DONE ingestion; PLAN_03 DONE OCR/layout kỹ thuật; PLAN_04 DONE extraction/CFR kỹ thuật; PLAN_05 DONE quality/manual kỹ thuật, calibration/release PENDING; PLAN_06 DONE capture/review kỹ thuật, real/browser acceptance PENDING; PLAN_10-15 chưa triển khai.** Xem [gate PLAN_00](evidence/gate_00.md), [gate PLAN_01](evidence/gate_01.md), [gate PLAN_02](evidence/gate_02.md), [gate PLAN_03](evidence/gate_03.md), [gate PLAN_04](evidence/gate_04.md), [gate PLAN_05](evidence/gate_05.md), [gate PLAN_06](evidence/gate_06.md) và [quyết định phạm vi](evidence/plan00/technical_scope_decision.md); real-data acceptance còn mở ở PLAN_05–06.

PLAN_07–09: IMPLEMENTED_TECHNICAL; legal approval/taxonomy mappings và P09-T06 PENDING. [Gate PLAN_07](evidence/gate_07.md), [gate PLAN_08](evidence/gate_08.md), [gate PLAN_09](evidence/gate_09.md). PLAN_10–15 chưa triển khai; OCR V2 và nghiệm thu dữ liệu thực PLAN_05–06 vẫn mở.

## 1. Thứ tự thực hiện và phạm vi các mốc

1. **M0 — nền móng:** PLAN_00–01. Khóa scope, dữ liệu, contracts, runtime và lưu trữ.
2. **M1 — MVP đọc chứng từ:** PLAN_02–06. Upload PDF/ảnh, đọc native text/OCR, trích field, review/correction/rederive và export CFR. Chưa có kết luận thuế.
3. **M2 — MVP compliance:** PLAN_07–09. Registry/taxonomy/planning, ZEN và template explanation. Chỉ kết luận trên ruleset/source scope đã chứng minh.
4. **M3 — mở rộng nguồn:** PLAN_10–11. XML, Excel và bank. Bank chưa tự đối soát vào invoice.
5. **Nhánh tùy nhu cầu:** PLAN_12 giải thích LLM; PLAN_13 một ERP connector. Không là điều kiện bắt buộc của M2/M3.
6. **M4 — vận hành:** PLAN_14 cho chính những feature chọn phát hành; bảo mật tối thiểu đã thực hiện từ PLAN_01–02.
7. **M5 — sau MVP:** PLAN_15 đối soát nhiều nguồn, có dataset/gate riêng và phải hardening bổ sung trước release.

NEW_PLAN vẫn là hợp đồng kiến trúc. Thứ tự thực hiện ở bộ này thay cho thứ tự XML-first tại mục 1.3/17 của bản thiết kế. Đây là thay đổi thứ tự sản phẩm theo yêu cầu OCR/PDF trước, không miễn các invariant. XML-first có thể rút ngắn thử luật nhưng chưa chứng minh được đường OCR; bộ này ưu tiên hoàn thành đường OCR có review trước.

## 2. Bảng tiến độ và ước lượng

Đơn vị là **ngày công của một người làm tập trung**, không phải deadline lịch. Khoảng cộng dồn giả sử làm lần lượt mọi chặng trong bảng; các nhánh tùy chọn có thể bỏ. Chưa tính chờ gán nhãn, giấy phép dữ liệu, GPU, tài khoản, pháp lý hoặc sandbox. Không dùng các khoảng này như cam kết khi chưa qua PLAN_00.

| Kế hoạch | Kết quả chính | Ngày công | Cộng dồn nếu làm tất cả | Trạng thái |
|---|---|---:|---:|---|
| [PLAN_00](PLAN_00_SCOPE_DATASET.md) | Chốt scope và bộ fixture kỹ thuật | 2–3 | 2–3 | DONE — technical-functional-v1 |
| [PLAN_01](PLAN_01_CONTRACT_FOUNDATION.md) | Hợp đồng dữ liệu, runtime và nền lưu trữ | 3–5 | 5–8 | DONE — capture-foundation-v1 |
| [PLAN_02](PLAN_02_INGESTION_PDF.md) | Upload, phân loại và đọc PDF theo trang | 3–5 | 8–13 | DONE — ingestion-v1, 12/10/2026 |
| [PLAN_03](PLAN_03_OCR_LAYOUT_BRIDGE.md) | OCR, layout và cầu nối benchmark vào ứng dụng | 4–6 | 12–19 | DONE — ocr-layout-v1 kỹ thuật, 12/10/2026 |
| [PLAN_04](PLAN_04_EXTRACTION_CFR.md) | Trích xuất field, line items và chuẩn hóa CFR | 5–8 | 17–27 | DONE kỹ thuật; [gate](evidence/gate_04.md) |
| [PLAN_05](PLAN_05_QUALITY_CALIBRATION.md) | Data Quality, hiệu chỉnh confidence và chính sách review | 4–6 | 21–33 | DONE phần kỹ thuật/manual; calibration/release PENDING; [gate](evidence/gate_05.md) |
| [PLAN_06](PLAN_06_REVIEW_CAPTURE_MVP.md) | Review, sửa dữ liệu và nghiệm thu MVP đọc chứng từ | 4–6 | 25–39 | DONE kỹ thuật/manual; real/browser acceptance PENDING; [gate](evidence/gate_06.md) |
| [PLAN_07](PLAN_07_LEGAL_TAXONOMY_PLANNING.md) | Legal Registry, VAT taxonomy và Rule Planning | 6–9 | 31–48 | IMPLEMENTED kỹ thuật; legal/mapping PENDING; [gate](evidence/gate_07.md) |
| [PLAN_08](PLAN_08_ZEN_RULES_AGGREGATION.md) | GoRules ZEN, Decimal, trace và tổng hợp kết quả | 4–6 | 35–54 | IMPLEMENTED kỹ thuật; legal release PENDING; [gate](evidence/gate_08.md) |
| [PLAN_09](PLAN_09_COMPLIANCE_MVP.md) | Tích hợp compliance, giải thích bằng template và nghiệm thu | 4–6 | 39–60 | IMPLEMENTED kỹ thuật; T06/M2 pháp lý PENDING; [gate](evidence/gate_09.md) |
| [PLAN_10](PLAN_10_INVOICE_XML.md) | Bổ sung Invoice XML trên cùng pipeline | 3–5 | 42–65 | NOT_STARTED |
| [PLAN_11](PLAN_11_EXCEL_BANK.md) | Excel và bank statement, không suy diễn đối soát | 5–8 | 47–73 | NOT_STARTED |
| [PLAN_12](PLAN_12_RAG_EXPLANATION.md) | RAG và LLM giải thích có kiểm soát — tùy chọn | 3–5 | 50–78 | NOT_STARTED |
| [PLAN_13](PLAN_13_ERP_CONNECTOR.md) | ERP connector và adapter registry mở rộng | 4–7 | 54–85 | NOT_STARTED |
| [PLAN_14](PLAN_14_PRODUCTION_HARDENING.md) | Bảo mật, quan sát, tải và phát hành có thể phục hồi | 5–10 | 59–95 | NOT_STARTED |
| [PLAN_15](PLAN_15_RECONCILIATION_FUTURE.md) | Đối soát invoice–payment–ledger — sau MVP | 8–15 | 67–110 | NOT_STARTED |

| Mốc | Phạm vi | Ước lượng tích lũy |
|---|---|---:|
| M0 | PLAN_00–01 | 5–8 ngày công |
| M1 | PLAN_00–06 | 25–39 ngày công |
| M2 | PLAN_00–09 | 39–60 ngày công |
| M3 | PLAN_00–11 | 47–73 ngày công |
| M4 tối thiểu, bỏ nhánh tùy chọn | PLAN_00–11 + PLAN_14 | 52–83 ngày công |
| Có cả LLM và một ERP, chưa đối soát | PLAN_00–14 | 59–95 ngày công |
| Tất cả gồm đối soát | PLAN_00–15 | 67–110 ngày công |

PLAN_15 chỉ là ước lượng sơ bộ cho lát cắt đối soát chưa khóa. Sau M1 và M2 phải ước lượng lại phần còn lại dựa vào tốc độ thực, chất lượng dữ liệu và hạn chế đã phát hiện. Nghiệm thu theo gate, không theo số ngày đã trôi qua.

## 3. Phụ thuộc và phần có thể chuẩn bị đồng thời

| Chặng | Gate cần có | Có thể chuẩn bị độc lập | Không được làm tắt |
|---|---|---|---|
| 00 | Không | Inventory và tìm dữ liệu có quyền dùng | Tự bịa nhãn còn thiếu |
| 01 | 00 kỹ thuật (đã PASS) | Đọc runtime requirements hiện hữu | Đổi env/database cũ để thử schema mới |
| 02 | 01 | Fixture PDF hỏng/rotate | OCR mọi trang mà mất geometry gốc |
| 03 | 02 | Kiểm kê adapter/model/env | Import hai package src vào cùng namespace |
| 04 | 01,03 | Thiết kế annotation và candidate schema | Gán heuristic score thành calibrated confidence |
| 05 | 04; DQ-02/03/05 trước accuracy freeze/calibration | Viết metric definitions từ PLAN_00 | Tune trên frozen test |
| 06 | 02–05; DQ-01–05 trước nghiệm thu thực tế | Mock evidence UI từ schema v1 | Correction bỏ rederive Layer 5 |
| 07 | 01,05,06 | Đọc PDF luật và thiết kế taxonomy từ sớm | Publish rules chưa có căn cứ hoặc lấp UNKNOWN |
| 08 | 07 | Chạy spike ZEN đã có; thiết kế money boundary | Dùng float tiền và no-hit→PASS |
| 09 | 06–08 | Soạn template từ hợp đồng output | Để LLM tính hoặc đổi verdict |
| 10 | 09 | Inventory XML families/XXE fixtures | Mặc định mọi XML là invoice hợp lệ |
| 11 | 09,10 | Inventory Excel/bank template | Tự coi bank payment liên quan invoice |
| 12 | 09 | Version hóa corpus theo registry | Chặn core MVP vì chờ LLM |
| 13 | 09 + sandbox | Chọn một ERP và schema | Ghi integration done chỉ bằng mock |
| 14 | 09 + mọi feature release | Threat review và capacity assumptions từ sớm | Trì hoãn tenant auth/upload limits đến cuối |
| 15 | 11 và/hoặc 13;14 baseline | Scope/dataset matching | Auto-match chỉ từ amount/date giống nhau |

Chuẩn bị đồng thời ở đây là lựa chọn tổ chức công việc, không giả định có nhiều người. Thứ tự đọc PLAN_12→13→14 không có nghĩa PLAN_14 bắt buộc triển khai LLM/ERP; chọn nhánh trong release scope rồi mới tính lịch.

## 4. Những hợp đồng giữ nguyên qua mọi chặng

- **Field semantics:** PRESENT không null; UNKNOWN direction phải AMBIGUOUS/null; confidence basis và validation độc lập. Thiếu dữ liệu không là vi phạm hoặc tuân thủ.
- **Money:** Decimal nội bộ, serialization chính xác; không float ở API/storage/engine boundary. ZEN phải qua spike trong miền hỗ trợ trước money rules.
- **Identity:** tenant có nhiều taxpayer; mỗi record pin taxpayer master revision. Không tự cắt MST chi nhánh. item_id immutable, khác line number; correction có expected_revision.
- **Evidence:** giữ raw/observed và derived riêng; evidence truy ngược document/page/span/geometry. Raw OCR không thấy field không đủ chứng minh CONFIRMED_ABSENT.
- **VAT:** TAXABLE_RATE/KCT/KKKNT rõ ràng; 0% khác không chịu thuế. Legal category có taxonomy evidence độc lập observed rate.
- **Planning:** applicability tri-state; missing date không chọn latest. Record missing không biến thành source out of scope; unknown/discovery incomplete không cho false FULL/PASS.
- **Execution:** mọi eligible unit độc lập được chạy; unit ERROR không thành REVIEW/PASS; duplicate/stale/missing outcomes được kiểm. Rule/unit counts tách biệt.
- **Review:** sửa → revision mới → rederive Layer 5 → quality Layer 6 → planning/rules khi đã tích hợp. Không tái dùng outcome revision cũ.
- **Output:** precedence FAIL > REVIEW > NO_VERDICT > PASS_WITHIN_SCOPE > PASS; FAIL vẫn giữ review/errors. Contract error có verdict null. PASS luôn giới hạn trong snapshot/ruleset đã nêu.
- **Explanation/security:** template trước LLM, LLM không đổi kết luận. Tenant isolation, file bounds, masked logs và audit bắt đầu ngay từ nền móng.

## 5. Đích tổ chức code và tài liệu bàn giao

Đây là cây **dự kiến**, không tạo scaffold trong lần chia kế hoạch này. Giữ code, dataset, models và env hiện có tại chỗ.

```text
agent3_tax_compliance/
  src/
    app.py                   # app factory; API legacy vẫn tách riêng
    domain/                  # CFR, FieldObject, evidence, money, identities
    persistence/             # migrations/repositories; tránh src/database.py cũ
    ingestion/               # upload, detection, PDF pages, transforms
    adapters/                # OCR bridge, XML, Excel, bank, ERP
    extraction/              # field candidates, tables
    canonicalization/        # normalization và rederive
    quality/                 # validity, completeness, calibration
    review/                  # tasks, correction transactions
    legal_registry/ taxonomy/ planning/
    rules/                   # adapter, trace, outcomes, aggregation
    orchestration/ explanation/ api/v1/
    reconciliation/          # chỉ sau MVP
  contracts/ configs/ migrations/
  tests/                     # unit/contract/integration/e2e theo chặng
docs/agent3/plans/
  README.md                  # tiến độ tổng
  PLAN_00_...md ... PLAN_15_...md
  evidence/                  # tạo khi triển khai; gate reports không chứa PII
```

Không thay database legacy bằng schema mới. Không copy thư mục env/model lớn. OCR worker dùng interpreter/cwd riêng và protocol versioned, không ghép sys.path của hai project có package src.

## 6. Quy tắc cập nhật tiến độ và bằng chứng

Trạng thái: **NOT_STARTED → IN_PROGRESS → VALIDATING → DONE**. **BLOCKED** chỉ dùng khi có phụ thuộc thật chưa đáp ứng, phải ghi rõ điều kiện gỡ; quay lại IN_PROGRESS sau khi được giải quyết. Đây là trạng thái tài liệu quản lý công việc, không tự tạo goal ở hệ thống agent.

Khi làm một PLAN:

1. Ghi owner, ngày bắt đầu và phiên bản input trong nhật ký bên dưới.
2. Tick task chỉ khi có output + verification; task có scaffold nhưng chưa chạy vẫn đang làm.
3. Lưu report ở `evidence/gate_XX.md`, kèm command/cwd/runtime/config/hash, số mẫu và kết quả. Dữ liệu thật ở storage hạn chế, không commit chứng từ vào report.
4. Gate chưa qua thì không chuyển DONE; nêu blocker hoặc giảm phạm vi có decision record, cập nhật cả dependencies và estimates.
5. Sau gate ghi bàn giao và version cho chặng sau; việc thay contract phải ghi migration/backward compatibility rồi chạy lại consumers bị ảnh hưởng.

| Ngày | PLAN / task IDs | Trạng thái trước → sau | Bằng chứng / đầu ra | Blocker và bước tiếp |
|---|---|---|---|---|
| 11/10/2026 | Bộ tài liệu PLAN_00–15 | Đã lập kế hoạch; chưa triển khai | Các PLAN và bảng dependency này | Bắt đầu P00-T01; chưa có gate implementation |
| 11/10/2026 | P00-T01/02/03/07/08; T04/05/06 một phần | NOT_STARTED → IN_PROGRESS → BLOCKED một phần | [Gate report](evidence/gate_00.md): 30 synthetic files, 1.153 receipt sources kiểm hash, schemas/metrics; 8 exact duplicate groups cross legacy splits | Chờ dataset phù hợp và second reviewer; [nguồn tải](evidence/plan00/data_sources_and_downloads.md) đã chuẩn bị |
| 11/10/2026 | Kiểm dữ liệu FATURA2 vừa tải | BLOCKED một phần → giữ nguyên | [Download audit](evidence/plan00/fatura_download_check.md): MD5/CRC/50.004 extracted files PASS, 10.000 generated instances | Annotation mapping, template splits, điều kiện sử dụng và review; PDF/invoice Việt Nam vẫn thiếu |
| 11/10/2026 | Bước 1–4 chuẩn bị FATURA | Đã xong technical preparation; gate chung giữ BLOCKED một phần | [Mapping/pilot report](evidence/plan00/fatura_preparation_report.md): 20.000 variant annotations, 30/10/10 templates, 50 pilot AI-reviewed, schemas/tests | Còn independent human review/terms và PDF/invoice Việt Nam; chưa chạy OCR/train |

| 11/10/2026 | Chốt scope PLAN_00 theo yêu cầu người dùng | BLOCKED một phần → DONE kỹ thuật | [Decision record](evidence/plan00/technical_scope_decision.md), [gate kỹ thuật](evidence/gate_00.md), verify-only PASS | PLAN_01 đủ đầu vào; DQ-01–05 chuyển PLAN_05–06, chưa claim real accuracy |
| 11/10/2026 | P01-T01–08 | NOT_STARTED → IN_PROGRESS → VALIDATING → DONE | [gate_01](evidence/gate_01.md): isolated runtime, 22 tests, 17 schemas, 7 positive/4 negative examples, 2 legacy DB hashes unchanged | PLAN_02 nhận contracts/repositories/config; OCR/auth data API/calibration chưa hiện thực |
| 12/10/2026 | P02-T01–08 | NOT_STARTED → IN_PROGRESS → VALIDATING → DONE | [gate_02](evidence/gate_02.md): 45 tests, 7 schemas, 30 original + 11 extra fixtures, auth/upload/reader/queue/recovery, legacy DB unchanged | PLAN_03 nhận page artifacts/routes/native blocks/outbox; chưa chạy OCR model hoặc field extraction |
| 12/10/2026 | P03-T01–08 | NOT_STARTED → IN_PROGRESS → VALIDATING → DONE kỹ thuật | [gate_03](evidence/gate_03.md): 67 tests, 11 schemas, 3 cấu hình × 10 mẫu, 38 tài liệu/41 trang; Tesseract PSM 3, JSONL/layout/cache/recovery | PLAN_04 nhận normalized blocks/evidence/raw responses; quality thực tế/calibration chưa nghiệm thu |
| 12/10/2026 | P03 bổ sung model switch | DONE → VALIDATING → DONE kỹ thuật | [Model switch](evidence/plan03/model_switch/README.md): mặc định PP-OCRv6 + VietOCR; registry engine, 72 tests, 12 schemas, 5 tài liệu/6 trang | PLAN_04 giữ hợp đồng chung; detector score chưa phải recognition/field confidence |
| 12/10/2026 | P04-T01–09 | NOT_STARTED → IN_PROGRESS → VALIDATING → DONE kỹ thuật | [gate_04](evidence/gate_04.md): 99 tests, 7 schema mới; 15 tài liệu/17 trang; extraction/CFR/Decimal/identity/VAT/rederive/DAG/evidence/API | PLAN_05 nhận candidates và 12 field lỗi development; mọi CFR review; DQ-01–05 vẫn mở |
| 13/10/2026 | P05-T01/02/03/06/08; T04/05/07 phần công cụ | NOT_STARTED → IN_PROGRESS → VALIDATING → PASS kỹ thuật/manual | [gate_05](evidence/gate_05.md): 133 tests, 12 schemas; 15 tài liệu, review 100%, auto-accept 0, 211 score rows audit | Calibration thực tế/threshold/frozen release PENDING vì DQ-01/02/03/05; PLAN_06 kỹ thuật/manual có thể tiếp tục |

Mẫu `evidence/gate_XX.md` khi thực hiện:

```text
PLAN / owner / ngày:
Input dataset/schema/config/model/rules/legal versions + hashes:
Scope thực sự nghiệm thu; phần bị loại và lý do:
Task IDs hoàn tất + artifact paths:
Commands + cwd + runtime:
Kết quả test/eval, số mẫu, tử số/mẫu số, giới hạn thống kê:
Known issues + severity + next action:
Replay/recovery evidence nếu liên quan:
Gate PASS/FAIL/BLOCKED + lý do:
Versions bàn giao và estimate phần còn lại:
```

Không tạo sẵn báo cáo gate PASS; chưa có code/test run thì ghi chưa có bằng chứng.

## 7. Kiểm chứng và lệnh chạy

Lần chia kế hoạch chỉ sửa tài liệu. Không cài dependency, chạy OCR benchmark nặng hoặc gọi API/model ngoài. Khi triển khai, ưu tiên test hợp đồng ở ranh giới mới, fixtures cho lỗi/retry, accuracy eval trên nhãn thật; không viết test chỉ lặp lại code.

**Lệnh có tài sản hiện hữu:** đọc README của từng benchmark trước khi chạy. Spike ZEN hiện có có thể chạy từ workspace root bằng môi trường prototype để tái hiện quan sát; đây không là gate của runtime mới:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\spike_zen_contract.py
```

**Lệnh hiện hành sau PLAN_01:** `.venv` đã tạo và contract tests đã chạy; không cần pytest trong runtime nền móng. Từ thư mục project:

```powershell
# cwd: D:\financial\agent3_tax_compliance
.\.venv\Scripts\python.exe -m unittest discover -s tests/contracts -p test_*.py -v
# Chặng sau: chạy thư mục test vừa triển khai và integration consumers bị ảnh hưởng.
```

Các command benchmark riêng chạy ở `data invoice/ocr_e2e_workflow` theo [runbook hiện có](<../../../data invoice/ocr_e2e_workflow/MANUAL_RUNBOOK.md>); không import package src của benchmark vào backend. Không chạy toàn bộ benchmark chỉ để nghiệm thu thay đổi tài liệu.

## 8. Đối chiếu toàn bộ NEW_PLAN

| Mục thiết kế | PLAN chịu trách nhiệm chính | Bằng chứng cần có |
|---|---|---|
| 1. Mục tiêu, phạm vi, legal sources | 00,07,09 | Scope card, registry, acceptance scope |
| 2. Kiến trúc 11 layers | 01,09 | Module contracts và workflow snapshot |
| 3. Envelope/detector/router/capability | 01–03,07,10–11,13 | Registry thống nhất, route/profile fixtures |
| 4.1 ERP | 13 | Sandbox integration |
| 4.2 XML | 10 | Parser/fidelity/security |
| 4.3 Excel | 11 | Mapping/version/cell provenance |
| 4.4 OCR/PDF | 02–06 | Geometry, bridge, extraction và review |
| 4.5 Bank | 11 | Bank semantics và source capabilities |
| 5. CFR/field/examples | 01,04,10–11 | Schema + money/identity/partial record tests |
| 6. Quality/calibration | 05 | Calibration card, policy và holdout report |
| 7. Planning/gates/units | 07 | Tri-state/date/observations/units matrix |
| 8. Review/correction | 06,09 | Atomic revision, rederive và reevaluation |
| 9. ZEN/rules/legal mapping | 07–08,15 | Legal evidence, money spike, rule truth tables |
| 10. RAG/LLM | 09,12 | Template baseline, grounded claims/fallback |
| 11. Aggregation/output/audit | 01,08–09 | Negative outcome tests, audit replay |
| 12. API/async/idempotency | 02,06,09,11,13–14 | Cursor/retry/concurrency/recovery |
| 13. Testing/golden/metrics | 00 và tất cả gate | Dataset card và per-stage evidence |
| 14. Security/monitoring | 01–02,06,14 | Tenant isolation sớm, capacity/restore về sau |
| 15. Extensions/reconciliation | 10–13,15 | Adapter cards, match/period assertions |
| 16. Risks | 00,03,05,08,14–15 | Scope limits, spike, quality/capacity reports |
| 17. MVP/estimates/phases | README này,00–15 | Thứ tự OCR-first, estimates theo gate |
| Phụ lục state/sequence/semantics | 06,08–09 | Error exits, output invariants, E2E cases |

## 9. Rủi ro lịch trình phải theo dõi

| Rủi ro | Chặng phát hiện sớm | Hành động khi xảy ra |
|---|---|---|
| Receipt benchmark không đủ nhãn invoice/VAT | 00 | Bổ sung nhãn có quyền hoặc thu hẹp field scope; không gán nhãn giả |
| OCR/table accuracy thấp | 03–05 | Manual review có evidence; giới hạn family và đo lại |
| Không đủ dữ liệu calibration | 05 | Confidence UNAVAILABLE, manual path; chưa bật auto accept |
| ZEN không giữ tiền chính xác | Spike trước/đầu 08 | Chọn safe boundary có proof; money rules chưa đủ điều kiện thì block |
| Taxonomy/effective legal basis chưa rõ | 07 | UNKNOWN/review; chưa publish rule đó, vẫn chạy rule độc lập đủ input |
| Không có complete ledger/payment evidence | 07,11,15 | Không kết luận non-cash/daily aggregate; yêu cầu nguồn hoặc ngoài scope đúng policy |
| GPU/provider/ERP sandbox chưa có | 03,12,13 | Baseline chạy được/template/mock CI; không giả integration thật |
| Scope mở rộng quá MVP | Mỗi gate | Khóa release scope; chuyển feature sau M2 và ước lượng lại |

**Bước tiếp theo hiện tại:** PLAN_06 review/correction MVP kỹ thuật từ assessment/recommendations của [PLAN_05](evidence/gate_05.md), vẫn giữ manual review và auto-accept tắt. Song song cần hóa đơn Việt Nam có quyền dùng, nhãn độc lập, grouped frozen splits và business target để hoàn tất calibration/release PLAN_05. Có [runbook quality](evidence/plan05/runbook.md) và [runbook extraction/CFR](evidence/plan04/runbook.md). OCR mặc định **PP-OCRv6 + VietOCR**, có [runbook và cách đổi model](evidence/plan03/model_switch/runbook.md); PLAN_02 có [API/worker runbook](evidence/plan02/runbook.md). FATURA chưa vào calibration/release scope; MC-OCR tiếp tục QUARANTINE. Chỉ tuyên bố hỗ trợ thực tế cho family đã nghiệm thu. Chưa có compliance verdict.
