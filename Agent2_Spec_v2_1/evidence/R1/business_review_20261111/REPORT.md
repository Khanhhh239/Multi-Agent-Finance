# Rà dữ liệu, feature và bằng chứng R1 — 11/11/2026

**Kết luận: cần sửa hai lỗi trước khi nghiệm thu R1.** Luồng demo và phép tính trên fixture chuẩn khớp; các ca mở rộng phát hiện lỗi phân quyền khi đọc chứng từ đã xác minh và lỗi thể hiện lịch sử phân bổ thiếu nguồn thành số 0.

Đây là rà soát kỹ thuật/ngữ nghĩa dữ liệu do Codex thực hiện theo yêu cầu người dùng, trên dữ liệu mô phỏng. Không phải xác nhận chứng từ gốc, phê duyệt của kế toán hoặc kết luận về độ chính xác ML. Chưa sửa code runtime, đổi contract, fit model hay chuyển sang R2.

## Đã chạy và đối chiếu gì?

- Chạy `agent2/scripts/demo_snapshot_features.py` thành công: snapshot lưu thật trong kho demo riêng; 3 dòng C001, 33 feature; T001/T002 cùng thấy một giao dịch trước nhóm. Chạy ở mốc muộn hơn không đổi feature cũ.
- Chạy công cụ rà riêng `agent2/scripts/review_r1_business.py`. Kỳ đầu có 5 dòng của C001/C002; kỳ sau có 11 dòng, gồm số âm và số 0. Đối chiếu **528 ô số/null** (16 lượt dòng × 33 cột), khớp hoàn toàn với phép tính độc lập; sai số tuyệt đối tối đa cho phép 1e-8, theo độ làm tròn 8 chữ số của kernel được giữ lại.
- Giá trị kỳ vọng được tính từ ví dụ nghiệp vụ cố định, bằng số nguyên, `log1p`, tỷ lệ và lịch. Công cụ không dùng đầu ra của legacy kernel làm giá trị kỳ vọng. Đây chưa phải kiểm tra toàn miền giá trị hay chứng minh thuật toán cho mọi dữ liệu.
- Tra lại từng evidence reference đúng doanh nghiệp, bảng, ID, revision và hai thời điểm của bản ghi nguồn. Kiểm tra giới hạn thời điểm từng dòng và missing reason cho từng giá trị null.
- Kiểm tra thêm tài khoản ngân hàng khác nhau, hai hạn mức phê duyệt mâu thuẫn, phân bổ điều chỉnh âm, snapshot/artifact lưu thật và retry artifact trong cùng snapshot.
- Chạy lại native regression ở thư mục evidence riêng: **508 tests / 7 mandatory IDs pass**, 0 skip, failure, error, 156,763 giây. Không ghi đè kết quả nghiệm thu CR-008. Kết quả chi tiết tại `native_tests.json` và `native_tests.log`.

Nguồn: `agent2/tests/fixtures/r1_feature_replay_v1.json`; hash tại [review_checks.json](review_checks.json). Mốc job: 10/10/2026 11:00 và 13/10/2026 00:00, giờ Việt Nam.

## Đối chiếu các khoản chính

| Doanh nghiệp / giao dịch | Số tiền nguồn | Lịch sử phân bổ hóa đơn được dùng | Kết quả đã kiểm tra |
|---|---:|---:|---|
| C001 / H0 | 4.000.000 VND | 0 | Phân bổ hiện tại / hóa đơn 20 triệu = 0,20 |
| C001 / T001 | 6.000.000 VND | 4.000.000 VND, 1 khoản trả | Tỷ lệ 0,30; không thấy T002 cùng giờ |
| C001 / T002 | 7.000.000 VND | 4.000.000 VND, 1 khoản trả | Tỷ lệ 0,35; không thấy T001 cùng giờ |
| C002 / T001, T002 | 6 và 7 triệu VND | 0 | Không lấy H0 của C001 dù trùng ID danh mục/giao dịch |
| C001 / ADJ001 | **-2.000.000 VND** | Không có phân bổ hóa đơn của dòng điều chỉnh | Giữ dấu âm ở nguồn/evidence; magnitude và dấu là hai feature riêng |
| C001 / Z0001 | **0 VND** | Không có liên kết hóa đơn | Giữ dòng, log độ lớn = 0; không giả có dữ liệu magnitude lịch sử dùng được |
| C001 / NEXT01 | 8.000.000 VND | **17.000.000 VND**, 3 khoản trả | 4 + 6 + 7 triệu; không tự trừ ADJ001 khi chưa có allocation tương ứng |
| C002 / NEXT01 | 8.000.000 VND | **13.000.000 VND**, 2 khoản trả | 6 + 7 triệu, tách đúng C001 |

