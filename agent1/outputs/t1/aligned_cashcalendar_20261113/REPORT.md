# T1 18 feature: đồng bộ, refit, học tiếp local và T6 — 13/11/2026

## Quyết định dựa trên bằng chứng

Đã hoàn thành một lượt thí nghiệm mới và giữ nguyên artifact/báo cáo cũ. Bản refit được huấn luyện với feature phục vụ đã căn chỉnh, ngân sách Neural 400/600 vòng và validation trọng số riêng. Bản refit không qua audit đã khai báo; giữ global hiện tại cho đường tích hợp nghiên cứu. Global 75/25 hiện tại luôn là điểm xuất phát và đối chứng cho nhánh học tiếp được yêu cầu.

Test mới gồm **4 World, 24 doanh nghiệp, 71 doanh nghiệp/ngày chốt và 3,506 snapshot hóa đơn đủ điều kiện**. Có 46 context đủ cửa sổ để thử thích nghi và 19 context chấp nhận thích nghi bằng audit quá khứ.

Đường phục vụ có kiểm hash/ngày sẵn sàng và allowlist tenant đã được tích hợp. Chưa đặt biến môi trường để thay model của tenant nào. Mặc định Monte Carlo T6 đã đổi thành 1000 đường; SHAP vẫn tối đa 30 hóa đơn. Cổng pilot thật không thay đổi.

Global hiện tại giảm 9.43% cash score so với Workspace và thắng ở 19/24 doanh nghiệp trên cohort này. Học tiếp chỉ giảm thêm 0.23% so với global hiện tại; CI 95% của lợi thế tuyệt đối là [-0.001633; 0.003045], còn chứa 0. Giữ global 75/25 làm điểm xuất phát tổng quát; chỉ xét thích nghi khi validation và audit local chấp nhận. Workspace vẫn là đối chứng tại doanh nghiệp. Không có bằng chứng để mặc định fine-tune cho mọi doanh nghiệp hoặc khẳng định một nhánh thắng mọi khía cạnh.

## Sửa nhãn tất toán theo ngày tiền thực thu

Kiểm tra độc lập phát hiện nhãn Paid cũ có thể tất toán sớm khi thứ tự ngày biết thanh toán khác thứ tự ngày tiền thực thu. Phiên bản này tính lại cumulative cash theo ngày tiền, chỉ sử dụng receipt đã biết trước label_end, và không tính credit note là tiền thu. Feature, mẫu hóa đơn, split, seed, cash amount, ứng viên, ngân sách và ngưỡng chọn giữ nguyên.

`target_contract.json` và từng receipt prepared lưu hash dữ liệu cũ/mới. Toàn bộ model global và nhánh thích nghi bị ảnh hưởng được train/chọn/refit lại trên nhãn sửa. Workspace dùng cơ chế nhãn riêng theo ngày thực thu; bundle cũ được kiểm hash, đối chiếu đầu vào và tái tạo dự báo khớp trước khi dùng lại. Các chỉ số trong báo cáo này đều chấm theo nhãn sửa.

Các World là seed mới được tạo trong session, sau đó dùng lại khi sửa nhãn một cách độc lập với dự báo. Không coi đây là một lần tạo thêm holdout chưa nhìn thấy sau sửa lỗi. Chưa có điểm test tổng hợp được dùng để thay hyperparameter. Lượt trước sửa nhãn giữ nguyên trong `aligned_refit_20261112`, không được dùng thay kết luận của phiên bản này.

| Phần dữ liệu | Snapshot | Ngày Paid thay đổi |
|---|---:|---:|
| train | 78171 | 86 |
| validation | 4034 | 7 |
| weight_validation | 1911 | 6 |
| audit | 1317 | 3 |
| fresh_test | 3506 | 2 |

## Đồng bộ feature và dữ liệu được biết

`ledger_bridge.workspace_data` biểu diễn giảm trừ thành phiên bản công nợ có ngày biết, không thành tiền thu. `ledger_context` là adapter vector hóa cho ledger World giới hạn này; đối chiếu với `workspace_context` thực tế ở đầu/cuối mỗi lịch sử doanh nghiệp và kiểm tra lại đầu vào model tại từng context test. Train, serving và SHAP cùng dùng `landmark_features.prepare_features`, đủ 18 feature và một tọa độ tuần tương lai.

