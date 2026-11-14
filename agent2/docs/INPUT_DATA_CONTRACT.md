# Hợp đồng đầu vào Agent2 — phiên bản 1.0.0 / 1.1.0

Backend hiện đọc cả 1.0.0/1.1.0 với validator/report 1.2.0, snapshot và feature R1. Phiên bản 1.1.0 thêm [đầu vào P1](P1_INPUTS.md); không tự nâng dữ liệu cũ, suy kênh hoặc coi lịch sử thiếu là 0. Các phần CR-005/006 bên dưới được giữ làm lịch sử; UI/CSV/Excel mới không thuộc bước này.

**CR-007:** đã có DB/API [snapshot bất biến](IMMUTABLE_SNAPSHOTS.md) cho tệp JSON, phiên bản nguồn/mapping/report và atomic commit có xác nhận/idempotency. Các đoạn lịch sử bên dưới về "chưa có snapshot" mô tả CR-005; phần UI/CSV/Excel/identity Portal/feature replay vẫn chưa triển khai.

**CR-008:** [adapter feature và job replay](SNAPSHOT_FEATURES.md) đã được nối, contract mới có allowlist/missing, tách kênh ID/evidence và kiểm as_of/nhóm đồng thời. UI/CSV/Excel/identity Portal và model adapter R2 còn chờ.

## Kết quả đọc Git các agent

Đã fetch ref từ `Khanhhh239/Multi-Agent-Finance`, chỉ đọc, không merge hay thay code agent khác. Nguồn tích hợp mới nhất được kiểm tra là `platform-Khanh` tại commit `140a741e7290e70a783496e56e9ef48268a00f5d` ngày 10/11/2026; local vẫn ở nền `3cae5a3`. Nhánh riêng cũng được kiểm kê, nhưng hợp đồng trong bản platform là mốc tích hợp được dùng để đối chiếu. File/hash cụ thể: [UPSTREAM.json](../../shared/finance_input/UPSTREAM.json).

| Thành phần | Có thể dùng chung | Giới hạn và quyết định |
|---|---|---|
| Agent1: `agent1_service/ingest/money.py` | Có. Decimal → integer đơn vị nhỏ nhất, không float/làm tròn, giữ dấu | Trích nguyên file vào package chung, khóa commit/hash. Profile chỉ nhận VND. Không copy toàn bộ validator công nợ. |
| Agent1: ngày và adaptive import | Có thể dùng cơ chế preview/mapping khi tích hợp sau | Parser ngày hiện chuẩn hóa về ngày VN và bỏ giờ; một số known_at có fallback; kiểm tra tiền yêu cầu dương ngoài điều chỉnh hóa đơn, chặn thu vượt hóa đơn. Không dùng nguyên cho lịch sử chi/điều chỉnh và phát hiện trả thừa Agent2. |
| Agent3: CFR, envelope, quyền, provenance | Dùng chung nguyên tắc tenant + revision, tiền chính xác, trạng thái thiếu, nguồn/xác minh | CFR là hóa đơn/thuế; tenant_id và taxpayer_id không tự bằng company_id. Không import toàn bộ Pydantic/app hoặc tự coi hóa đơn là giao dịch thanh toán. |
| Agent4: ledger generator | Dùng cách hiểu journal/line và integer để thiết kế fixture/mapping | Là simulator, không cung cấp hợp đồng nhập thực tế hay thời điểm được biết có thể tin cậy. Không coi dữ liệu sinh là chứng từ gốc. |
| Portal: phân loại file, UI nhập | Có thể tái dùng màn chọn file/mapping ở bước nối API | Portal đang gọi API Agent2 cũ đã đóng; không phải bộ validator domain chung. Chưa thay route trong công việc này. |

Kết luận: dùng chung được các phần nền tảng; **chưa có hợp đồng sẵn đủ cho Agent2**. Đã tạo package `shared/finance_input` và profile `sme_fraud/imports.py`. Các agent khác vẫn chạy hợp đồng riêng. Việc này không tuyên bố cả platform đã dùng cùng một database.

## Các bảng cần gửi

Bundle JSON có `contract_version: "1.0.0"`, `tenant_id` và các mảng dưới đây. Tất cả mảng trừ `vendor_bank_history` phải xuất hiện; có thể để `[]` khi chưa có nguồn. `companies` phải có ít nhất một bản ghi.

