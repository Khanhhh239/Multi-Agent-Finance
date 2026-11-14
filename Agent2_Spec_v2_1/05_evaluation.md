# Đánh giá ML và pipeline — nguồn đặc tả đánh giá chính

BẮT BUỘC: RULE-TIME-01, RULE-LABEL-01, RULE-FIT-01, RULE-SCORE-01 và RULE-RELEASE-01. Đọc D-03/04/09/13 trong 99. R2 kiểm parity và chạy benchmark detector ứng viên; R6 nghiệm thu pipeline/cảnh báo thật. Parity không chứng minh chất lượng phát hiện.

## E1. Dữ liệu và protocol

Lưu EvaluationPlan trước xem test: dataset/snapshot, DN, kỳ, feature/reference/model versions, target/label provenance, grouping, budget, seeds, metrics, weights nếu có, baseline, acceptance thresholds và người duyệt. Chia history/train → validation chọn detector/tổ hợp → validation policy/threshold → test tương lai. Tách cùng case/template/episode, cách ly episode qua biên; báo hiệu quả theo DN và họ rủi ro khi đủ mẫu. Giữ người rà soát không biết phương pháp khi tổ chức được.

Synthetic regression fixture chỉ kiểm tính đúng, không đủ để đánh giá độ chính xác ML hay khả năng chuyển miền. Ground truth thật phải ghi tỷ lệ có kết luận; thiếu nhãn thì report insufficient_labels và chỉ phát hành technical report.

## E2. Benchmark ML không nhãn (R2)

Chạy EntityDeviation, ECOD, IF, HBOS, AE nếu hiện có và đủ điều kiện. Cùng feature thông tin tương đương, history window, validation/test, policy gộp và ngân sách. Adapter tiền xử lý có thể riêng nhưng phải version. Fit trên lịch sử cũ; không fit/refit reference trên batch test. Lịch sử không nhãn có thể chứa rủi ro: đo độ nhạy nhiễm bẩn và thay đổi history nếu có dữ liệu; không tự xóa mọi điểm cao.

Xuất từng detector, baseline hiện tại và tổ hợp nhỏ. Ghi số dòng khả dụng/không khả dụng và lý do; so trên toàn bộ vận hành kèm fallback, đồng thời báo phân tích trên common-coverage subset để hiểu khác biệt. Không chỉ bỏ dòng khó để làm đẹp precision.

Thử nhiều seed cho detector ngẫu nhiên theo D-09 (số seed chốt trước); báo mean/dispersion khi có. Xác định vụ đúng mới mà phương pháp thêm bắt được và overlap/Jaccard; chỉ giữ thành phần có lợi ích bổ sung ở cùng ngân sách/công rà soát. Chi phí fit, score, memory và vận hành là chỉ số chọn model.

## E3. Chỉ số và cách tính

| Chỉ số | Định nghĩa |
|---|---|
| Confirmed cases found | Vụ confirmed_risk được gửi; không đếm nhiều dòng cùng vụ |
| Precision resolved | confirmed_risk/(confirmed_risk+legitimate) trên alert đã kết luận; mẫu số 0 trả null |
| Resolution coverage | Số alert có kết luận xác định / tổng alert gửi; inconclusive và chưa xử lý báo riêng |
| False alerts/company-week | Vụ legitimate gửi / số company-week được quan sát; ghi cách tính DN-tuần thiếu dữ liệu |
| Review effort | Phút thao tác active và thời gian chờ bằng chứng báo riêng |
| Label coverage | Số dòng/vụ có nhãn, nguồn nhãn, lệch chọn mẫu theo từng vùng score |
| Recall/PR-AUC | Chỉ tính khi ground truth phù hợp; không suy recall toàn tập từ nhãn riêng vùng cảnh báo |
| Ops | Fit/score runtime, memory, availability/fallback, queue age, duplicates |

Rà mẫu vùng không cảnh báo: strata theo DN/thời gian/score, xác suất chọn >0 được lưu, người rà kết luận theo cùng định nghĩa. Ước lượng bỏ sót có trọng số theo thiết kế mẫu và khoảng bất định phù hợp; không áp tỷ lệ mẫu trực tiếp cho toàn bộ dữ liệu.

## E4. So phối hợp và chính sách

Bắt đầu phương pháp tốt nhất rồi thêm tín hiệu bổ sung. So một biến đổi mỗi lần khi có thể: detector, trọng số, grouping, policy. Ngưỡng chọn sau khi khóa cách tính điểm vụ. Weighted percentile là điểm ưu tiên; chưa có calibration thì không gọi là xác suất. Calibration có nhãn, data và tập giữ lại riêng; không fit test.

Budget demo B=3 là thử chính sách, không chứng minh 3 là tối ưu. Báo số đủ ngưỡng nhưng deferred, vụ mandatory, task tồn và công việc hồ sơ riêng.

## E5. Artifact bắt buộc

R2: evidence/R2/evaluation_plan.json, detector_benchmark.json, parity_report.json. R6: evidence/R6/comparison_report.json, release_gate.json, rollback_report.json.

EvaluationReport fields: spec_version, plan_id/hash, data/split/label provenance, model/reference/preprocess versions, seed, per_company/per_period metrics, numerator/denominator, unresolved counts, coverage, sample design, uncertainty_method, runtime/memory, baseline_delta, limitations và status (technical_only/insufficient_labels/evaluated). Không báo số chưa đo thành 0.

ReleaseGate: từng gate ID, numeric threshold đã duyệt, observed, pass/fail/blocked, evidence ref, approver. D-09 chưa duyệt hoặc mẫu thiếu thì release BLOCKED; human reviewer mới duyệt DONE/active. Metric benchmark do tool tính trên predictions+labels, lưu hash inputs/script; không chỉ JSON AI tự khai.

## E6. TH1/TH2 về sau

Xem 90_future_TH1_TH2.md: supervised synthetic tách DN/template/time; so Logistic/LightGBM. HE so B0 sigmoid rõ, B1 polynomial rõ, B2 cùng thuật toán mã hóa; tách sai số xấp xỉ với sai số mã hóa. Không đưa HE vào R2/R6 runtime trừ kiểm tra chặn giả năng lực.
