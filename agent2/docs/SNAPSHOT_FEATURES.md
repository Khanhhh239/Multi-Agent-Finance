# Feature từ snapshot: đúng thời điểm, tách dữ liệu dự báo và truy vết

Đã nối snapshot bất biến với `features.build_features` đang giữ lại. Lõi cũ và contract legacy không bị sửa. Adapter có contract **snapshot-point-in-time/1.1.0**, xuất **33 biến số** có nguồn phù hợp với hợp đồng mới. Không tự coi model/cache dùng bộ feature cũ là tương thích; bước này chưa fit hoặc chấm ML.

## Chạy demo

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -X utf8 -B scripts/demo_snapshot_features.py
```

Demo tạo snapshot từ fixture mô phỏng, chạy job có xác thực quyền C001, in số dòng/biến, cho thấy T001 và T002 cùng nhìn lịch sử trước nhóm. Chạy lại ở mốc muộn hơn để kiểm tra feature hai giao dịch cũ giữ nguyên. Kho thử nằm riêng tại `.runtime/feature_demo`, credential tạm được dọn, không in ra màn hình.

## Ý nghĩa của as_of

- `as_of` của job là mốc kiến thức tối đa: giao dịch có ngày nghiệp vụ hoặc ngày nguồn được biết sau mốc đó chưa được đưa ra.
- Mỗi revision giao dịch được tạo feature tại `available_at = max(effective_at, observed_at)`. Mốc này được ghi trong rows.json. Rerun sau này không lấy thêm chứng từ đến muộn để viết lại vector cũ. Revision giao dịch mới có vector/provenance mới.
- Context NCC/nhân viên/hóa đơn/chứng từ/phê duyệt phải có `observed_at <= available_at` và `effective_at <= effective_at của giao dịch`. Chọn revision sau khi lọc hai mốc, không lấy master mới nhất toàn bộ rồi dùng cho quá khứ.
- Lịch sử giao dịch chỉ gồm dòng có `effective_at` **nhỏ hơn** thời điểm nghiệp vụ của nhóm và `available_at` **nhỏ hơn** mốc được biết của nhóm. Không tính chính ID giao dịch hoặc cộng nhiều revision của một ID.
- Hai dòng cùng thời điểm nghiệp vụ **hoặc cùng lúc được biết** không vào lịch sử của nhau. Các dòng trong nhóm dùng cùng lịch sử trước nhóm rồi mới được tính cho nhóm sau. Đảo thứ tự tệp không đổi kết quả.
- So sánh thời gian bằng datetime có offset, giữ microsecond. VN UTC+07 chỉ dùng khi tạo biến lịch kinh tế. Không dùng giờ upload làm giờ lập chứng từ.

Ví dụ fixture: H0 có trước; T001 và T002 cùng lúc 09:00 ngày 10/10. Cả T001 và T002 thấy một khoản H0, không thấy nhau. Chứng từ DOC_LATE được biết ngày 12/10 không thay feature của hai khoản ngày 10/10. Nếu một chứng từ hóa đơn mới đủ điều kiện cho giao dịch ngày sau thì giao dịch ngày sau được dùng, không bỏ qua toàn bộ chứng từ muộn.

Đây là replay theo thời điểm nguồn khai báo. Độ tin cậy của timestamp/chứng từ thật vẫn cần quy trình dữ liệu và rà nghiệp vụ, không tự được xác minh bởi checksum.

## Đọc chứng từ đã xác minh

Từ patch 1.0.1, job đọc snapshot đã commit và kiểm checksum được sử dụng trạng thái xác minh đã lưu bằng quyền đọc snapshot hiện có (`data.import` trong adapter local). Người đọc không cần thêm `evidence.verify`; tạo feature không tạo hay sửa trạng thái xác minh.

Nhập/preview/commit nguồn mới có trạng thái verified vẫn cần `evidence.verify`. `build_feature_rows` nhận bundle raw/offline cũng giữ kiểm tra này. Chỉ nhánh nội bộ sau `build_from_snapshot` bỏ áp lại lỗi quyền ghi xác minh; thiếu người/căn cứ/thời điểm xác minh, sai schema, liên kết, tenant hoặc checksum vẫn bị chặn. Không có cờ bỏ kiểm tra dành cho client và không tự bổ sung quyền cho scope. Quyền vẫn kiểm lại trước khi xuất artifact.

Patch giữ nguyên 33 cột và các phép tính; version/fingerprint mới phân biệt hành vi đọc. Tạo artifact theo contract hiện hành, không sửa artifact cũ hoặc tự coi model khác fingerprint tương thích.

## Lịch sử phân bổ chưa đủ nguồn

Từ 1.1.0, ba cột `prior_invoice_payment_count`, `prior_invoice_allocation_log_abs`, `prior_invoice_allocation_negative` trả null khi có phân bổ lịch sử liên quan đã biết nhưng chưa dùng được revision hóa đơn/giao dịch mà nó tham chiếu. `missing.json` đánh dấu true, `missing_reasons` ghi `prior_invoice_history_incomplete`. Không lấy revision tương lai hay tự chuyển sang revision cũ để điền số.

`evidence.json` có `prior_invoice_history` gồm status, coverage_basis và unavailable_references. Mỗi nguồn thiếu có phân bổ làm căn cứ, trường tham chiếu, ID/revision cần đối chiếu, thông báo **“Chưa đủ dữ liệu”** và hành động. Phân bổ đã biết vẫn nằm trong records; giá trị/timestamp của revision tương lai không được xuất. Tổng `prior_signed_allocation_vnd` cũng null nếu lịch sử không khả dụng, tránh trình bày một tổng một phần như tổng đã đủ nguồn.

Nếu các liên kết nhìn thấy đủ nguồn và không có phân bổ trước, hoặc phân bổ dương/âm cộng về 0, giá trị 0 vẫn được giữ đúng. Thiếu liên kết hóa đơn hiện tại thì prior unavailable/null. available chỉ nói các liên kết trong snapshot/cutoff đang dùng đủ nguồn để tính, không chứng minh doanh nghiệp đã cung cấp toàn bộ lịch sử ngoài hệ thống. Evidence thêm trường, numeric schema vẫn 33 cột; contract/fingerprint 1.1.0 phân biệt semantics missing mới.

## Ba kênh tách biệt

| Tệp | Nội dung |
|---|---|
| features.json | Ma trận số/null, đúng thứ tự columns; không ID, nhãn, hash hay văn bản chứng từ |
| missing.json | Ma trận boolean cùng kích thước, đánh dấu giá trị null; chưa impute |
| rows.json | row_index, tenant/DN, ID, revision, event_at và as_of của mỗi dòng |
| evidence.json | Các source record/revision/thời điểm thực, số tiền signed đối chiếu, lịch sử đã dùng và lý do missing |
| contract.json | Schema/thứ tự/ý nghĩa/cutoff/dtype, fingerprint adapter và core legacy |
| manifest.json | Snapshot ID/checksums, as_of, contract fingerprint và checksum của từng kênh |

Nhãn và kết luận rà soát không được đọc vào bộ tạo feature. Các cột nhãn/seed/template lạ trong snapshot bị validator từ chối. Tên nguồn, tên doanh nghiệp, ID, số hóa đơn và hash chứng từ không được biến thành predictor hoặc embedding ID. Các thống kê đếm chứng từ/quan hệ được tạo từ nguồn hợp lệ; bản ghi và hash làm căn cứ vẫn ở kênh riêng. Đổi ID đồng bộ với tham chiếu không thay các giá trị dự báo.

## Những phần được tái sử dụng và giới hạn

Adapter gọi nguyên bộ tạo feature cũ cho các primitive magnitude/lịch sử, chu kỳ giờ/thứ, graph ngân hàng và bút toán có nguồn. Thống kê liên kết hóa đơn/phân bổ nhiều–nhiều, số chứng từ và phê duyệt lấy từ quan hệ canonical đã lọc thời điểm; không coi chúng là đối chiếu nghĩa vụ hoàn chỉnh của R4.

- Số tiền nguồn vẫn là integer VND có dấu. `log_abs_amount` là log của độ lớn, có `amount_negative` và `amount_zero` riêng. Số tiền tổng phân bổ signed chính xác được giữ trong evidence; không lấy trị tuyệt đối rồi ghi đè sổ.
- Core cũ đòi số dương và timestamp giây UTC+07. Projection nội bộ dùng magnitude tối thiểu 1 và đồng hồ thứ tự để gọi core; hai thứ này **không được xuất như dữ kiện nguồn**. Thống kê magnitude bị ảnh hưởng bởi số 0 trả null/lý do rõ; log của amount=0 xuất 0 đúng nghĩa. Full-precision clocks thực điều khiển selection và grouping trước projection.
- Các biến lịch được đặt tên `event_*`, dựa trên thời điểm nghiệp vụ thực, không giả là giờ tạo/phê duyệt. Các feature cửa sổ thời gian dựa trên đồng hồ projection không được xuất.
- Contract mới không xuất những feature legacy cần chế độ kế toán, lịch nghỉ, tuổi NCC, hợp đồng lao động, VAT, chính sách tự duyệt hoặc tài liệu chưa có trong schema. Placeholder kỹ thuật cho các trường bắt buộc của core không trở thành predictor.
- Z-score giữ định nghĩa core: ít nhất 5 mẫu trước cùng loại, SD floor .25. Thiếu mẫu/zero bị đánh dấu null, không giả bằng 0. Đây không phải quyết định min-history hay readiness cho detector R2.
- `observed_approval_limit_ratio` chỉ có khi có hạn mức approved dương, không mâu thuẫn, gắn đúng giao dịch. Không tự coi đó là hạn mức người lập hoặc quyền được phép chi.
- Graph ở profile này chỉ dùng định danh ngân hàng có cả mã ngân hàng và tài khoản được biết; số 0 đầu được giữ. Không tạo quan hệ mạnh từ địa chỉ đơn lẻ hay ghép sang doanh nghiệp khác.

`null` không là “bình thường”. Model/preprocessor R2 phải kiểm contract và xử lý missing có phiên bản; R1 không tự impute/fit hoặc thay trọng số.

## Job cho snapshot đã lưu

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -X utf8 -B -m sme_fraud.feature_pipeline `
  --snapshot-db .runtime/imports/snapshots.sqlite3 `
  --auth-file .runtime/validation-auth.json --token-file .runtime/client-token.txt `
  --company C001 --snapshot-id snp_MA_LAY_TU_SERVER `
  --as-of 2026-10-10T11:00:00+07:00 --output-dir .runtime/features
```

