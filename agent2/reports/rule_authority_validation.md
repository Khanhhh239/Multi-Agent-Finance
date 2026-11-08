# Kiểm định dữ liệu quyền C2/C3 — R5, 16/10/2026

**R5 đã sửa kỹ thuật:** `self_approval_allowed=2` không còn được hiểu là có quyền. Nguồn sai bị từ chối bằng `ValueError` chỉ rõ bảng, ID và trường trước khi C2/C3 ra quyết định; không bỏ qua dòng sai hoặc chuyển sang fallback.

## Hành vi hiện tại

[ApprovalAuthority](../sme_fraud/authority_policy.py) kiểm tra tất cả revision của `approval_authorities` và `approval_authority_coverage`, kể cả nguồn tương lai/đã thu hồi, trước khi đưa vào chỉ mục lịch sử.

| Nhóm | Giá trị hợp lệ | Giá trị bị từ chối |
| --- | --- | --- |
| `self_approval_allowed`, `evidence_on_file` | Số nguyên 0/1, boolean native, chuỗi CSV `"0"`/`"1"` | 2, -1, số thực kể cả 1.0, chuỗi `true`/`false`, rỗng/null và kiểu khác |
| Hạn mức VND | Số nguyên không âm hoặc chuỗi chữ số; min ≤ max, gồm hai đầu | Số âm, số thực, boolean, NaN/Infinity, ký hiệu khoa học, dấu phân cách hoặc khoảng đảo ngược |
| Enum | Hành động/cấp quyền/loại quyền/trạng thái đúng danh sách schema | Giá trị lạ, sai chữ hoa/thường hoặc rỗng |
| `covered_actions` | Danh sách không rỗng, không trùng, chỉ `self_approve`/`approve` | `all`, token lạ/rỗng, danh sách trùng hoặc sai kiểu |
| Ngày hiệu lực/coverage | Ngày thực `YYYY-MM-DD`, đầu ≤ cuối, gồm hai đầu | Ngày không tồn tại, sai định dạng hoặc khoảng đảo ngược |
| Thời điểm | `YYYY-MM-DDTHH:MM:SS+07:00`, `approved_at <= observed_at` | Giờ/ngày không tồn tại, thiếu/sai múi giờ, thiếu giây, phần lẻ giây hoặc quan sát trước ngày duyệt |
| Cột văn bản | Chuỗi; ID nguồn/công ty không rỗng | Null/số/list thay chuỗi, khoảng trắng đầu/cuối ngoài danh sách action |

Cờ, số và thứ tự action trong coverage được chuẩn hóa trên bản sao trước khi so revision/binding. Hai revision cùng nghĩa qua CSV và Python không bị coi là xung đột chỉ do `1` khác `"1"`. Không sửa bảng đầu vào của bên gọi; kiểm tra xung đột và binding bất biến vẫn hoạt động.

Phép chuyển số có giá trị mặc định đã được gỡ khỏi đường dùng quyền. Chỉ cờ đã xác minh bằng 1 mới cho phép tự duyệt; min/max dùng số nguyên đã kiểm định.

Schema công bố miền/định dạng tại [authority_policy.schema.json](../sme_fraud/authority_policy.schema.json), hướng dẫn nhập tại [examples/authority_sources](../examples/authority_sources/README.md). Nguồn múi giờ/độ chính xác khác phải được chuyển về hợp đồng thời gian của engine trước khi nhập, vì chỉ mục as-of hiện so chuỗi thời gian chuẩn.

## Đối chứng và kết quả

**247/247 test đạt**, 66,015 giây, gồm 227 test trước và [20 test kiểm định nguồn quyền mới](../tests/test_authority_validation.py). Không failure/error. [Log đầy đủ](../.runtime/authority_validation_20261016/tests.log), [kết quả và hash](../.runtime/authority_validation_20261016/result.json).

```powershell
python -B -m unittest discover -s tests
```

Các ca mới kiểm tra lỗi tái hiện qua engine C2, boolean/enum/số/ngày giờ trên cả hai bảng, biên hạn mức CSV, nguồn tương lai/thu hồi, bằng chứng thiếu, revision tương đương, xung đột/binding và tính bất biến của đầu vào. Nhóm quyền/lịch sử gồm 43 test đã đạt trước khi chạy toàn bộ; đối chứng lịch sử nhân sự C2/C3 tiếp tục đạt.

Nguồn hợp lệ nhưng chưa có chứng từ/người ký (`evidence_on_file=0`, `evidence_id=''` hoặc `approver_id=''`) vẫn không cấp ngoại lệ. Nguồn tương lai hợp lệ vẫn được lưu, chỉ có hiệu lực khi kiểm tra as-of cho phép. Không áp mốc giờ máy hiện tại để loại nguồn, không đổi điểm/ngưỡng hay chính sách fallback khi thực sự không có coverage hợp lệ.

## Phạm vi còn lại

Bản sửa kiểm định nội dung hai bảng quyền C2/C3; không xác minh chữ ký, tính đầy đủ thực tế của coverage hoặc mở rộng validator sang mọi nguồn nghiệp vụ khác. Cần đối soát coverage với IAM/ERP khi nhập nguồn thật, theo hợp đồng đã có.

Chưa chấm lại benchmark lớn hoặc nghiệm thu nguồn SME thật. R2 đã có [bản sửa định danh ngân hàng](rule_bank_identity.md), R8 đã có [lịch sử người ký dùng chung](rule_signer_history.md), R7 đã có [kiểm định các nguồn ngoại lệ còn lại](rule_exception_validation.md), R6 đã có [định danh và migration hồ sơ](rule_case_identity.md). Các bước tích hợp/nghiệm thu ở [báo cáo readiness](rule_readiness_recheck_20261016.md) vẫn còn thiếu. Các probe và kết quả audit ban đầu được giữ nguyên làm snapshot lịch sử.
