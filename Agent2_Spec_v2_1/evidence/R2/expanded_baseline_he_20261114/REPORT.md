# CR-049 — HE hiện có và baseline luật đã mở rộng

14/11/2026 · spec_version=2.1 · **READY_FOR_REVIEW cho kiểm chứng kỹ thuật;
độ phủ HE của baseline vẫn PARTIAL.** Không duyệt toàn R2 hoặc production.

Người dùng giao kiểm chứng tính mã hóa rồi chạy lại so sánh ML với baseline
luật mở rộng. Đã đo mới CKKS cho C001/C002 và hai ca P1 Concrete, sau đó khóa
báo cáo so sánh local P1/E3/B5/E4. **E3/B5/E4 chưa có evaluator HE**, không
gửi raw của ba luật đó cho worker hoặc gọi kết quả local là full HE.

## Kết quả thực đo

| Hạng mục | C001 | C002 |
|---|---|---|
| Nguồn | 8 giao dịch mô phỏng, snapshot 1.2.0 mới | 8 giao dịch mô phỏng, snapshot 1.2.0 mới |
| Feature | Toàn bộ 33 feature bằng bản nguồn 1.1.0 trước bổ sung master | Tương tự |
| ML đã chấm HE mới | 7 khả dụng, 1 chưa khả dụng, không mất dòng | 7 khả dụng, 1 chưa khả dụng, không mất dòng |
| Sai lệch ML tuyệt đối lớn nhất | 0.00005083814993156466 | 0.00005091664951351049 |
| Đảo cặp vượt dung sai | 0 | 0 |
| Thứ tự tuyệt đối | Có đổi thứ tự điểm gần nhau trong dung sai | Tương tự |
| Chỉ luật / ngân sách tối đa | T03, T06, T07 — 3/5 | T03, T06, T07 — 3/5 |
| Luật + ML / ngân sách tối đa | Giữ ba khoản, thêm T04/T02 — 5/5 | Giữ ba khoản, thêm T04/T02 — 5/5 |
| Tập chọn khi ML tính rõ và mã hóa | Giống nhau | Giống nhau |
| P1 native FHE mới | T03 đã vượt: số nguyên/matched khớp | T05 có điều chỉnh âm lịch sử: số nguyên/matched khớp |
| P1 wall time ở fixture | 267.219 giây | 229.063 giây |

Tiền tố đầy đủ của ID là `P1_`. T06/T07 là một nhóm đồng thời; không cắt nhóm
cho vừa ngân sách hoặc coi thành hai vụ gian lận độc lập. Baseline P1 có một
row-hit, năm row-no-hit, một không áp dụng và một thiếu nguồn; group-hit T06/T07
được giữ riêng với row-no-hit. Ba master rules có 8 no-hit/DN trong nguồn một
NCC đã cung cấp, chưa chứng minh master bên ngoài đầy đủ.

B5/E4/E3 giữ master-quality, 0 điểm đóng góp giao dịch; không tự thay trọng số
hoặc tạo cảnh báo để làm baseline có thêm khoản chọn. Hai phương án dùng cùng
cap 5, số được chọn thực tế 3 và 5; không padding danh sách luật. T04 là điều
chỉnh âm P1 không áp dụng, T02 chưa vượt nghĩa vụ. Còn 31 luật snapshot chưa
nối. Không gọi hai khoản bổ sung là gian lận hoặc toàn bộ luật đã bỏ sót.

Accuracy/precision/recall/lợi ích thêm/thời gian rà nghiệp vụ vẫn null vì chưa
có đối chiếu người rà. Sai lệch số học nhỏ không phải độ chính xác gian lận.
ML timing ở JSON là đăng ký + HTTP evaluate + giải mã, không gồm nạp nguồn,
model và chuẩn bị mã hóa; P1 wall time gồm encrypt/HTTP/open. Không so hai
đại lượng này thành SLA hoặc benchmark thời gian nghiệp vụ.

## Kiểm thử và các ràng buộc

