# Kiểm tra lại Agent2 sau phần việc Antigravity — 14/11/2026

**Cập nhật sau rà:** lỗi batch/cutoff bên dưới đã được sửa trong code và kiểm
chứng trên server riêng: [bản sửa và hồi quy](rule_cutoff_fix_20261114.md).
Báo cáo này giữ nguyên ghi nhận lỗi ở thời điểm rà; không coi là đã deploy live.

**Cập nhật model:** đã thêm và ghim artifact đúng contract bridge mới cho
C001/C002, có bộ 5 ứng viên/DN và bảo toàn model/khóa cũ:
[báo cáo kích hoạt demo](rule_bridge_models_20261114.md).

**Kết luận: các phần bàn giao đã được triển khai thêm, không cần giao làm lại
từ đầu. Hệ thống đã bật lại; còn lỗi batch/cutoff và bước chuẩn bị model mới.**

## Đã kiểm tra trên code hiện tại

| Phần | Kết quả chạy lại |
|---|---|
| Bridge 33 feature, 35 luật và analysis API | 55 test đạt, không fail/error/skip |
| Adapter P1/C3/định danh và worker contract/reference/security | 33 test đạt |
| Coordinator/vault/snapshot adapter/config/blob lifecycle HE | 21 test đạt |
| Chrome UI nguồn đầy đủ sau sửa reload | 8 bước đạt, không lỗi JavaScript |
| Runtime sau bật lại | Portal 8800, Agent2 8766, CKKS 8868, HE4 8869: HTTP 200; Agent2 running/dependency ready |
| Bảo toàn sau đổi bundle/bật lại | 4 model artifact và 2 file khóa DPAPI không đổi checksum |

109 test là bộ tập trung của lượt này, không phải chạy lại toàn dự án. Test
worker contract/reference có mock/plain reference; không coi số test đó là
109 phép FHE native thật. Kiểm thử UI dùng server riêng; lượt này chưa đăng
nhập và nghiệm thu lại trọn luồng trên Portal live. Asset workbench qua proxy
Portal được kiểm hash trùng code đã sửa.

## Hai lỗi đã sửa

**Reload làm sai as_of.** Báo cáo QA trước có tổng `status=passed` nhưng ca
`reload_direct_data_import.passed=false`: lần reload tiếp theo dùng giờ hiện
tại, phân tích lỗi RULE_CUTOFF_MISMATCH. Đã tái hiện bằng Chrome trước sửa.

Nguyên nhân: setSaved() ghi sessionStorage trước khi khôi phục asOf. Sửa
`agent2/sme_fraud/web/workbench.js` để khôi phục thời gian trước khi nhớ trạng
thái; profile nguồn đầy đủ đọc required_as_of từ report đã khóa theo snapshot,
đối chiếu origin_report_hash. Chuyển ISO sang giờ VN trước hiển thị, không cắt
chuỗi timezone tùy ý. Test cả storage cũ đã sai giờ và hai lần reload liên tiếp:
giữ cùng snapshot/as_of/analysis ID, phân tích thành công.

**Không bật được Agent2 do worker bundle cũ.** Cả bốn cổng ban đầu đều tắt.
Khởi động cho thấy HE4 bundle integrity bị chặn: public_worker.py và service.py
ở source đã mới hơn gói worker triển khai. Đây là guard đúng, không bị tắt đi.

Đã build gói public riêng tại `.runtime/recheck-20261114-runtime/he4-public-bundle`,
kiểm manifest/source, backup config rồi đổi duy nhất
`agents.agent2.he4_worker.bundle`. Giữ nguyên gói cũ, không đổi key/model/build
circuit/bindings model. Restart đúng Portal vừa được lượt này tạo và bật Agent2
qua lifecycle sẵn có; không kill tiến trình kiểm chứng HE khác đang chạy.
Thư mục bundle mới đang được config tham chiếu, cần giữ lại khi dọn runtime.
Backup config và kiểm preservation nằm trong `.runtime/recheck-20261114-runtime/`;
không đưa các file private đó lên Git.

## Việc cần làm tiếp, theo bằng chứng

### P1 — một ứng viên ngoài cutoff làm hỏng cả batch

Tạo hai ứng viên cùng snapshot: một đã biết tại 12/08/2025 11:00 UTC+07, một
posted/observed ngày 13/08. Upload/preview/commit chấp nhận có cảnh báo; analyze
trả RULE_CANDIDATE_MISSING từ bridge, không trả được kết quả của dòng đã biết.

