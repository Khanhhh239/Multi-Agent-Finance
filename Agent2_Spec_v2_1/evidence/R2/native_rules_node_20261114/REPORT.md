# CR-047 — Kiểm chứng 35 luật local

Ngày 14/11/2026 · spec_version=2.1 · **READY_FOR_REVIEW kỹ thuật**.

Theo lựa chọn rõ của người dùng: “Cho đủ 35 luật chạy và đối chiếu tại node
doanh nghiệp trước, sinh data test; sau đó mở rộng HE (đề xuất)”. Không nâng
toàn R2 thành DONE, không xác nhận hiệu quả gian lận hoặc nghiệm thu nghiệp vụ.
Working tree đang có thay đổi từ nhiều CR trước; chưa tạo commit/push/deploy.

## Kết quả

| Kiểm tra | Quan sát |
|---|---|
| Danh mục | Đủ 35 luật trong RULE_NAMES |
| Nguồn thử | 120 gói JSON mô phỏng, C001/C002 tách scope |
| Trúng và đối chứng | 140/140 đạt: hai ca × 35 luật × hai DN |
| Thiếu nguồn | 70/70 trả unavailable/null, không đổi thành no-hit/0 |
| Parity | 120 gói đối chiếu engine độc lập; 140 kiểm tra theo luật khớp |
| Nguồn bất biến | Checksum trước/sau khớp; expected nằm ngoài nguồn |
| Focused/regression | 53 tests, 0 fail, 0 error, 0 skip |
| ML/HE/Portal | Không fit, không chấm HE mới, không đổi Portal |
| Độ chính xác phát hiện gian lận | Chưa đánh giá; accuracy=null |

Kết quả này trên bộ ca có kiểm soát, không khẳng định mọi biến thể của mỗi
luật hoặc nguồn thực tế đã đủ. D là kiểm tra tập/cutoff, có nhóm nhỏ vẫn chưa
khả dụng. E4 dùng alias B5 giữ lại; master-quality và F4 không phải điểm dòng.
Không cộng tổng điểm native vào queue. Tất cả nguồn/phê duyệt/chứng từ demo
đều mô phỏng, không phải chứng từ gốc đã được xác minh.

## Thay đổi và nguồn bằng chứng

- `agent2/sme_fraud/native_rule_node.py`: profile native riêng, validator,
  scope, manifest/hash, as_of, source gaps và kết quả theo phạm vi luật.
- `agent2/sme_fraud/native_rule_demo.py`: sinh nguồn nghiệp vụ, ca cảnh báo
  và ca đối chứng; không gọi cấu hình override của Case.score.
- `agent2/scripts/prepare_native_rule_demo.py`: 120 nguồn + manifest expected
  riêng + ZIP; không chứa model, khóa hoặc trạng thái live.
- `agent2/scripts/run_native_rule_demo.py`: kiểm checksum nguồn, gọi engine
  độc lập, so diagnostics D, probe thiếu coverage và xuất JSON/Markdown/HTML.
- `agent2/tests/test_native_rule_node.py`: 15 tests mới, cùng 38 tests parity,
  evaluator và source hiện có trong bộ 53.
- `agent2/docs/NATIVE_RULE_NODE.md`: cách chạy, dữ liệu, miền hỗ trợ/giới hạn.

Các source fingerprint của CR-046 được đối chiếu lại, không đổi. Engine,
chính sách/tham số, canonical P1/E3 và adapter HE không bị sửa để làm ca thử đạt.
`manifest.json` ở evidence này khóa hash code, artefact và gói nguồn ZIP.
`rule_checks.json` có từng ca; `focused_tests.json` có từng test.

## Lệnh và kết quả thực thi

Từ gốc `D:\agent22`:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_native_rule_demo.py --output-dir agent2/.runtime/native_rules_demo_20261114
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_native_rule_demo.py --input-dir agent2/.runtime/native_rules_demo_20261114 --output-dir .runtime/native_rules_results_final_20261114
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_r1_tests.py --report .runtime/native-rules-focused-final-v2.json --suite test_native_rule_node --suite test_rule_parity --suite test_rule_evaluation --suite test_rule_sources
```

Ba lệnh cuối cùng đạt exit 0. Trước bản cuối, một test bổ sung dùng chuỗi rỗng
cho trường giá trị hóa đơn mà profile native bắt buộc integer nên bị từ chối
schema; sửa fixture để kiểm tra giá trị 0 do nguồn khai (không phải impute của
adapter), rồi toàn bộ 53 tests đạt. Không nới schema hay policy để qua test.

## Miền và phần chưa làm

Đây là native-rule-source/1.0.0 riêng tại DN; chưa là migration hợp đồng
snapshot 1.1.0 hoặc đầy đủ adapter point-in-time từ Portal. Profile từ chối
tiền âm và giao dịch/sổ cái ghi nhận muộn để không giả hỗ trợ mà engine cũ
chưa xử lý; không abs/zero/retime. Canonical P1 có dấu giữ nguyên. Cần adapter
có dấu/bitemporal tiếp theo trước khi nhận các nguồn này cho toàn catalog.

Coverage complete là khai báo xuất nguồn, không chứng minh đầy đủ bên ngoài.
Validator không phải dịch vụ xác minh chứng từ. Hàm local cần AccessScope
caller tin cậy; CLI demo chỉ nhận synthetic tenant. Chưa endpoint import nguồn
này, mapping CSV/Excel, bật đủ 35 luật trên UI/HE, connector thật, cloud public,
gate chất lượng hoặc xác minh reviewer. Không truy cập DB/khóa live, restart
dịch vụ, đổi quyền, fit/model, trọng số/ngân sách, mandatory routing hay queue.

Xem [báo cáo dễ đọc](../../../../reports/native_rules_acceptance_20261114.html)
và [hướng dẫn](../../../../agent2/docs/NATIVE_RULE_NODE.md).
