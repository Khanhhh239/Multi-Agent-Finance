# Định danh hồ sơ và giữ liên kết rà soát — R6, 16/10/2026

**R6 đã sửa kỹ thuật:** đảo thứ tự nguồn tương đương không đổi ID cụm/hồ sơ, điểm, hit, thành viên hoặc người phụ trách. **341/341 test hồi quy đạt**, gồm 22 test mới; **7/7 probe readiness đạt**. Đã kiểm tra migration từ ID cũ qua cache SQLite, phản hồi CLI/web và lịch sử nhận việc; chưa chuyển các snapshot vận hành/benchmark hiện có trong workspace sang ID mới.

## Khóa cụm tại thời điểm quan sát

[`KnownGraph`](../sme_fraud/rules.py) dựng cạnh hiện hành theo thứ tự chuẩn. Định danh hồ sơ không lấy root UnionFind: khóa `cluster:` băm từ phiên bản `component-members-v1`, công ty và danh sách node `entity:` trong thành phần liên thông, đã sắp xếp và loại trùng. Danh sách này chỉ dùng các cạnh/master đã được quan sát ở thời điểm chấm. Số TK/SĐT thay đổi riêng lẻ nhưng không đổi tập thực thể không tự tạo định danh cụm khác.

Thành viên thực thể bao gồm NCC, nhân viên và node người đại diện theo mô hình đồ thị hiện tại. Thêm/bớt thực thể làm đổi khóa cụm; dữ liệu tương lai không đổi khóa quá khứ. Khóa vẫn theo quy tắc chuẩn hóa định danh hiện hành của engine, không thay hợp đồng mapping ID từ ERP.

`rule_scores.csv` bổ sung `case_cluster_members`; queue bổ sung `identity_version`, `cluster_members`, `scope_hash`. Cửa sổ gom hồ sơ 30 ngày và giao dịch mở hồ sơ vẫn được giữ. ID nguồn F3/F4 và ID lô giữ công thức hiện hành. Các cột feature, trọng số, ngưỡng và chính sách thiếu bằng chứng không đổi.

[`review_queue`](../sme_fraud/case_queue.py) chọn nhân sự mới nhất theo từng ID tại lúc mở hồ sơ, kiểm tra công ty/vai trò sau đó, rồi lấy ID nhỏ nhất trong các kế toán trưởng đủ điều kiện. Không chọn dòng đầu tiên trong file; snapshot tương lai hoặc vai trò cũ không cấp phân công mặc định. Cache UI cũng chọn revision master theo thời gian và từ chối revision cùng ID/thời điểm khác nội dung.

Probe cũ từng đổi `RC_8991c3826efb5d65` thành `RC_29e63b58497be224` khi đảo nguồn. Bản hiện tại cho cùng **`RC_aa845b6799dc6efb`** ở cả hai lần; `case_entity` cùng **`cluster:08ac142567a9c699a457aca5`**. [Quan sát probe](../.runtime/case_identity_20261016/observations.json).

## Nạp lại và ánh xạ hồ sơ

[`case_identity.py`](../sme_fraud/case_identity.py) khai báo phạm vi chuẩn và quan hệ kế thừa. [`ReviewStore.prepare`](../sme_fraud/review_store.py) đọc hồ sơ cũ trước khi dựng lại cache, kiểm tra toàn bộ snapshot mới rồi lưu `case_identity.json` trong thư mục report. File này có phiên bản, checksum queue, hồ sơ hiện hành/lịch sử, alias ID, alias phạm vi và quan hệ kế thừa.

| Tình huống | Phản hồi và phân công | Lượt nhận việc |
| --- | --- | --- |
| Đổi ID, hồ sơ tương đương một-một | Giữ người phụ trách đã lưu; ID cũ mở hồ sơ chuẩn; phản hồi vẫn áp dụng | Chuyển khóa admission sang ID mới, giữ ngày, công ty, phút và loại công việc; không tính hai lượt |
| Cụm/hồ sơ tách, gộp, đổi phạm vi hoặc bằng chứng | Ghi `split`, `merged`, `split_merge` hoặc `changed`; giữ kết luận cũ làm lịch sử, hồ sơ mới cần rà lại và dùng phân công riêng | Giữ công việc đã thực hiện tại hồ sơ cũ; không chuyển thành đã nhận việc ở hồ sơ mới |
| Không còn hồ sơ trong snapshot | Ghi `retired`, giữ tóm tắt và nhật ký cũ ở chế độ chỉ đọc | Giữ lịch sử công việc thực tế |
| Nhiều ứng viên tương đương hoặc khác công ty | Không đoán alias, không chuyển kết luận/phân công | Không tự chuyển lượt nhận việc |

Điều kiện tương đương bao gồm công ty, loại hồ sơ, thời gian mở/lần thấy cuối, giao dịch, tập luật, mức ưu tiên/điểm, sự kiện lô, scope/trạng thái nguồn và bằng chứng đã nạp. Bản có `identity_version` còn yêu cầu cùng tập thành viên cụm. Bằng chứng được băm từ giao dịch thành viên, hit, giao dịch ngữ cảnh liên quan, sự kiện lô, chứng từ/dòng bút toán và finding nguồn; thứ tự dòng tương đương không làm đổi băm.

