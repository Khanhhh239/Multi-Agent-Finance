# Đầu vào P1 — hợp đồng 1.1.0

Đã bổ sung nguồn để đối chiếu thanh toán vượt hóa đơn. **CR-019 đã nối [evaluator P1](P1_EVALUATION.md) khi đủ nguồn.** Dữ liệu nhập lỗi bị chặn; nguồn còn thiếu được giữ với cảnh báo và P1 unavailable, không thành số đã trả bằng 0.

## Kênh thanh toán

Gửi `contract_version: "1.1.0"` và khai báo `transactions.payment_channel`:

- `bank` hoặc `cash`: kênh nguồn xác định, dùng cho đầu vào P1.
- `other`, `unknown`, null hoặc không có trường: giữ dữ liệu nhưng P1 chưa đủ đầu vào.

Không đoán kênh từ tài khoản 111/112, bank_code, mô tả hoặc số tiền. Mapping chỉ đổi tên cột có sẵn; không tự điền giá trị. Schema 1.0.0 cũ vẫn đọc được và không nhận cột mới nếu chưa nâng phiên bản payload.

## Liên kết và tiền có dấu

Mỗi payment_allocation phải chỉ đúng transaction_ref và invoice_ref theo ID/revision trong cùng tenant/doanh nghiệp. Không tìm hóa đơn gần giống theo số tiền. Ref không tồn tại bị reject; ref chỉ được biết sau làm đầu vào quá khứ unavailable. NCC khác nhau cần đối chiếu hồ sơ chi hộ/nghĩa vụ, không tự sửa liên kết hoặc kết luận gian lận.

Giữ signed amount và adjusts_ref/adjustment_reason hợp lệ. Số phân bổ vượt giá trị hóa đơn vẫn được nhập để kiểm tra sau, không phải lỗi định dạng. Current/prior/simultaneous records được giữ cho bước đánh giá tiếp theo; bản thân và nhóm đồng thời không trở thành history của nhau.

## Phạm vi lịch sử do nguồn khai báo

Bảng tùy chọn `payment_history_coverage`, có metadata tenant/company/ID/revision/effective_at/observed_at/source, gồm:

| Trường | Ý nghĩa |
|---|---|
| invoice_refs | Các ID/revision hóa đơn xác định scope |
| covered_from / covered_through | Khoảng đóng của effective_at phân bổ được cung cấp; kết thúc không sau observed_at |
| history_basis | since_inception / bounded_period / unknown, do nguồn khai báo |
| coverage_status | complete / partial / unknown, không tự chọn từ số dòng |
| export_id | Định danh lần xuất nguồn |
| manifest | invoice_refs, transaction_refs, allocation_refs; record_counts và records_sha256 |

Manifest khóa các phiên bản nguồn đã biết tại observed_at của claim. Với since_inception, không được bỏ hóa đơn/phân bổ đã có trước covered_from. Với bounded_period, phần ngoài khoảng vẫn chưa biết, không giả opening balance bằng 0. Những phiên bản liên quan được biết mới sau export làm claim stale ở cutoff mới; claim mới nhất partial/unknown không được thay bằng claim complete cũ. Các claim cùng thời điểm mâu thuẫn cũng unavailable.

Helper `sme_fraud.p1_inputs.export_manifest(bundle, claim)` chỉ tạo danh sách refs/count/hash từ scope và mốc thời gian **đã được nguồn cung cấp**; không tạo coverage_status hoặc kết luận complete. Hash được tính trên payload canonical của invoices/transactions/payment_allocations đã chọn, sort theo ID/revision. Khi đổi dữ liệu hoặc mapping phải kiểm tra lại và xuất lại manifest phù hợp; không tự sửa checksum để bỏ qua thiếu nguồn.

Backend kiểm schema, quyền, refs, thời gian, membership, count và checksum. Manifest khớp chỉ chứng minh dữ liệu gửi khớp khai báo, **không chứng minh đầy đủ sổ bên ngoài hoặc nguồn gốc đã xác minh**. Nếu không biết phạm vi, không tạo mốc giả: để thiếu coverage hoặc khai báo trạng thái hạn chế với phạm vi thực sự có.

## Đầu ra

- ValidationReport 1.2.0 có lỗi chính xác theo bảng/dòng/trường; thiếu đầu vào có `P1_INPUT_UNAVAILABLE` cùng gaps trong analysis_limits.
- RuleInputs 1.1.1 có P1 input_details và payload riêng p1_invoices/p1_allocations/p1_transactions/p1_vendors/payment_history_coverage. Mỗi giao dịch dùng cutoff riêng, không đưa nguồn đến muộn vào quá khứ.
- P1 source ready chỉ là đủ cấu trúc/phạm vi khai báo nhất quán. Evaluator kiểm tiếp chuỗi điều chỉnh, cap và số tiền; hợp lệ mới trả hit/no-hit, mâu thuẫn vẫn unavailable/null.
- Input contract 1.0.0 vẫn dùng schema riêng; snapshot cũ không bị viết lại. Snapshot mới ghi đúng phiên bản của payload. Feature contract 33 cột không đổi, nguồn/channel/coverage không tự thành predictor hoặc nhãn.

Luồng hiện tại nhận JSON qua backend upload → preview → commit. Không bổ sung CSV/Excel hoặc UI nhập mới trong bước này. Không đổi active model, trọng số, queue hoặc kết luận accuracy.

## Mẫu và chạy thử

[Tệp mẫu 1.1.0](../tests/fixtures/input_p1_v1_1.json) là dữ liệu mô phỏng; không dùng khai báo phạm vi trong mẫu cho sổ thực tế. Nguồn xuất phải cung cấp kênh, phạm vi và manifest của chính dữ liệu đó.

Chạy từ thư mục gốc repo, chọn thư mục kết quả chưa tồn tại:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_p1_inputs.py --output-dir agent2/.runtime/p1-demo-results
```

Demo kiểm bốn trường hợp: đủ khai báo, thiếu kênh, lịch sử partial và manifest sai; đồng thời đi qua upload/preview/commit, gửi lại cùng yêu cầu và xuất đủ 6/6 kết quả. Đây là demo backend với quyền thử nghiệm cục bộ, không phải luồng đăng nhập hay đánh giá hiệu quả model.

[Báo cáo kiểm thử CR-018](../../Agent2_Spec_v2_1/evidence/R2/p1_inputs_20261111/REPORT.md): 616 kiểm thử hồi quy qua, gồm 19 ca P1 mới. Đây là evidence lịch sử trước evaluator CR-019; xem [đánh giá P1](P1_EVALUATION.md) cho trạng thái mới. R2 tổng thể vẫn PARTIAL.
