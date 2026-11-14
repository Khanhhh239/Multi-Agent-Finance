# Đánh giá P1 — thanh toán vượt tổng giá trị cùng hóa đơn

CR-023 đã nối [API phân tích snapshot P1/E3](SNAPSHOT_ANALYSIS_API.md), có kiểm quyền và hai view. Không gọi fit/model hoặc tạo cảnh báo nghiệp vụ trong HTTP request này.

CR-019 đã nối evaluator `p1-evaluation/1.0.0` vào backend snapshot scoring. Kết quả ở `methods.rules.details.rule_results.rules`, dòng `rule_id=P1`. Shape RuleResult vẫn 1.0.0; RuleInputs là 1.1.1. Không thay bộ 33 feature, model hoặc kernel native.

## Ví dụ dễ đối chiếu

| Hóa đơn | Đã trả trước | Khoản hiện tại | Kết quả P1 |
|---|---:|---:|---|
| 10 triệu | 4 triệu | 7 triệu | Tổng 11 triệu, vượt 1 triệu; điểm dòng 20 |
| 10 triệu | 4 triệu | 6 triệu | Đúng 10 triệu; điểm dòng 0 |
| 10 triệu | 4 triệu | Hai khoản đồng thời, mỗi khoản 4 triệu | Mỗi dòng xét riêng là 8 triệu, điểm 0; kiểm nhóm là 12 triệu, điểm nhóm 20 |
| 12 triệu | Trả 12 triệu, sau đó giảm hợp lệ 2 triệu | 1 triệu | Lịch sử ròng 10 triệu, tổng 11 triệu; điểm dòng 0 |
| 12 triệu | Khoản giảm 2 triệu chỉ được biết sau khoản hiện tại | 1 triệu sau khoản trả 12 triệu | Tại thời điểm đó tổng biết được là 13 triệu; khoản giảm biết muộn không sửa kết quả quá khứ |
| 10 triệu | Chưa có phạm vi lịch sử đủ nguồn | Bất kỳ | unavailable, điểm null; không tự coi đã trả trước bằng 0 |

Đây là dữ liệu mô phỏng, không chứng minh gian lận hoặc hiệu quả ML.

## Cách tính và thời gian

- Dùng **số tiền phân bổ** cho từng nghĩa vụ, không lặp toàn bộ tiền giao dịch trên từng hóa đơn. Revision thay thế phiên bản cũ; bản ghi điều chỉnh riêng là delta có dấu, tính một lần.
- Giữ điều kiện native: row hit cần có thanh toán trước và `prior_paid_vnd + current_allocated_vnd > invoice_gross_vnd + 1 VND`. Trọng số P1 giữ 20, không nhân theo số hóa đơn. Khoản đầu tiên vượt hóa đơn chưa tự thành row hit P1 theo chính sách native này; không có nghĩa khoản đó hợp lệ.
- Lịch sử đòi cả effective_at và available_at của giao dịch/phân bổ **trước** event/cutoff hiện tại. Cùng một mốc thời gian thì tách sang kiểm nhóm, không đưa vào lịch sử nhau. Global as_of chỉ giới hạn tập đầu ra; mỗi dòng vẫn dùng cutoff riêng của R1.
- `details.invoice_checks` có số đã trả trước có dấu, tiền hiện tại, tổng, phần vượt và refs. `details.simultaneous_checks` là kiểm nhóm độc lập, có group_id, matched, points và `score_role=group_only_not_row_contribution`.

**Điểm nhóm không cộng vào điểm dòng.** Các dòng cùng nhóm có thể tham chiếu cùng group_id/kết quả kiểm nhóm. Đây chưa phải phát event hoặc hồ sơ nghiệp vụ. Không đếm các bản tham chiếu đó thành nhiều cảnh báo. Row hit và kết quả nhóm có thể khác nhau, chẳng hạn khoản giảm âm xuất hiện đồng thời với khoản chi: khoản giảm không là lịch sử của dòng chi nhưng có mặt trong tổng kiểm nhóm.

## Điều chỉnh, định danh và thiếu nguồn

Phân bổ điều chỉnh phải dẫn đúng phân bổ gốc; giao dịch điều chỉnh cũng phải dẫn đúng giao dịch gốc trong cùng nghĩa vụ và thời gian. Kiểm dấu tiền, số tiền phân bổ, chuỗi gốc, phiên bản và tổng giảm. Thiếu liên kết, phân bổ giảm gắn sang nghĩa vụ khác, giảm vượt gốc hoặc tổng phân bổ vượt tiền giao dịch đều unavailable/null, không ép về 0 hoặc đổi dấu. Dòng adjustment/reversal không tự được coi là payment mới để chấm row P1; nó tham gia số ròng của các khoản chi sau khi khả dụng.