Lịch sử tất toán và giá trị hóa đơn đi theo kế toán Workspace, gồm giá trị claim đã được điều chỉnh khi đã biết. Nhãn đánh giá vẫn là tất toán bằng tiền của claim đủ điều kiện; loại thay đổi claim trong follow-up và tiền trước origin nhưng được biết muộn. Toàn bộ kết luận có điều kiện trên quần thể đủ 91 ngày theo dõi; không áp dụng tự động cho mọi ca điều chỉnh kế toán.

`alignment_audit.json` lưu số hàng/feature thay đổi so với builder cũ. Kiểm thử có giảm trừ, tiền biết muộn, closure không bằng tiền, và bất biến khi bỏ bản ghi tương lai.

## Selection, refit và audit global

1. Fit 16 ứng viên/29 trial trên 8 World train, 76 lịch sử doanh nghiệp, 78.171 snapshot; cùng mẫu tối đa 100.000 risk-row. Survival là ứng viên tùy chọn và đối chứng.
2. Ba World validation gốc chọn cấu hình và ensemble theo lỗi thu tuần/lũy kế chuẩn hóa, độ ổn định, integrated Brier và SHAP. Kết quả trước refit: neural 70%, customer 20%, neural_wide 10%.
3. Refit đúng cấu hình thành viên trên train + validation gốc. Validation gốc trở thành dữ liệu refit; không còn được coi là holdout của artifact refit.
4. Hai World mới chỉ chọn trọng số sau refit, trên origin tháng 7/9/12 năm 2024, nhãn đến 31/03/2025. Trọng số được khóa: neural 30%, customer 40%, neural_wide 30%.
5. Hai World audit độc lập chấm bản đã khóa. Không dùng audit để chỉnh lại trọng số hoặc model. Bốn World test khác chỉ dùng để đo kết quả về sau.

| Audit global | Cash score ↓ | MAE tuần (triệu VND) ↓ | MAE lũy kế (triệu VND) ↓ | Integrated Brier ↓ |
|---|---:|---:|---:|---:|
| old_global | 0.263513 | 269.64 | 469.76 | 0.121955 |
| pre_refit | 0.264830 | 274.11 | 456.66 | 0.121504 |
| refit | 0.265739 | 264.98 | 565.22 | 0.132290 |

Điểm chuẩn hóa và lỗi VND có thể đi khác chiều vì doanh nghiệp được cân bằng theo World/doanh nghiệp/origin và quy mô dư nợ khác nhau. So với global cũ, thay đổi cash score của refit là +0.84%, integrated Brier là +8.47%. Giữ nguyên guard: cash không tăng quá 2%, integrated Brier không tăng quá 2% + 0,0001. Không bỏ guard sau khi thấy kết quả.

Sáu trial Neural mới và lượt refit Neural được ghi riêng trong `neural_convergence.json`/metadata. Cảnh báo 120 vòng của artifact cũ vẫn thuộc artifact cũ; kết quả hội tụ của bản mới không được gán cho bản đang giữ.

## So sánh global và local công bằng

Mọi nhánh dự báo cùng hóa đơn, ngày chốt, tiền còn phải thu, nhãn tương lai 13 tuần và partial-cash override. Global nguyên bản cũng được tính lại feature lịch sử local; chỉ tham số model không đổi.

- Global chọn lại trọng số: chỉ đổi tỷ trọng các thành viên đã học, dựa trên validation local.
- Global học tiếp: tiếp tục Neural từ artifact 75/25; giữ scaler global; Adam learning rate 0,0001; thử 5/20 epoch, replay 30% trọng số từ train World gốc và 70% local; chọn pooling 0/25/50/75/100% bằng validation local. Replay không chứa World test hay doanh nghiệp khác thuộc test.
- Global thích nghi qua audit: chọn nhánh reweight hoặc học tiếp bằng validation; audit quá khứ chỉ chấp nhận nhánh đó hoặc bác về global. Sau đó refit local với epoch/trọng số đã khóa, chỉ trên nhãn đã chín trước ngày dự báo.
- Neural local 18 feature: cùng kiến trúc/cấu hình Neural làm đối chứng; fit scaler và tham số từ đầu bằng lịch sử doanh nghiệp. Giới hạn 400 vòng. Đây là cấu hình lấy từ global để kiểm soát kiến trúc, chưa phải tìm mọi hyperparameter NN local. Khi thiếu cửa sổ thì dùng Workspace, được ghi rõ fallback và chấm thêm tập đủ điều kiện riêng.
- Workspace: giữ learner, pool, validation, audit và refit hiện có. Có điều kiện dùng Neural và fallback riêng. Đây là so sánh pipeline; khác feature, mục tiêu validation, lượng replay và ngân sách tối ưu nên không suy diễn thành ablation nhân quả thuần về pretrain.

