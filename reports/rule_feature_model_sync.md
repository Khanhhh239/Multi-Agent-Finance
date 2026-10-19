# Đồng bộ feature/model và chấm các bản sửa kết hợp — 17/10/2026

**Cập nhật tiếp theo:** đã có [bản sửa tiếp nhận mẫu chia nhỏ A2/A4](rule_split_pattern_admission.md), giữ điểm/ngưỡng/hard trigger và tháng lịch. **373/373 test, 7/7 probe đạt**; validation so với trạng thái đồng bộ bên dưới: **TP 194 → 200, FP 1.208 → 2.347**. Khôi phục 5/6 dòng mất cảnh báo; ca A4 còn lại đúng giới hạn tháng và có A1 ở khoản sau 5 giờ 5 phút. Tải hồ sơ tăng, chưa nghiệm thu vận hành. Các số liệu bên dưới là snapshot **trước sửa tiếp nhận**; model/cache nguồn của snapshot này được giữ nguyên.

## Phạm vi và cách tái lập

Lượt chính thức: [kế hoạch khóa trước đánh giá](feature_model_sync_20261017/evaluation_plan.json). Ba bộ gốc `sme_fraud_001/003/005`, seed 20261012; mỗi bộ chọn 50.000 dòng train năm 2024 và 25.000 dòng validation nửa đầu 2025. Mốc nguồn là trước `2025-07-01T00:00:00+07:00`. Chỉ chấm train/validation; không chấm test hoặc chọn lại ngưỡng bằng nhãn. Train là kết quả hồi cứu trên dữ liệu đã dùng fit, không phải đo ngoài mẫu.

```powershell
python -B -m sme_fraud.sync_feature_model --output reports/feature_model_sync_20261017 --jobs 4
```

Dữ liệu dẫn xuất ở `data/feature_model_sync_20261017/sme_fraud_00x`; model, prediction, hit, queue và SQLite rà soát ở `reports/feature_model_sync_20261017`. Lệnh từ chối ghi đè đầu ra dở dang; chỉ tiếp tục các bộ đã hoàn tất khi kế hoạch và hash mã vẫn khớp. Muốn chạy với mã/cấu hình khác phải dùng thư mục mới.

Baseline là các snapshot ban đầu `reports/rules/sme_fraud_00x` và model ở `reports/sme_fraud_00x`. So sánh bao gồm các thay đổi phase 2/3/4 và R1–R8 đến hiện tại; không tách riêng tác động nhân quả của R1–R8. Giữ chính sách thiếu hồ sơ nghĩa vụ chi, ngưỡng vận hành 7 điểm, cấu hình IF 300 cây / max_samples 2048 / seed 20261012. `n_jobs=4` chỉ giới hạn tài nguyên.

Ensemble giữ công thức 0,8 thứ hạng rule/graph + 0,2 thứ hạng IF, tham chiếu phân phối validation. Ngưỡng so sánh là quantile validation chưa gán nhãn, ngân sách 0,3%, `method=higher`. Có báo cáo riêng top-k cố định để thấy ảnh hưởng hòa điểm. Hàng đợi luật/hard trigger vẫn được dựng trước ensemble; sự kiện đóng lô được tính riêng, không ghi ngược điểm vào dòng giao dịch.

## Hợp đồng cache và model

`feature_contract.py` khóa thứ tự và mô tả 190 cột, dtype float32, phiên bản ngữ nghĩa, hash mã phụ thuộc, hash nguồn và nội dung feature CSV. Loader từ chối cache thiếu/sai provenance; model phải khớp hợp đồng, số cột, phiên bản sklearn, hướng điểm, định dạng dataset và có fingerprint dữ liệu train. Không tự bổ sung provenance cho model cũ. Model mới được fit chỉ trên train, lưu/nạp lại và đối chiếu chính xác điểm validation.

Nguồn callback tổng hợp cũ có bản ghi xác minh sau thời điểm quan sát, vi phạm R7. Chỉ với nguồn có provenance tổng hợp, bản dẫn xuất giữ một observation chưa xác minh rồi thêm revision tại `verified_at`; chỉ revision trước cutoff được đưa vào. Không đổi ID giao dịch/nhãn hoặc lùi ngày xác minh. Nguồn thật có lỗi tương tự phải được chủ nguồn sửa, không được tự chuyển đổi theo cách này. Từng bản ghi nằm trong `callback_revision_log.json` của dataset dẫn xuất.