| Mảng | Dữ liệu chính ngoài trường chung |
|---|---|
| companies | Tên, mã số thuế nếu có; record_id bằng company_id |
| transactions | amount_vnd, currency=VND, kind, mô tả; NCC, nhân viên, người lập, ngân hàng, bút toán nếu có |
| vendors | Tên NCC; mã thuế, địa chỉ, tài khoản và mã ngân hàng nếu có |
| invoices | Số hóa đơn dạng chuỗi, amount_vnd là tổng nghĩa vụ, loại hóa đơn/điều chỉnh, NCC, hạn trả nếu có |
| payment_allocations | Tham chiếu **revision** giao dịch và hóa đơn, số tiền phân bổ; hỗ trợ nhiều–nhiều |
| employees | Tên, vai trò, ngân hàng, ngày vào/nghỉ và CCCD nếu có nguồn |
| approvals | Giao dịch, người duyệt, quyết định approved/rejected/pending, hạn mức nếu có |
| supporting_documents | Tên/loại, simulated/export/original, SHA256, đối tượng liên quan, trạng thái xác minh |
| vendor_bank_history | NCC, tài khoản/mã ngân hàng, thời điểm hiệu lực và thời điểm biết, trạng thái xác minh; tùy chọn |

Schema chi tiết, trường bắt buộc/enum/giới hạn: [input.schema.json](../../shared/finance_input/src/finance_input/input.schema.json). Ví dụ hoàn chỉnh C001/C002: [input_contract_v1.json](../tests/fixtures/input_contract_v1.json). Đây hoàn toàn là dữ liệu mô phỏng.

## Trường chung trên từng bản ghi

| Trường | Ý nghĩa |
|---|---|
| tenant_id | Phạm vi tổ chức/hệ thống được cấp quyền. Không suy từ tên công ty hay MST. |
| company_id | Mã doanh nghiệp trong tenant. |
| record_id | ID nguồn đã map ổn định, dạng chuỗi; giữ số 0 đầu. |
| revision | Số nguyên từ 1; sửa thông tin tạo revision mới. |
| observed_at | Thời điểm nguồn được hệ thống biết, ISO 8601 có múi giờ. Không lấy ngày nghiệp vụ làm mặc định. |
| effective_at | Thời điểm nghiệp vụ/hiệu lực của bản ghi, cùng định dạng timestamp có múi giờ. |
| source | system, record_id nguồn, is_simulated; content_sha256 nếu có file nguồn. |
| missing_fields | Tùy chọn: tên trường → missing / unknown / not_provided_by_source / not_applicable. Không gán cho trường đang có giá trị hay trường bắt buộc. |

Khóa bản ghi là `(tenant_id, company_id, table, record_id, revision)`. Một mã T001 ở C001 và C002 là hai bản ghi độc lập. Mọi tham chiếu được giải quyết trong cùng tenant/DN, không tìm sang DN khác. Thiếu revision hoặc nguồn tham chiếu phải sửa; không tự chọn bản ghi gần giống.

`observed_at` và `effective_at` có thể khác nhau: hóa đơn ngày 01/10 nhưng nguồn đến ngày 05/10 thì khi xem ngày 03/10 chưa được dùng hóa đơn đó. Bổ sung chứng từ/xác minh ngày 06/10 tạo revision biết ngày 06/10, không ghi đè kiến thức cũ. `records_as_of` chọn revision nhìn thấy theo cả hai mốc; đây là helper kiểm tra dữ liệu, chưa phải replay feature hay snapshot lưu trữ.

Nguồn chỉ có ngày mà không có giờ/offset cần mapping được xác nhận hoặc giờ thu nhận thực được ghi bởi collector. Không tự gán nửa đêm, UTC+07 hay dùng giờ upload để giả lịch sử đã biết. Luồng đồng thời phải được chấm từ lịch sử trước nhóm trong bước tích hợp feature sau.

## Tiền và điều chỉnh