Với hồ sơ legacy chưa lưu thành viên cụm, chỉ nối khi phạm vi giao dịch và bằng chứng đã lưu tương đương một-một. Không khẳng định đã khôi phục được mọi thành viên đồ thị ẩn trong snapshot legacy. Nếu không có cache/metadata cũ để chứng minh phạm vi, không tự gắn kết luận vào một hồ sơ mới chỉ dựa vào root, tên NCC hoặc phần ID giống nhau.

## Nhật ký và giao diện

[`feedback.py`](../sme_fraud/feedback.py) giữ nguyên từng dòng và chuỗi hash trong `feedback_audit.jsonl`. Lần lưu mới gắn `case_scope_hash`; alias chỉ được áp dụng tại phép chiếu trạng thái. Kết luận của phạm vi cũ không đóng hồ sơ có bằng chứng/phạm vi mới, kể cả ID chưa đổi. `case_review_states.csv` được dựng lại khi migration và khi có phản hồi mới.

Phản hồi legacy không có hash phạm vi chỉ được nối khi có snapshot cũ đã lưu và thời điểm review phù hợp. Khóa đồng thời CLI/web và kiểm tra `expected_hash` tiếp tục hoạt động sau đổi ID. UI hiển thị quan hệ kế thừa, kết luận cũ để đối chiếu, cờ tái rà soát và liên kết giữa các hồ sơ. Hồ sơ lịch sử chỉ đọc không có form lưu kết luận hoặc tiêu tốn lượt nhận việc.

Hồ sơ lịch sử giữ tóm tắt, phân công và kết luận; cache hiện tại không hứa lưu trọn bộ bằng chứng cũ sau khi hồ sơ biến mất. UI ghi rõ giới hạn này. Muốn đối chiếu lại bằng chứng cũ cần giữ snapshot report/dataset tương ứng.

## Áp dụng trên bộ hồ sơ đang có

Giữ lại SQLite đang lưu admissions/phân công, nhật ký phản hồi, `case_identity.json` nếu đã có và snapshot report/dataset trước khi đưa queue mới vào cùng không gian rà soát. Không xóa database trước lần migration đầu; metadata cũ là bằng chứng để so sánh. Nếu đổi thư mục report, phải mang theo nhật ký và metadata rà soát đúng bộ nguồn; không ghép các bộ doanh nghiệp/seed độc lập bằng ID trùng nhau.

Sau khi queue/bằng chứng mới sẵn sàng, chạy chế độ chuẩn bị của UI với đúng đường dẫn đang dùng:

```powershell
python -B -m sme_fraud.review_server --data-root <data-root> --reports-root <reports-root> --database <database-dang-dung> --prepare-only
```

Cache schema 4 sẽ so sánh snapshot cũ–mới và lưu ánh xạ. Queue thay đổi nhưng chưa chuẩn bị lại sẽ bị chặn lưu phản hồi qua mapping cũ. Nếu file mapping từng được tạo bị mất, ReviewStore báo lỗi yêu cầu phục hồi thay vì âm thầm bỏ alias. Xung đột admissions bị từ chối; các lỗi nguồn phát hiện trước khi ghi mapping không thay cache/metadata cũ. File mapping/trạng thái dùng ghi thay thế nguyên tử; cơ chế này không phải giao dịch phân tán chống mọi tình huống mất điện giữa SQLite và filesystem.

Đợt R6 này kiểm thử migration trên thư mục/database tạm; không ghi lại nhật ký thật, không chạy migration trên các database trong `.runtime/review`, không sửa snapshot benchmark cũ. Hợp đồng scalar R7 tiếp tục áp dụng: nguồn cũ có ngày callback sai cần được xử lý trước khi tạo queue dẫn xuất mới.

## Kiểm chứng và việc tiếp theo

- **341/341 test đạt**, 74,452 giây, gồm 319 test trước và [22 test R6](../tests/test_case_identity.py). [Log](../.runtime/case_identity_20261016/tests.log), [kết quả/hash](../.runtime/case_identity_20261016/result.json), [hai ca đỏ trước sửa](../.runtime/case_identity_20261016/before_fix.log).
- **7/7 probe readiness đạt**, không failure/error; [log](../.runtime/case_identity_20261016/readiness_probes.log). Artifact các đợt trước được giữ nguyên.
- Có đối chứng nguồn → detector → queue → cache → lưu phản hồi → đảo nguồn/nạp lại; migration legacy, nguồn trùng/tương lai, nhận việc/phút không nhân đôi, khởi động lại, split/merge, khác công ty, ánh xạ mơ hồ, đổi giao dịch ngữ cảnh/bút toán, mapping mất và refresh thất bại.
- JavaScript qua kiểm tra cú pháp và chạy luồng mở ID cũ/hồ sơ lịch sử bằng Node VM với API/DOM giả lập; [chi tiết](../.runtime/case_identity_20261016/ui_verification.json). Chưa kiểm tra hiển thị bằng trình duyệt thật.

R1–R8 đã sửa kỹ thuật theo phạm vi từng bản; chưa phải nghiệm thu vận hành. Tiếp theo là tạo nguồn/dataset dẫn xuất hợp lệ, đồng bộ feature/model, chấm train/validation với các bản sửa kết hợp và nghiệm thu trên nguồn SME thật. Chưa chạy lại benchmark lớn, huấn luyện ML hoặc kết luận precision/recall mới trong đợt R6.