Bước dựng feature nạp đầy đủ dòng bút toán chính; từ chối giao dịch tài chính không có nguồn bút toán. Một lượt thử ban đầu thiếu nguồn này đã bị loại, ghi rõ tại [REJECTED.md](feature_model_sync_20261016/REJECTED.md); không dùng kết quả của lượt đó.

## Kết quả

Đã hoàn tất **225.000 dòng**, ba cache feature, ba model IF và ba cache SQLite riêng; **352/352 test hồi quy**, **7/7 probe readiness** đạt. Cả ba bộ đều giữ nguyên giá trị 190 cột so với cache gốc trên đúng các ID train/validation, nên IF không đổi điểm sau refit. Model mới có provenance đầy đủ và replay chính xác từ cache CSV đã lưu. Đây là kết quả tương thích trên bộ chuẩn, không chứng minh các nhánh nguồn mới đều có dữ liệu đại diện.

[Tổng kết máy đọc](feature_model_sync_20261017/summary.json), [kiểm tra artifact đã lưu](../.runtime/feature_model_sync_20261016/artifact_verification.json), [log hồi quy](../.runtime/feature_model_sync_20261016/tests.log), [log probe](../.runtime/feature_model_sync_20261016/readiness_probes.log).

Cảnh báo vận hành theo dòng ở ngưỡng 7 điểm / hard trigger; số hồ sơ tính theo kỳ mở hồ sơ:

| Bộ | Kỳ | Dòng gian lận | TP trước → sau | FP trước → sau | Precision sau | Recall sau | Hồ sơ trước → sau |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1% | train | 50 | 45 → 45 | 1760 → 841 | 5.08% | 90.00% | 1286 → 701 |
| 0.1% | validation | 25 | 22 → 20 | 911 → 398 | 4.78% | 80.00% | 644 → 335 |
| 0.3% | train | 150 | 130 → 128 | 1765 → 839 | 13.24% | 85.33% | 1352 → 772 |
| 0.3% | validation | 75 | 65 → 64 | 911 → 405 | 13.65% | 85.33% | 675 → 374 |
| 0.5% | train | 250 | 217 → 218 | 1766 → 843 | 20.55% | 87.20% | 1414 → 844 |
| 0.5% | validation | 125 | 111 → 110 | 915 → 405 | 21.36% | 88.00% | 709 → 408 |

Ensemble là chỉ số benchmark riêng; top-k dưới đây lấy đúng 75 dòng validation/bộ, không dùng làm bộ lọc loại hard trigger khỏi queue:

| Bộ | AP IF trước/sau | AP ensemble trước → sau | TP/FP ensemble sau, top 75 |
| --- | ---: | ---: | ---: |
| 0.1% | 0.0113 | 0.2932 → 0.3010 | 12/63 |
| 0.3% | 0.0432 | 0.4032 → 0.4109 | 27/48 |
| 0.5% | 0.0896 | 0.4730 → 0.4771 | 38/37 |

Tải validation ở 3 hồ sơ/công ty/ngày, trần 135 phút/ngày; việc chưa xử lý được chuyển sang ngày sau:

| Bộ | Phút trước → sau | Đỉnh tồn việc trước → sau | Việc phải chuyển ngày trước → sau |
| --- | ---: | ---: | ---: |
| 0.1% | 14270 → 7105 | 8 → 3 | 11 → 0 |
| 0.3% | 14950 → 7945 | 7 → 5 | 14 → 2 |
| 0.5% | 15710 → 8685 | 7 → 3 | 10 → 0 |

### Các ca cần rà tiếp

**Trạng thái hiện tại:** cơ chế tiếp nhận đã sửa và các ca đã được phân tích tại [báo cáo tiếp nhận A2/A4](rule_split_pattern_admission.md). Phần dưới giữ nguyên phát hiện và số liệu trước sửa để đối chiếu.

