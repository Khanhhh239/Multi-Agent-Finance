# CR-050 — nối đủ 35 luật vào snapshot nghiệp vụ

14/11/2026 · **READY_FOR_REVIEW kỹ thuật local**.

Theo yêu cầu nối toàn bộ luật và đính chính tỷ trọng của người dùng, luật cứng
là một thành phần; không cấu hình 70–80% hoặc thay chính sách phối hợp ML.

## Kết quả thực hiện

- Profile `agent2-rule-snapshot/1.0.0` nhận nguồn native chuẩn hóa, coverage,
  checksum từng bảng và danh sách ứng viên. Đi qua upload/preview/commit của
  SnapshotStore và cùng endpoint `/snapshots/{id}/analyze` có xác thực.
- Gọi engine giữ lại cho đủ A1–A6, B1–B7, C1–C4, D1–D6, E1–E4, F1–F4,
  P1–P2, T1–T2; không sửa kernel/ngưỡng, không chỉ bổ sung tên vào registry.
- Giữ đủ ứng viên. Hit lịch sử không được sao chép sang mọi giao dịch. D1–D6
  và F4 là kết quả tập/nguồn; master/context không tự trở thành cảnh báo giao
  dịch. B5/E4 không cộng hai lần. Không đưa ra điểm tổng hoặc xác suất gian lận.
- Thiếu bảng/coverage, ma trận quyền không biết tại thời điểm duyệt, bảng công
  chưa có hoặc định danh hóa đơn thiếu trả unavailable, matched/score null.
  Loại giao dịch ngoài phạm vi trả not_applicable, không phải không vi phạm.
- Cùng quyền đọc snapshot không bị yêu cầu xác minh lại chứng từ; nhập attestation
  vào nguồn thật vẫn cần quyền xác minh. View kỹ thuật và catalogue có quyền
  quản lý, kiểm tenant/doanh nghiệp trước khi đọc.
- Màn hình nhận profile mới, lấy as_of đã khóa, có nút rõ **Xem 35 luật tại node
  doanh nghiệp**, căn cứ/bước tiếp theo và phần mở rộng cho chẩn đoán nhóm.

## Bằng chứng

| Kiểm chứng | Kết quả |
|---|---|
| Upload → preview → commit → analyze, C001/C002 | 120/120 gói nguồn, 35 mã |
| Trúng và đối chứng với native engine | 140/140 kiểm tra |
| Đối chiếu | Hash output nguyên bản score_rules; nhóm D so monthly_diagnostics cùng cutoff |
| Giao diện Chrome headless, server tạm có xác thực | 6/6 bước, không lỗi JavaScript |
| Bộ mẫu chia sẻ | 120 JSON trong ZIP và 6 JSON chọn sẵn, tenant demo; validate schema/scalar lại trên mã cuối |

`tests.json` ghi bộ hồi quy cuối và số test thực tế; `matrix.json` ghi từng ca.
Các số trên là độ đạt kiểm thử kỹ thuật của nguồn mô phỏng, không phải accuracy.
`ui.json` và `ui.png` là server kiểm thử riêng, không giả nghiệm thu Portal live.
`code-manifest.json` khóa mã/schema dùng để tái kiểm tra.

Trong quá trình thử đã sửa phản hồi nhánh unavailable thiếu danh sách rỗng làm
UI không render, bổ sung guard nguồn rỗng và tách summary nguồn/từng giao dịch.
Một lượt cũ gặp Windows socket abort khi thử header xác thực rỗng; chạy lại
tuần tự, không bỏ kiểm tra xác thực. Test coverage dùng đúng `covered_through`.

## Ranh giới đã giữ

Profile canonical 1.0/1.1/1.2 vẫn có bốn adapter P1/E3/B5/E4 theo nguồn đủ;
không tuyên bố file canonical ít cột đã hỗ trợ 35 luật. Profile mới là đường
nguồn đầy đủ **tại DN**, không fallback dữ liệu rõ khi HE lỗi. Cloud không
nhận nguồn này. Chưa có HE toàn catalog hoặc bridge 33 feature cho profile mới;
ba nhánh độc lập thống kê/đồ thị/ML báo chưa khả dụng. Model/khóa/worker/TTL và
luồng chấm mã hóa hiện có giữ nguyên, không fit/chấm cloud trong lượt này.

Native kernel còn giới hạn số âm và giao dịch/sổ cái quan sát muộn. Profile
từ chối trường hợp ngoài miền, không abs/zero/đổi thời gian. Canonical P1 có
dấu không đổi. Coverage/checksum là khai báo bên xuất, không tự chứng minh
nguồn ngoài hệ thống đã đầy đủ. Cần nghiệm thu nghiệp vụ trên chứng từ thật.

Không deploy/restart live, không dùng mật khẩu hay phiên Portal, không đẩy Git,
không ghi queue/nhãn hoặc tự xác nhận hiệu quả phát hiện gian lận/R2 DONE.

## Tái chạy

Tại root repository:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_full_rule_pipeline.py --output .runtime/full-rules-replay-new
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_rule_snapshot_ui.py --output .runtime/full-rules-ui-new
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/prepare_full_rule_inputs.py
```

Lệnh replay cần bộ nguồn mô phỏng CR-047 ở `agent2/.runtime/native_rules_demo_20261114`;
output replay phải là thư mục mới. Mẫu nhập và hướng dẫn:
[FULL_RULE_PIPELINE.md](../../../../agent2/docs/FULL_RULE_PIPELINE.md),
[examples/full_rules](../../../../agent2/examples/full_rules/README.md).