Kỳ vọng: bảo toàn từng ứng viên theo hợp đồng hàng đầu ra, dòng chưa nhìn thấy
tại cutoff có unavailable/lý do và không rò nguồn tương lai vào feature/model;
các dòng đủ nguồn vẫn được đánh giá. Nếu muốn đổi sang từ chối chọn ứng viên
ngay lúc nhập thì phải chốt/phiên bản hóa hợp đồng, không để lưu rồi lỗi cả lượt.

Reproducer riêng, không chạm live/credential:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_rule_cutoff_regression.py --report .runtime/cutoff-retest.json
```

Lượt kiểm này exit 1/status failed đúng lỗi đang mở; không ghi thành pass.
Cần bổ sung test mixed batch và trường hợp tất cả ứng viên ngoài cutoff trước
khi sửa adapter/analyze. Cẩn thận đổi hash/fingerprint làm model mới không còn
tương thích; chưa thay model live để né gate.

### P1 — bridge đã có nhưng model cho Portal nguồn đầy đủ chưa được chuẩn bị

`local-analysis-bindings.json` đang có bindings rỗng. Kho model Portal chỉ có
4 artifact canonical snapshot-point-in-time/1.1.0: Mahalanobis hai biến và
RobustZ, mỗi loại cho C001/C002. Không có artifact contract mới
rule-snapshot-point-in-time/1.0.0 được ghim cho profile nguồn đầy đủ.

Vì vậy ML local trên nguồn mới unavailable là đúng gate, không phải bridge
chưa được viết. Việc tiếp theo là fit offline trên train/reference đúng kỳ và
đúng DN, kiểm missing policy (8 cột chưa có cấu trúc nguồn giữ null), rồi ghim
artifact qua quyền quản lý phù hợp và thử 5 ứng viên/DN trên Portal. Không dùng
artifact canonical cũ hoặc model fit sau kỳ để làm ML hiện điểm cho được.
Model mới cần phát sinh đúng quy trình; không tự fit khi người rà bấm phân tích.

### P2 — khôi phục C002 qua trang Portal ngoài cần nghiệm thu tiếp

Báo cáo QA trước còn finding: reload /#agent2 mở workspace mặc định C001,
không tự mở lại snapshot C002 vừa dùng. Lượt này đã sửa cutoff của trang nhập,
chưa sửa routing/selector lịch sử ở workspace và chưa tái nghiệm thu finding
trên Portal đã đăng nhập. Cần kiểm lại riêng, không lấy PASS tổng của báo cáo
cũ làm bằng chứng ca này đã đạt.

### P2 — chốt chứng cứ HE native/HTTP/recovery của phần mở rộng

Các adapter mới và C3 build có thật, hash server/client manifest kiểm được;
C3 source hash khớp code hiện tại. Lượt này không chạy thêm bản verifier nặng
để tránh đụng tiến trình kiểm chứng HE riêng đang có. Chưa thấy metrics.json
hoàn tất của he_rule_expansion_20261114 khi chốt báo cáo.

Cần lấy kết quả verifier từng lát cắt thật, gồm thất bại/recovery/timing, rồi
mới đưa vào coordinator/Portal opt-in. Worker ready hiện tại là các profile
đang cấu hình, không chứng minh P1/C3/B1/B5/E4 mới đã HE end-to-end hoặc đủ35HE.

## Bằng chứng của lượt này

- `.runtime/recheck-20261114-current-bridge.json`: 55 tests.
- `.runtime/recheck-20261114-he-expansion.json`: 33 tests.
- `.runtime/recheck-20261114-he-lifecycle.json`: 21 tests.
- `.runtime/recheck-20261114-reload-before.log`: Chrome tái hiện lỗi trước sửa.
- `.runtime/recheck-20261114-reload-after/report.json`: 8 bước UI sau sửa.
- `.runtime/recheck-20261114-cutoff-gap.json`: ca lỗi còn mở.
- `.runtime/recheck-20261114-runtime/after-preservation.json`: runtime/preservation.

Không reset mật khẩu/quyền, không fit/đổi model hoặc xoay khóa, không chỉnh
trọng số/routing/queue và không push Git. Không suy accuracy từ kiểm thử mô phỏng.