Giữ khóa nghĩa vụ native theo doanh nghiệp/NCC/số hóa đơn chuẩn hóa, để hai ERP ID không làm nhân đôi trần. Alias phải có coverage phù hợp; giá trị mâu thuẫn cần đối chiếu. Invoice revision thay thế; invoice adjustment/credit note có adjusts_ref là delta có dấu theo nguồn. Cap sau điều chỉnh không xác định hoặc không dương thì unavailable. Không ghép theo số tiền gần giống.

Vẫn cần [đầu vào 1.1.0](P1_INPUTS.md), kênh bank/cash và coverage complete/since_inception với manifest nhất quán tại cutoff. Nguồn thiếu, partial/unknown/bounded, stale hoặc mâu thuẫn không thành no-hit. Coverage là khai báo ràng buộc tập nguồn đã gửi, không xác minh độc lập đầy đủ sổ bên ngoài.

## Chạy thử

Từ thư mục gốc repo, chọn thư mục kết quả chưa tồn tại:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_p1_evaluation.py --output-dir agent2/.runtime/p1-evaluation-results
```

Demo upload → preview → commit → score cho năm tình huống ở trên, giữ đủ số dòng và kiểm retry không tạo snapshot trùng. Tệp source/validation/snapshot/results và summary được lưu để đối chiếu. Dùng quyền thử nghiệm backend cục bộ; không mô phỏng đăng nhập production.

Kiểm thử có đối chiếu native trên miền dương/một hóa đơn, cùng tiền mặt, dung sai và nhóm đồng thời. Kernel native không nhận số âm; phần điều chỉnh có dấu được kiểm riêng bằng kết quả nghiệp vụ định trước và thời gian nguồn. Không tuyên bố parity native cho miền số âm.

Chạy đối chiếu độc lập, có cả lịch sử cách 45 ngày:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_p1_evaluation.py --output agent2/.runtime/p1-native-parity.json
```

Tổng `rules` vẫn `rules_incomplete/null` vì các luật khác chưa đầy đủ. Không fit, thay active model, tăng trọng số ML hoặc đưa kết quả vào queue trong bước này. R2 tổng thể vẫn PARTIAL.

## Đối chiếu CR-020 và bản sửa CR-022

Audit mới có cả nguồn thiếu và nguồn biết muộn:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_p1_acceptance.py --output-dir agent2/.runtime/p1-acceptance-recheck
```

Chọn thư mục kết quả chưa tồn tại. Exit **2** nghĩa là còn finding; exit **0** chỉ nói các assertions trong phạm vi audit đạt, không nghiệm thu toàn engine. [Báo cáo CR-020](../../Agent2_Spec_v2_1/evidence/R2/p1_recheck_20261111/REPORT.md) giữ bằng chứng lỗi trước sửa; [CR-022](../../Agent2_Spec_v2_1/evidence/R2/p1_native_fix_20261111/REPORT.md) ghi kết quả sau sửa.

**P1-NATIVE-LATE-INVOICE đã có bản sửa CR-022 trong phạm vi đã kiểm:** đường native kiểm cả thời điểm phát hành/được biết đã khai báo ở current và prior/batch. Nguồn chưa khả dụng được giữ là information_gap, points=0, hard_trigger=0 và signal=null; không phải evaluated_no_hit và không phát risk từ tổng thiếu nguồn. Đường snapshot canonical vẫn trả unavailable/null. Giao dịch sau có thể dùng chứng từ đã đến, kết quả quá khứ giữ nguyên.

Header legacy không có mốc thời gian vẫn giữ tương thích đầu vào cũ, không được chứng nhận đúng as_of. Native cũng chưa có coverage/availability theo phân bổ hoặc signed corrections như canonical. Bản sửa này không mở rộng thành nghiệm thu các luật khác hoặc toàn pipeline. Shape đầu ra, weight P1=20, dung sai, 33 feature và model giữ nguyên.

Phân biệt tài liệu: hóa đơn/phân bổ bắt buộc biết muộn làm P1 unavailable tại cutoff; tệp đính kèm không thuộc yêu cầu P1 đến muộn không tự vô hiệu hóa P1 khi nguồn cần thiết đã đủ, và không được đưa vào bằng chứng quá khứ. Legacy hit list không có khả dụng/coverage tương đương; không đổi null thành 0 chỉ để khớp điểm.