Các origin local fit cách ngày test 1001–301 ngày, validation 210/182 ngày, audit 91 ngày. Nhãn fit kết thúc trước validation, nhãn validation kết thúc trước audit, và nhãn audit đã biết trước/ngay ngày test. Không dùng nhãn tương lai của doanh nghiệp để chọn nhánh.

## Test mới

| Nhánh | Cash score ↓ | MAE tuần (triệu VND) ↓ | MAE lũy kế (triệu VND) ↓ | Brier4 ↓ | Brier13 ↓ |
|---|---:|---:|---:|---:|---:|
| Global hiện tại 75/25 | 0.318059 | 210.99 | 511.05 | 0.172800 | 0.155220 |
| Ứng viên refit | 0.322246 | 212.91 | 539.05 | 0.185405 | 0.168313 |
| Global chọn lại trọng số local | 0.322479 | 214.47 | 521.82 | 0.176262 | 0.157820 |
| Global học tiếp Neural + pooling local | 0.317323 | 211.00 | 514.35 | 0.171843 | 0.156235 |
| Global thích nghi qua audit local | 0.317670 | 211.12 | 503.22 | 0.172108 | 0.155957 |
| Neural local 18 feature + fallback Workspace | 0.358916 | 238.21 | 662.58 | 0.250434 | 0.206330 |
| Workspace local hiện tại | 0.351173 | 234.18 | 523.22 | 0.217291 | 0.181090 |

| So sánh | Δ lỗi, dương có lợi cho nhánh mới | CI 95% | Doanh nghiệp cải thiện |
|---|---:|---|---:|
| global_finetuned_vs_old_global | 0.000736 | [-0.001633; 0.003045] | 9/24 |
| global_adapted_audited_vs_old_global | 0.000389 | [-0.001220; 0.001902] | 6/24 |
| global_finetuned_vs_local_neural18 | 0.041592 | [0.025791; 0.057100] | 20/24 |
| global_adapted_audited_vs_workspace | 0.033504 | [0.016967; 0.050635] | 19/24 |

Bootstrap lấy lại mẫu doanh nghiệp trong từng World cố định, giữ các origin cùng doanh nghiệp; không phải khoảng tin cậy cho mọi doanh nghiệp Việt Nam. CI chứa 0 thì chưa đủ kết luận thắng chắc.

Trong 46 context đủ dữ liệu để thích nghi, cash score global=0.271375, học tiếp=0.269218, qua audit=0.269791, Neural local 18=0.309893, Workspace=0.296267. `eligible_local_results.json` tránh trộn lợi ích pretrain với fallback của doanh nghiệp thiếu lịch sử.

Ba World test có lịch sử dài, gồm baseline/credit/supply shock. World onboarding mới có dữ liệu từ 01/01/2025, chấm sau khoảng 3/6/9 tháng. `fresh_by_world.csv`, `fresh_by_firm_origin.csv`, `fresh_slices.csv` giữ ngoại lệ theo World, doanh nghiệp, thời gian, trả từng phần, khách mới/ít lịch sử và nợ quá hạn 90 ngày. Không kết luận một model thắng mọi phân nhóm.

## T6, SHAP và ngân sách tính toán

| Đường mô phỏng | Giới hạn SHAP | Số lần đo | Trung vị forecast (giây) |
|---:|---:|---:|---:|
| 400 | 30 | 12 | 5.244 |
| 1000 | 10 | 12 | 3.662 |
| 1000 | 30 | 12 | 5.838 |

Đo trên doanh nghiệp có danh mục mở lớn nhất tại origin cuối của mỗi World test, warmup rồi xoay thứ tự ba cấu hình, ba lần mỗi cấu hình/context. `compute_budget_runs.csv` giữ từng lần đo; trung vị này không phải p95 SLA.

