# CR-048 — Nối luật đủ nguồn vào snapshot

14/11/2026 · spec_version=2.1 · **READY_FOR_REVIEW kỹ thuật local**.

Người dùng giao nối luật đủ nguồn và đối chiếu engine cũ trên cùng dữ liệu,
thời điểm. Đã nối thêm **B5/E4** qua immutable snapshot/source resolver và API
phân tích có xác thực. Hai mã này dùng cùng bằng chứng master, không tạo hai
cảnh báo giao dịch. P1/E3 hiện có giữ nguyên; chưa hoàn thành cả 35 evaluator.

## Phạm vi và kết quả

| Nội dung | Quan sát |
|---|---|
| Input | 1.2.0 opt-in, thêm phone/related_party_disclosed_at cho vendors |
| Tương thích | Default schema 1.1.0, byte schema 1.0/1.1 giữ nguyên |
| Canonical evaluator | P1, E3, B5, E4 khi đủ nguồn; 31 mã khác chưa nối |
| So native | 20/20 đạt trên 10 gói C001/C002 × năm tình huống |
| Thiếu nguồn bổ sung | 4/4 B5/E4 trên hai DN trả unavailable/null |
| Hồi quy/focused | 303 tests, 0 fail, 0 error, 0 skip |
| Giữ mọi dòng | Hai DN, mỗi DN 5 đầu vào → 5 kết quả và đủ 35 trạng thái/dòng |
| Căn cứ | Trạng thái, điểm, evidence payload và evidence_id khớp native |
| Master-quality | Bank/phone: nội tại 3; chỉ address: 1; đóng góp giao dịch 0 |
| HE/fit/Portal live | Không mở HE, không fit/active, không restart/deploy |

`checks.json` ghi checksum nguồn, as_of chung, event_at và knowledge_at từng
giao dịch. Native `score_rules` gọi độc lập trên bảng do cùng producer sinh;
canonical được preview/commit vào kho snapshot riêng rồi gọi `score_snapshot`.
Không dùng nhãn/expected để quyết định luật. Năm tình huống gồm trùng bank và
phone, không trùng, phone-only, address-only và đã khai báo quan hệ. Không
diễn giải phép thử này như độ chính xác gian lận hoặc đầy đủ mọi ca nghiệp vụ.

## Thời gian, nguồn và quyền

Revision được chọn sau khi lọc cả observed/effective; nguồn tương lai không
thay kết quả quá khứ. Master biết muộn sau economic event giữ unavailable để
không giả parity native bằng cách dời ngày. Reference sai revision bị chặn ở
validation; thiếu trường/null/missing_fields hoặc contact UNKNOWN không tạo
no-hit. Ngày khai báo không sau observed_at. Scope/nguồn/checksum bị sửa bị từ
chối; C001/C002 dùng cùng ID không lẫn nhau.

Test API POST analyze có xác thực đọc snapshot 1.2.0, trả technical căn cứ B5/E4
và điểm 0; review không lộ rule_coverage. Mọi request còn kiểm quyền như cũ.
Không fit khi inference, không cộng tổng một phần, không đưa master vào queue.
Trùng bank account ở B5/E4 là token legacy, chưa xác minh institution và không
thay B1. Nguồn khai complete/khai báo quan hệ không chứng minh bên ngoài đầy đủ.

## Mã và lệnh

Thêm `vendor_identity_rules.py`, `vendor_identity_demo.py`,
`check_vendor_identity_snapshot.py`, schema input.v1_2 riêng và 10 JSON mẫu.
Sửa source resolver/evaluator, metadata kỹ thuật analysis, registry schema,
validator ngày khai báo và các test liên quan. Không sửa rules.py/noise_policy
hoặc kernel P1, feature builder, worker/adapter HE, model/quyền/config live.

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_vendor_identity_snapshot.py --output-dir .runtime/vendor_identity_snapshot_20261114_final
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_r1_tests.py --report .runtime/vendor-snapshot-regression-final.json --suite test_vendor_identity_snapshot --suite test_rule_evaluation --suite test_rule_sources --suite test_rule_parity --suite test_input_contract --suite test_analysis_api --suite test_snapshots --suite test_validation_backend --suite test_four_branch_analysis --suite test_snapshot_features --suite test_native_rule_node --suite test_p1_evaluation --suite test_p1_inputs
```

Hai lệnh cuối đạt exit 0. Lượt hồi quy trước bắt assertion validator_version
vẫn 1.2.0 sau khi validator tăng 1.3.0; cập nhật kỳ vọng version rồi chạy lại
303 tests đạt. Hai fixture test đầu dùng revision không tồn tại và ceiling
trước khi giao dịch được biết được sửa để kiểm đúng validation/cutoff; không
nới guard sản phẩm. CLI đầu dùng nhầm tên trường commit, đã dùng đúng receipt
contract hiện có rồi chạy lại trên thư mục mới. Không đổi fixture nguồn nghiệp
vụ/ngưỡng để làm đẹp parity.

## Phần còn lại

Chưa mapping toàn bộ 31 luật còn lại, HE B5/E4, CSV/Excel cho thuộc tính mới,
giao diện master finding riêng hoặc deploy Portal live. Điểm tổng/accuracy
chưa khả dụng. Chưa duyệt toàn R2/production; không tự chuyển milestone.

[Hướng dẫn](../../../../agent2/docs/VENDOR_IDENTITY_SNAPSHOT.md) ·
[JSON mẫu](../../../../agent2/examples/vendor_identity_snapshots/README.md).