- **299 HE tests pass**, không fail/error/skip, gồm crypto boundary, scope,
  key/session, replay, source plans và recovery hiện có.
- **82 native/focused tests pass**, gồm baseline mở rộng, P1/source parity,
  snapshot B5/E4 và nguồn thiếu/thời gian/khóa model.
- **10 selection compatibility tests pass** sau refactor helper chung;
  đây là subset chạy lại của suite HE, không cộng như 10 tests độc lập mới.
- Hai công ty chấm CKKS mới bằng model đã fit riêng từ registry hiện có;
  hash DB model và hai tệp khóa bảo vệ giữ nguyên. Fit/publish bị spy chặn.
- P1 dùng public worker bundle mới, state/port riêng trong WSL; DPAPI helper
  DN dùng đúng context/key epoch đã có. Encrypt/return/decrypt thật, signed
  response và ciphertext hash được kiểm; đọc lại ciphertext commit giống hệt.
- Hai ca P1 là spot-check native trên nguồn mới, chưa là lượt HE mới cho mọi
  request P1/đồ thị/RobustZ hoặc toàn catalog. Supervisor Portal preflight được
  bỏ qua trong fixture; không ghi đã nghiệm thu Portal live hoặc public cloud.
- Thời hạn/replay worker cũ giữ nguyên. Không restart dịch vụ live, đổi queue,
  model/khóa hoặc dùng thông tin đăng nhập Portal trong công cụ đo này.

Một lỗi mới trong helper so sánh được test bắt: thêm dòng ML trùng ID vẫn có
thể lọt qua vì chỉ đếm khóa duy nhất so với row_count. Đã kiểm cả chiều dài
danh sách và khóa duy nhất, từ chối trùng; 82 tests cuối đạt. NaN/Infinity bị
từ chối trước khóa JSON; không sanitize thành 0. Các lượt CLI đầu sửa sai tên
import/API receipt/group khi nối công cụ; không đổi dữ liệu/ngưỡng để qua test.

Report comparison ban đầu được khóa trước các bổ sung kiểm tra metadata của
helper. Đã dùng code cuối đọc lại projection của điểm HE đã xác thực và cùng
nguồn: selections/groups/coverage giống hệt cả hai DN (`current-code-recheck`).
Không chấm HE lần hai hoặc sửa bản khóa cũ. Revalidated comparison giữ riêng
hash báo cáo cũ, request hash HE và ghi rõ nguồn điểm là projection.

## Lệnh

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_expanded_baseline_he.py --output .runtime/he4/expanded-baseline-20261114-v3
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_he_tests.py --report .runtime/he4/expanded-baseline-he-tests.json
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_r1_tests.py --report .runtime/he4/expanded-baseline-native-tests-v3.json --suite test_expanded_selection --suite test_vendor_identity_snapshot --suite test_rule_evaluation --suite test_rule_sources --suite test_rule_parity --suite test_p1_evaluation
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_he_tests.py --report .runtime/he4/expanded-baseline-selection-tests-final.json --suite test_selection_comparison
```

Các lượt cuối exit 0. Tổng kiểm chứng native/ML/so sánh khoảng 504 giây ở máy
local lượt này, không phải thời gian nghiệp vụ hoặc SLA. Báo cáo công khai chỉ
copy allowlist: nguồn mô phỏng, kết quả/metrics đã mở và test logs; không copy
auth policy, key/vault, worker config/state, DB hoặc packet có private receipt.

Mã mới: `expanded_selection.py`, `check_expanded_baseline_he.py`,
`test_expanded_selection.py`; selection_comparison dùng chung helper chọn theo
cap mà không đổi policy cũ. Không sửa kernel/circuit/registry/33 feature/HE
transport. Các schema đầu vào cũ và mới của CR-048 giữ nguyên trong lượt này.

[Báo cáo dễ đọc](../../../../reports/expanded_baseline_he_20261114.html) ·
[Hướng dẫn](../../../../agent2/docs/EXPANDED_BASELINE_HE.md).