Tất cả hóa đơn hợp lệ đều vào T6; danh sách vẫn tối đa 30 dòng. `shap_limit=10` chỉ giải thích 10 dòng, các dòng còn lại ghi deferred. Dự thu kỳ vọng và thứ tự danh sách không đổi khi đổi Monte Carlo/SHAP. SHAP giải thích xác suất tất toán 4 tuần; tiền và số dư 13 tuần có cash decomposition riêng.

`runtime_shap.json` chấm từng model và Workspace bằng lời giải thích thực, không ước thời gian từ số feature. `runtime_verification.json` kiểm toàn bộ incoming với phân phối model + partial profile, SHAP cộng đúng và bất biến khi bỏ dữ liệu tương lai. Đo MC nhiều seed với mốc 10.000 đường nằm trong `monte_carlo_precision.csv`; đây là độ ổn định số, chưa phải hiệu chỉnh dải tiền theo thực tế.

Kết quả tích hợp nghiên cứu được chấp nhận: **True**. Artifact phục vụ explicit: `serving_artifact`; refit được chấp nhận: **False**. Không tự đặt cấu hình dịch vụ hoặc kích hoạt doanh nghiệp. Các plan smoke có số dư đầu 0, chỉ phạm vi AR, không chứng minh độ chính xác số dư ngân hàng đầy đủ.

### Danh mục lớn — kiểm tra tải kỹ thuật

Đã tạo fixture 1136 hóa đơn mở/18184 hóa đơn lịch sử, vượt ngưỡng census 512. Ledger được nhân bản với ID khách/hóa đơn riêng và hệ số tiền nguyên để giữ quan hệ thu/claim; đây là kiểm tra tải, không phải dữ liệu đánh giá độ chính xác mới. SHAP p95 một hóa đơn: 0.320 giây; policy tham chiếu và từng lần chạy nằm trong `large_book_runtime.json`.

| Đường mô phỏng | Giới hạn SHAP | Trung vị forecast (giây) |
|---:|---:|---:|
| 400 | 30 | 14.297 |
| 1000 | 30 | 13.632 |
| 1000 | 10 | 11.496 |

## Bằng chứng và giới hạn

- `protocol.json`, `fresh_world_design.json`, `onboarding_design.json`: split, seed, budget và vai trò dữ liệu.
- `comparison_amendment.json`: sửa nhánh học tiếp để dùng đúng global hiện tại, giữ lượt chạy bị ngắt và ghi sự cố ghi protocol đồng thời; không dùng điểm test tổng hợp để chỉnh model. `protocol_before_onboarding.json` giữ thiết kế trước khi thêm World thiếu lịch sử.
- `frozen.json`, `post_refit_weight_selection.json`, `audit_results.json`: lựa chọn global và gate không đạt.
- `verification.json`: kiểm độc lập điểm cash, khối lượng xác suất, hash dữ liệu/model và tái tạo global.
- Các kết quả là synthetic cùng họ simulator, dùng giả định fallback khi thiếu raw WDI/OxCGRT; không có dữ liệu doanh nghiệp thật để xác nhận khả năng tổng quát ngoài simulator.
- Kết quả fine-tune chỉ cho phương pháp/ngân sách đã thử. Không khẳng định mọi hình thức học tiếp đều tốt hơn hoặc kém hơn; không dùng test để tiếp tục tìm epoch/trọng số.
- Nếu muốn cải thiện thêm bản refit, cần một lượt nghiên cứu khai báo mới, lựa chọn đồng thời chất lượng xác suất và tiền trên validation, rồi audit mới. Không sửa bản đã khóa để qua audit cũ.

Mã chạy lại: `refit_landmark.py --phase prepare/train/audit`, `compare_adaptation.py --prepare/--world/--summarize`, `verify_refit_comparison.py`, `verify_refit_runtime.py`. Các file cache chỉ được tiếp tục khi protocol/source/model hash tương thích.

## Kiểm thử mã

115 kiểm thử Python và 28 kiểm thử giao diện đã qua; `git diff --check` không có lỗi. Các cảnh báo MLP trong fixture dùng 2/30 vòng và cảnh báo Starlette được giữ trong ghi chú, tách khỏi các trial Neural nghiên cứu đã hội tụ.