- Canonical `amount_vnd` là số nguyên có dấu, tối đa 18 chữ số. Không float, không phân nhóm, không tự quy đổi ngoại tệ. `parse_vnd` dùng ở adapter để chuyển chuỗi số chính xác; `"100.00"` → 100, `"100.25"` bị từ chối, không làm tròn.
- Bundle canonical dùng ở backend. Khi nối web, ô tiền phải giữ chuỗi tới parser backend; không chạy qua JavaScript Number với số vượt giới hạn số nguyên chính xác của trình duyệt. DTO hiển thị cần giữ độ chính xác tương ứng, không âm thầm làm tròn số 18 chữ số.
- Khoản thông thường dùng kind payment/receipt/payroll/transfer, số tiền không âm; kind chỉ rõ bản chất dòng, chưa tự là dấu dòng tiền ngân hàng. Điều chỉnh/reversal/credit_note là **chênh lệch có dấu**; giữ nguyên dấu, cần `adjustment_reason` và `adjusts_ref` dẫn bản gốc. Không lấy trị tuyệt đối hay tự nhân âm lần nữa.
- Revision sửa nội dung của cùng bản ghi; điều chỉnh nghiệp vụ là một bản ghi riêng dẫn bản gốc. Hai cơ chế khác nhau, không cộng mọi revision thành tiền phát sinh.
- Hai giao dịch ID khác nhau trả cùng hóa đơn hoặc tổng phân bổ vượt nghĩa vụ vẫn được nhập. Đó có thể là tín hiệu cần phát hiện, không phải lỗi cú pháp để xóa mất dữ liệu.
- Bút toán `accounting_lines` giữ Nợ/Có riêng. Schema không ép một payment bằng một journal hoặc tự kết luận bút toán cân là giao dịch hợp lệ.

## Chứng từ và dữ liệu thiếu

`original` nói loại nguồn, không có nghĩa đã xác minh. File SHA256 chỉ khóa nội dung, không chứng minh đã có file trong kho hay file là thật. `verified` cần verification gồm người, thời điểm, căn cứ và quyền `evidence.verify` từ backend; không tự tạo nhãn ML. Xác minh một fixture không làm mất dấu simulated. API/chính sách xác minh nguồn thật còn phải tích hợp sau.

Thiếu lịch sử tài khoản chỉ làm `bank_change_input` unavailable và tạo warning. Có giao dịch vẫn giữ `transaction_input`; chưa có tài liệu tạo warning, không biến thành nhãn sai phạm. Capability là “có nguồn cho phần này”, không phải khẳng định đủ số mẫu để detector fit/score. Tham chiếu đã khai mà không tồn tại là lỗi, khác với trường tùy chọn chưa có nguồn.

## Dùng bộ kiểm tra

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -m pip install -r requirements-lock.txt
$env:PYTHONPATH='.;tests'
& .venv/Scripts/python.exe -X utf8 -B -m unittest test_input_contract -v
```

```python
import json
from pathlib import Path
from finance_input import AccessScope
from sme_fraud.imports import validate_input

# Context này chỉ dùng ví dụ offline. Web phải lấy từ identity/membership đã xác thực.
scope = AccessScope('demo', frozenset({'C001', 'C002'}),
                    'offline-demo', frozenset({'data.import'}))
bundle = json.loads(Path('tests/fixtures/input_contract_v1.json').read_text('utf-8'))
report = validate_input(bundle, scope)
print(report['status'], report['counts'], report['errors'])
```

Backend phải xác thực và kiểm quyền **trước khi mở file**, sau đó gọi core + profile, rồi hiển thị report. Report có status accepted / accepted_with_warnings / rejected, lỗi/cảnh báo có path, dòng trong bảng (đếm từ 1), trường, code, giải thích và cách sửa. Dòng này chưa phải dòng Excel vì chưa có adapter file; adapter cần giữ mapping về dòng gốc.

Hợp đồng hiện kiểm một tập dữ liệu đóng theo tham chiếu. Nhập tăng dần cần ghép với snapshot nền đúng quyền rồi kiểm lại, không dùng gói đơn lẻ để suy rằng dữ liệu cũ phải bị xóa. Một lỗi từ chối toàn gói; không lưu nửa gói hay bỏ dòng ngầm. Report hiện chưa là token được phép commit.

## Việc nối tiếp trong R1

Đã có quyền tại API validate qua cấu hình backend; chưa nối identity/membership Portal. Tiếp theo xây upload/parse/mapping, bản preview khóa source/mapping/context/hash, commit snapshot bất biến và idempotent. Sau đó mới map canonical record vào feature/rule/graph, replay nhóm đồng thời và kiểm đầy đủ R1-01…07 ở API. Không gọi ML, không thay ngưỡng và không tự tăng version của feature lõi chỉ vì đã có input schema.
# Cập nhật P1 — hợp đồng 1.1.0

Đã thêm [payment_channel và phạm vi lịch sử P1](P1_INPUTS.md), hỗ trợ đọc song song 1.0.0/1.1.0. Nội dung 1.0.0 bên dưới giữ làm tham chiếu; schema cũ không bị viết lại, payload mới phải khai báo đúng phiên bản.

