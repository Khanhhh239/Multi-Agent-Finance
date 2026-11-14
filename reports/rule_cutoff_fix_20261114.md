# Sửa batch có ứng viên sau as_of — 14/11/2026

**Đã sửa và kiểm chứng kỹ thuật trên server thử riêng.** Không còn lỗi toàn
lượt RULE_CANDIDATE_MISSING khi snapshot có ứng viên chưa nhìn thấy tại cutoff.

- Trả đủ số dòng và giữ thứ tự ứng viên của snapshot.
- Chỉ tạo feature/chấm model cho ứng viên có posted_at và observed_at không
  sau as_of. Dòng còn lại unavailable, matched/score null, lý do
  `transaction_not_visible_at_as_of`; không fake vector, không đổi đồng hồ.
- Với toàn bộ ứng viên ngoài cutoff, không gọi score_batch hoặc replay cả lịch
  sử để lấp batch. Nếu không có core native nhìn thấy thì không gọi kết quả
  giả của engine: 35 entry source unavailable, native_reference_sha256=null.
- Giữ nguyên kiểm quyền, checksum, ID không tồn tại vẫn bị từ chối và as_of
  vẫn phải khớp mốc nguồn đã khóa. Guard nguồn của các ứng viên chỉ xét dòng
  nhìn thấy, tránh ứng viên tương lai làm thay đổi kết quả dòng đủ điều kiện.
- API thêm availability/lý do riêng ở dòng chưa khả dụng. UI hiển thị cảnh báo
  ngay trên dòng; kỳ giao dịch tổng hợp chỉ tính dòng nhìn thấy. Thông tin tệp
  gốc trên thẻ vẫn là metadata snapshot, không phải feature/điểm đã được chấm.

## Bằng chứng

| Kiểm chứng | Kết quả |
|---|---|
| Bộ hồi quy backend/API/bridge/35 luật, gồm test mới | 61/61 đạt |
| HE adapter P1/C3/định danh và snapshot adapter liên quan | 17/17 đạt; không tuyên bố 17 phép FHE native |
| Chrome UI, gồm mixed/all-future và reload | 10/10 bước, không lỗi JavaScript |
| ECOD/RobustZ thật trong sandbox, 5 ứng viên | Đủ 5 kết quả; 4 dòng nhìn thấy giữ nguyên raw_score/score, dòng tương lai không đi vào frame chấm |
| Hai DN cùng mã giao dịch; boundary == as_of | Đạt |
| HTTP thật, snapshot lưu thật và technical view | 200, đủ 5 dòng, reason/null đúng ở dòng tương lai |

Nguồn hợp lệ được quan sát nhưng ngày phát sinh còn ở tương lai cũng bị chặn
chấm đúng lý do. Có test cả all-future vẫn có lịch sử và all-future không có
giao dịch core nhìn thấy. Ca thử ban đầu có timestamp observed trước approved
bị validator từ chối đúng; đã sửa fixture scheduled transaction cho hợp lệ,
không nới validator.

`snapshot_features.py`, `rule_snapshot_features.py`, `method_adapters.py` và
các estimator/preprocess không đổi. Contract/fingerprint feature và model cũ
được giữ; analysis ID ghim thêm hash module visibility mới. Không fit khi chấm,
không đổi model/key live. Các fit dùng để kiểm chứng chỉ ở SQLite sandbox tạm.

## Tệp chính

- `agent2/sme_fraud/rule_snapshot_visibility.py`: chọn ứng viên nhìn thấy,
  empty frame/provenance và kết quả unavailable riêng dòng.
- `agent2/sme_fraud/rule_snapshot.py`: orchestration/DTO, fallback core không
  nhìn thấy; không sửa kernel luật.
- `agent2/sme_fraud/analysis_branches.py`, `web/workbench.js`: lý do dễ đọc.
- `agent2/tests/test_rule_snapshot_cutoff.py`: hồi quy, model thật và HTTP.

## Tái chạy

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_rule_cutoff_regression.py --report .runtime/cutoff-rerun.json
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_r1_tests.py --report .runtime/cutoff-tests-rerun.json --suite test_rule_snapshot_cutoff
agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_rule_snapshot_ui.py --cutoff-cases --output .runtime/cutoff-ui-rerun-new
```

Output UI phải là thư mục mới. Lượt kiểm chứng này không restart/deploy
backend Portal đang chạy, không dùng phiên đăng nhập thật hoặc push Git.
Bản backend giữ module cũ cần được nạp lại qua lifecycle vận hành trước khi
nghiệm thu Portal live; không coi test server riêng là đã nghiệm thu live.

Sau sửa này, model cho contract nguồn đầy đủ chưa ghim trên Portal và routing
khôi phục C002 vẫn là các việc riêng của [báo cáo rà](agent2_recheck_20261114.md).