Riêng T001: hai dòng kế toán Nợ 331/Có 112 cùng 6 triệu, tỷ lệ lệch tổng Nợ–Có = 0; người lập trùng người duyệt được biết, tỷ lệ tiền/hạn mức approved 10 triệu = 0,60. Đây là mô tả dữ liệu, chưa chứng minh tự duyệt được phép.

DOC_KNOWN được tính là một bản ghi chứng từ mô phỏng chưa xác minh. Số chứng từ gốc đã xác minh = 0. DOC_LATE đến ngày 12/10 không thay dữ liệu dự báo của giao dịch ngày 10/10. Nhân viên và NCC cùng ngân hàng + số tài khoản nên có liên kết; khi đổi tài khoản nhân viên, overlap và số nhân viên trong graph về 0. Liên kết này không tự chứng minh gian lận.

## Hai lỗi tái hiện được

### BR-07 — P1: đọc snapshot đã xác minh lại đòi quyền xác minh

Vị trí: `agent2/sme_fraud/snapshot_features.py:165` gọi `validate_input`; `agent2/sme_fraud/imports.py:110–113` kiểm quyền `evidence.verify`.

Cách tái hiện:

1. Tạo nguồn thử với một chứng từ có trạng thái verified, đủ người/thời điểm/căn cứ xác minh. Ca này chỉ mô phỏng cấu trúc quyền, không giả là chứng từ thật.
2. Import, preview và commit bằng scope có `data.import` và `evidence.verify`: thành công.
3. Dùng scope cùng tenant/DN, chỉ có `data.import`: đọc manifest snapshot thành công.
4. Tạo feature từ chính snapshot đó: lỗi **422 FEATURE_INPUT_INVALID**.

Nguyên nhân: bộ tạo feature kiểm tra lại quyền *ghi nhận xác minh* bằng quyền của người *đọc/phân tích*. Người đọc không sửa hoặc xác minh thêm chứng từ nào. Lỗi bị bọc thành thông báo hợp đồng đầu vào nên người dùng cũng khó biết cách xử lý.

Hướng sửa: tách kiểm tra cấu trúc/toàn vẹn khi đọc snapshot đã commit khỏi kiểm tra quyền xác nhận ở bước ghi/import. Giữ quyền xác minh bắt buộc khi tạo/thay đổi trạng thái verified; không tự cấp `evidence.verify` cho người đọc hoặc tin cờ bỏ kiểm tra do client gửi. Bổ sung test reader tạo feature thành công nhưng vẫn không được tự import/xác nhận chứng từ verified.

### BR-08 — P2: thiếu revision liên quan trong lịch sử bị thể hiện như đã biết số 0

Vị trí: `agent2/sme_fraud/snapshot_features.py:232–241`, đặc biệt `if not invoice: continue`.

Cách tái hiện:

1. Phân bổ H0 trị giá 4 triệu được biết ngày 09/10, trỏ hóa đơn I001 revision 2.
2. Revision 2 chỉ được biết ngày 12/10; revision 1 đã biết từ trước. Phân bổ của T001 vẫn trỏ revision 1.
3. Validator nhận gói với cảnh báo nguồn liên quan đến muộn, đúng chủ đích giữ dữ liệu để phân tích.
4. Tại T001 ngày 10/10, không được sử dụng revision 2. Tuy nhiên adapter bỏ qua phân bổ lịch sử này và xuất ba giá trị `prior_invoice_*` = **0 / 0,0 / 0**, không có missing reason hoặc evidence giải thích phần lịch sử bị loại.