Nhiễu giảm nhưng có giao dịch gian lận mô phỏng mất cảnh báo vận hành. Không đóng khoảng trống này bằng việc hạ ngưỡng toàn hệ thống theo nhãn. Cần rà cơ chế đưa mẫu chia nhỏ vào hồ sơ: A2/A4 còn hit thuộc cùng họ A, tổng điểm có thể chỉ còn 4 dưới ngưỡng 7 sau khi bỏ tín hiệu nhiễu C1/E3. Với A4 bị mất hit, cần đối chiếu chính sách tháng lịch với kịch bản đi qua ranh giới tháng trước khi kết luận predicate sai.

| Bộ | Kỳ | Thêm / mất dòng gian lận có cảnh báo |
| --- | --- | ---: |
| 0.1% | train | +0 / −0 |
| 0.1% | validation | +0 / −2 |
| 0.3% | train | +1 / −3 |
| 0.3% | validation | +1 / −2 |
| 0.5% | train | +4 / −3 |
| 0.5% | validation | +1 / −2 |

Bộ 0,1% validation có hai ca `distributed_days`: `T000038122`, `T000050567`, điểm **8 → 4**; A2 vẫn có hit nhưng không vào queue. Đây là bằng chứng cần rà chính sách tổng hợp/tiếp nhận cảnh báo, không phải model IF đổi điểm.

Mỗi thư mục bộ dữ liệu có `score_changes_train_validation.csv`, `score_change_analysis.json`, `changed_hits_train_validation.csv`, `case_identity_comparison.json` và `comparison_train_validation.json`: đối chiếu từng ID, điểm/hard trigger, rule mất/thêm, hit và bằng chứng hiện tại của các ca gian lận mất cảnh báo. Báo cáo JSON chứa cả hard negatives, loại gian lận, chế độ kế toán, từng rule/công ty, precision hồ sơ hồi cứu và tải ở 1/3/5 hồ sơ/công ty/ngày. Các thay đổi score/hit không được cộng cơ học thành tác động toàn queue.

Đổi ID theo R6 được lưu đối chiếu theo giao dịch chung; không tự chuyển feedback/phân công sang hồ sơ đổi phạm vi. Tất cả file nguồn và snapshot/model baseline đã được kiểm tra hash giữ nguyên. Ba SQLite mới nạp và replay thành công.

## Giới hạn nghiệm thu

Các số TP/FP bên trên dựa trên nhãn gian lận mô phỏng. FP theo nhãn này không tự chứng minh điều kiện kế toán/nghiệp vụ của rule sai. Precision hồ sơ hồi cứu dùng thành viên quan sát tại cutoff; độ hữu ích lúc mở hồ sơ và tải phút/ngày được báo cáo riêng trong `workload`.

Mô phỏng tải dùng ước lượng 20–45 phút/hồ sơ và cấp năng lực mỗi ngày lịch, kể cả cuối tuần; chưa phải lịch làm việc hoặc thời gian xử lý đo được của SME. Chỉ số tải trước/sau hỗ trợ so sánh nội bộ, chưa đủ để chốt nhân sự/SLA vận hành.

Các file `case_identity_comparison.json` chỉ liệt kê hồ sơ cũ và hồ sơ mới có giao dịch chung, không cấp quyền chuyển kết luận. Cache SQLite mới được dựng riêng; chưa chạy migration phản hồi/phân công trên database vận hành cũ. Khi áp dụng vào bộ rà soát có lịch sử người dùng, tiếp tục dùng chính sách tương đương một-một và rà lại split/merge của [R6](rule_case_identity.md).

Nguồn bổ sung ERP/HR/công nợ thật vẫn chưa được nghiệm thu; cổng F1/C4/E2/F2/F3/F4 còn `awaiting_real_data`, 0 đơn vị chấm mù, `not_frozen`. Bộ tổng hợp thiếu các nguồn mới không đủ chứng minh hiệu quả của mọi nhánh ngoại lệ. Bước tiếp theo là nghiệm thu nguồn và kết luận độc lập, đo chất lượng/tải rà soát thực tế, rồi đánh giá trên tập mới giữ kín. Chưa có cơ sở tăng số luật hoặc siết ngưỡng đồng loạt từ kết quả đồng bộ này.
