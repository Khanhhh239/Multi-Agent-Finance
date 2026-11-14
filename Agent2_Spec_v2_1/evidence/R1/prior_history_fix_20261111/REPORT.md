# Sửa BR-08 — phân biệt lịch sử thiếu nguồn với số 0

Ngày 11/11/2026, CR-011, spec 2.1. **R1 READY_FOR_REVIEW**, chưa DONE hoặc duyệt production. Phạm vi: sửa lỗi được người dùng giao trong R1; không fit/chấm ML, đổi trọng số hay nối hàng đợi nghiệp vụ.

## Kết quả và cách hiểu

Phân bổ H0 trị giá 4 triệu đã được biết, trỏ hóa đơn I001 revision 2; revision đó chưa khả dụng tại thời điểm T001. Trước sửa, adapter bỏ qua phân bổ và xuất lịch sử 0. Sau sửa:

| Trường | Kết quả khi thiếu nguồn |
|---|---|
| prior_invoice_payment_count | null |
| prior_invoice_allocation_log_abs | null |
| prior_invoice_allocation_negative | null |
| missing mask của ba cột | true |
| missing reason | prior_invoice_history_incomplete |
| evidence.prior_signed_allocation_vnd | null; không hiển thị tổng một phần |
| evidence.prior_invoice_history.status | unavailable |
| evidence.records | Giữ phân bổ đã biết A_H0 |
| unavailable_references | Source allocation, field invoice_ref, target I001 revision 2, thông báo/cách xử lý |

Thông báo: **“Chưa đủ dữ liệu: phiên bản hóa đơn được phân bổ lịch sử tham chiếu chưa khả dụng tại thời điểm phân tích.”** Cách xử lý yêu cầu đối chiếu đúng bản ghi và thời điểm nguồn, tạo snapshot mới khi bổ sung, không lùi thời gian nguồn. Không xuất giá trị hoặc timestamp từ revision chưa khả dụng.

Tình huống đủ nguồn vẫn giữ số thật: không có khoản trước trong tập nguồn nhìn thấy → count/log/signed total 0; 4 triệu cộng điều chỉnh -4 triệu → tổng 0 nhưng count vẫn là một khoản trả. Không biến một phần lịch sử đã tính được thành tổng đầy đủ khi còn liên kết liên quan chưa giải được.

## Triển khai và tương thích

- Thay `agent2/sme_fraud/snapshot_features.py`, giữ lõi `features.py`, validator, auth, store và fixture chuẩn. Raw/import vẫn giữ quyền ghi xác minh; nhánh đọc snapshot của BR-07 vẫn được kiểm lại bằng regression.
- Chỉ xét phân bổ trước nhóm, cùng doanh nghiệp, invoice ID hiện liên quan và transaction ID thuộc lịch sử hợp lệ. Revision invoice/transaction được tham chiếu phải khả dụng; thiếu một trong hai làm thống kê prior unavailable. Phân bổ/hóa đơn không liên quan không làm mất thống kê invoice khác.
- Thiếu nguồn không làm mất cả dòng hoặc các feature không phụ thuộc. Tỷ lệ phân bổ hiện tại và feature tiền/lịch/graph đủ nguồn vẫn được tính.
- Contract **snapshot-point-in-time/1.1.0**, ordered schema vẫn **33 cột**. Evidence thêm `prior_invoice_history`; exact prior total cũng null khi không có liên kết hiện tại đầy đủ. Fingerprint mới phân biệt semantics missing, không sửa artifact cũ hoặc tự nhận model/cache fingerprint khác là tương thích.
- `available` chỉ mô tả các liên kết trong tập nguồn nhìn thấy tại snapshot/cutoff, không xác nhận đầy đủ toàn bộ sổ bên ngoài hệ thống. Chưa phải đối chiếu nghĩa vụ hoàn chỉnh của R4 hoặc xác minh chứng từ thật.

## Kiểm chứng đã lưu

- Trước sửa: 11 ca mới, **6 failure / 4 error / 1 pass**; có lỗi 0 thay vì null và thiếu metadata giải thích. [Kết quả](before_tests.json), [log](before_tests.log). Hai ca bổ sung kiểm effective-time và tách missing theo doanh nghiệp được thêm sau đó, không thay giá trị kỳ vọng hoặc tolerance để làm pass.
- Sau sửa: **52 focused tests pass**, gồm 13 ca mới và các ca snapshot feature/quyền đọc BR-07. [Kết quả](focused_tests.json), [log](focused_tests.log).
- Kiểm revision đến muộn hoặc chưa hiệu lực, tổng lịch sử chỉ đủ một phần, revision transaction thiếu, số 0 thật, số âm triệt tiêu, invoice không liên quan, nguồn chưa được biết, tách DN trùng ID, đảo thứ tự nguồn, replay sau này và artifact persisted có null/mask/provenance.
- T001 giữ null ở lần chạy sau; NEXT01 khi đã đủ nguồn dùng được lịch sử 17 triệu/3 khoản trả. Không điền ngược nguồn mới vào feature quá khứ.
- Bộ rà nghiệp vụ **8/8 ca pass**, gồm BR-07 và BR-08; **528 ô số/null** của fixture chuẩn vẫn khớp phép tính độc lập. [Kết quả](business_review/review_checks.json), [log](business_review.log).
- [Ví dụ thiếu nguồn thực tế từ ca rà](business_review/unknown_prior_invoice_observed.json) lưu cả null, missing reason, phân bổ và tham chiếu cần đối chiếu. Đây là nguồn mô phỏng, không phải chứng từ xác nhận nghiệp vụ thật.
- Demo chạy thành công: [log](demo.log). Numeric/missing/rows của fixture chuẩn trước/sau được đối chiếu trong `parity.json`; evidence thay đổi theo version đã công bố.
- Chạy formal R1: **527 tests / 7 mandatory IDs pass**, 0 skip/failure/error, 168,080 giây. Checker exit 0, READY_FOR_REVIEW, run_id `5759a8dd-9b06-4143-aaca-640fa1e876c2`, release_approved=false. [Log formal](formal_run.log), [native results](native_tests.json), [checker](checker_result.json); tổng hợp nguồn/lệnh/hash tại `provenance.json`. Bản root evidence trước lần chạy giữ tại các tệp `prior_*`, các báo cáo CR-008/009/010 không bị ghi đè.

## Chạy lại ca sửa

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py `
  --suite test_prior_invoice_history --report agent2/.runtime/prior-history-tests.json
```

R1 chỉ được ghi tối đa READY_FOR_REVIEW sau gate kỹ thuật mới. Reviewer nghiệp vụ thật chưa được chỉ định; không ghi DONE hay phê duyệt production từ fixture mô phỏng. Các quyết định dữ liệu thật/triển khai và chất lượng còn mở theo 99 giữ nguyên phạm vi.