Thay snapshot ID và các đường dẫn bằng cấu hình thật của môi trường thử; không có credential mặc định. Job xác thực trước mở DB, kiểm checksum snapshot và kiểm lại quyền trước xuất. Không chạy fit trong HTTP. Đây là worker/CLI, chưa có nút tạo feature trên Portal.

Artifact ID được tính từ snapshot, as_of, contract và các kênh. Retry trả artifact đã có sau kiểm checksum, không ghi đè; thư mục đang ghi được công bố bằng rename khi đủ các tệp. `read_artifact` kiểm checksum, row alignment, kiểu số/missing mask và phạm vi DN. Nếu tệp hỏng thì báo lỗi, không âm thầm sửa cache. Job tham chiếu hiện replay riêng từng nhóm để đúng hai thời gian; chưa phải tuyên bố đạt SLA/performance cho dữ liệu lớn.

## Kiểm thử R1

Các test catalog R1-01…07 ở `tests/test_r1_acceptance.py` dùng snapshot thật và HTTP thực trong môi trường tạm. Runner `scripts/run_r1_tests.py` xuất kết quả từng test; lệnh formal:

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B Agent2_Spec_v2_1/scripts/run_stage.py R1
```

Runner ghi evidence và run_id; acceptance phải được điền theo kết quả mới rồi chạy checker, không lấy PASS của lần cũ. Đây là nghiệm thu kỹ thuật trên fixture, không chứng minh accuracy ML hoặc duyệt dữ liệu thật. Không tự chuyển R2/production sau khi test pass.