Không dùng revision tương lai là đúng. Phần cần sửa là phân biệt **“chưa có khoản trước nào trong tập đủ nguồn”** với **“có liên kết lịch sử liên quan nhưng chưa đủ nguồn để xác định tổng”**. Trong contract hiện tại, cần trả null/lý do thiếu cho thống kê bị ảnh hưởng và giữ reference của phân bổ đã biết để truy nguyên. Không lấy revision tương lai hay tự thay bằng revision 1 để điền số. Nếu đổi sang chỉ đếm phần quan sát được thì phải khai báo rõ semantics/coverage và version contract trước khi sử dụng cho model.

Đầu ra thực tế: [unknown_prior_invoice_observed.json](unknown_prior_invoice_observed.json). Ca rà mong muốn lịch sử thiếu nguồn được thể hiện rõ; hiện thất bại. Không sửa test hoặc tự coi số 0 này là tổng thanh toán đã xác nhận để làm kết quả xanh.

## Giới hạn nghiệp vụ cần giữ rõ

- Fixture có khoản điều chỉnh giao dịch -2 triệu nhưng không có allocation điều chỉnh hóa đơn. Vì vậy chưa thể dùng nó để xác nhận số dư nghĩa vụ sau điều chỉnh. Không tự suy trừ theo số tiền hoặc NCC; cần nguồn phân bổ cụ thể.
- Các tỷ lệ trong R1 dựa trên giá trị mặt hóa đơn và các allocation nhìn thấy. Chưa phải đối chiếu nghĩa vụ hoàn chỉnh, xử lý đủ credit note/hoàn tiền hoặc kết luận trả thừa của R4.
- Các bản ghi chứng từ trong fixture chuẩn đều mô phỏng/chưa xác minh. Checksum và replay đúng không chứng minh nội dung chứng từ là thật hoặc nghiệp vụ hợp lệ.
- Thử nghiệm này chưa đo precision/recall, hiệu quả tăng thêm của ML, tải lớn, hoặc kiểm thử UI Portal/CSV/Excel. Các phần đó chưa triển khai ở R1 hiện tại.

## Evidence và chạy lại

- [Kết quả từng ca](review_checks.json): 8 ca, **6 pass / 2 fail**. BR-01 gồm toàn bộ 528 đối chiếu số/null. Sáu ca đạt không xóa hai lỗi phát hiện mới.
- [Bảng đối chiếu từng giá trị](feature_reconciliation.csv).
- [Log rà](review.log); [manifest snapshot demo](demo_snapshot_manifest.json); các kênh artifact nằm trong `artifacts/`, đường dẫn chính xác tại BR-06 trong review_checks.json.
- [Native regression](native_tests.json), [log regression](native_tests.log). Bộ mandatory cũ không bao phủ hai ca BR-07/08; không thể dùng kết quả xanh của bộ đó để bác bỏ hai lỗi mới.
- `initial_review_checks.json` giữ lần chạy đầu của công cụ rà. BR-02 ban đầu so cả `row_index` giữa hai artifact có số dòng khác nhau; đã sửa oracle so provenance theo DN + ID, bỏ chỉ số vị trí cục bộ. Không sửa fixture, runtime, giá trị kỳ vọng tài chính hoặc tolerance để làm pass.

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/review_r1_business.py `
  --output agent2/.runtime/r1-business-review-rerun
```

Lệnh rà hiện trả **exit 1** vì hai ca mong muốn chưa đạt. Chạy lại vào thư mục mới để giữ nguyên evidence lần này. Lệnh native regression và metadata/checksum nguồn nằm trong `provenance.json`.

**Đề xuất tiếp theo:** sửa BR-07 và BR-08 trong phạm vi R1, chạy lại hai ca lỗi, bộ rà và regression cần thiết, rồi mới đề nghị nghiệm thu. Chưa chốt thay ngưỡng, tăng tỷ trọng ML hoặc bất kỳ quyết định nghiệp vụ còn mở nào trong 99. R1 được ghi PARTIAL để tránh hiểu nhầm đã đạt nghiệm thu mới; không tự duyệt DONE hoặc chuyển R2.
