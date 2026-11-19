# Prompt giao Antigravity: Huấn luyện và quản lý mô hình Agent2

Bạn đang làm trong repo Multi-Agent-Finance, workspace `D:\agent22`. Hãy giúp hoàn thiện **Khu vực B – Huấn luyện & quản lý mô hình** cho Agent2, bằng chức năng backend và giao diện chạy được, bám ảnh mẫu đã gửi. Không chỉ dựng các thẻ hoặc số liệu minh họa.

## 1. Ngữ cảnh và giới hạn công việc

- Repo: https://github.com/Khanhhh239/Multi-Agent-Finance. Mốc main đã pull trước đây là `e4127f4`; workspace đang có thay đổi chưa commit, trong đó có mã mới của khu vực A. Phải đọc `git status`, diff, file mới/untracked và hướng dẫn áp dụng trước khi sửa. Không pull/reset/clean đè công việc local, không sửa phần Agent1/3/4.
- Agent2 chạy qua Portal 8800, backend 8766. Dữ liệu và quyền doanh nghiệp do sảnh chung quản lý. Không xây thêm màn hình tải file, sửa dữ liệu nguồn hoặc kiểm tra CSV/XLSX trong khu vực B.
- Khu vực A đã có bản nghiệm thu hàng đợi → điều tra → quan hệ → bằng chứng → lưu kết quả và lịch sử. Giữ chức năng này và API compatibility; đừng viết lại hàng đợi.
- Mã đang tiếp tục thay đổi sau nghiệm thu. Báo cáo 24 test backend, 64 test Portal, 6 tình huống UI chỉ thuộc bản có checksum trong `.runtime/investigation-build-20261119/verification.json`. Không dùng báo cáo cũ để tuyên bố code mới của bạn đã pass.
- Không chứa mật khẩu/token/khóa trong mã, log, prompt hoặc artifact đưa lên Git. Dùng phiên Portal hiện có; không yêu cầu nhập khóa local vào giao diện nghiệp vụ.

## 2. Khảo sát trước khi viết code

Đọc ít nhất các nhóm sau, xác nhận lại file/API thật đang có, không mặc định tên dưới đây là toàn bộ kiến trúc:

| Phần | Điểm bắt đầu |
|---|---|
| Portal và dữ liệu chung | `portal/agent2_intake.py`, `portal/agent2_bridge.py`, `shared/finance_input/`, `agent2/sme_fraud/snapshots.py` |
| Quyền và API | `agent2/sme_fraud/portal_auth.py`, `config_api.py`, `review_server.py`, `workbench.py` |
| Feature đúng thời điểm | `snapshot_features.py`, `rule_snapshot_features.py`, `method_preprocess.py`, `feature_contract.py` |
| Model không nhãn và fit tách biệt | `ml_estimators.py`, `method_adapters.py`, `method_jobs.py`, `method_store.py`, `method_storage.sql` |
| Nguồn/artifact đang dùng | `analysis_resources.py`, các bindings mẫu và `rule_bridge_models.py`; file demo không phải cấu hình production |
| Đánh giá và release | `validation_study.py`, `release_shadow_plan.py`, `pipeline_release.py`, `pipeline_release_store.py`, `pipeline_release_api.py`, các schema tương ứng |
| Luồng HE riêng trước đây | `batch_training_api.py`, `experiments/he_training/`, `experiments/he4/config_manager.py`, `web/batch-training.*`, `web/analysis-settings.*` |
| Khu vực A cần giữ | `investigation.py`, `investigation_api.py`, `web/investigation.*`, `bundle_reviews.py`, `bundle_workspace_api.py`, `docs/INVESTIGATION_WORKFLOW.md` |

API hiện có để khảo sát: `GET /api/v1/ui/context`; các route theo DN `analysis-config` với `draft/fit/activate`; `pipeline-releases` với `prepare/qualify/approve/switch/revoke/diff`; `batch-training`; `pipeline-workspace/.../investigation`. Các path này phải qua prefix/cầu Portal phù hợp. API huấn luyện không giám sát tổng quát mới, nếu thiếu, phải được thiết kế rõ chứ không giả định đã có.

Các estimator không nhãn đã có gồm Isolation Forest, Autoencoder, ECOD, LOF. Autoencoder hiện có dùng bottleneck `MLPRegressor`; tái sử dụng trước khi thêm framework/GPU. `method_jobs.run_fit_job` và `fit_local_reference` là điểm bắt đầu cho fit độc lập; inference không được gọi ngược lại fit.

Lưu ý: giao diện `analysis-settings` cũ đang hướng đến profile kiểm chứng HE4 với RobustZ/Mahalanobis và hai cột. `batch-training` cũ là luồng train có nhãn/mã hóa riêng. Không đổi nhãn trang rồi gọi đó là quản trị IF/AE và 33 feature đã hoàn thiện.

Đầu ra khảo sát cần có: sơ đồ luồng hiện tại, bảng giữ/sửa/bổ sung, API được tái sử dụng, khoảng trống thực tế, kế hoạch theo giai đoạn và tiêu chí nghiệm thu. Hoàn thành phần này trước khi sửa code; sau đó triển khai trong phạm vi đã rõ, chỉ hỏi nếu còn quyết định nghiệp vụ hoặc bảo mật chặn công việc.

## 3. Luồng đích

`Chọn DN có quyền → chọn snapshot đã lưu từ sảnh chung → xem chất lượng và phạm vi nguồn → chia kỳ → chuẩn bị feature → chọn IF/AE → tạo job fit → theo dõi → đánh giá trên tập giữ riêng → đối chiếu ứng viên → phê duyệt chạy thử → nghiệm thu → phát hành qua bundle → theo dõi/hoàn nguyên.`

Mỗi đối tượng phải truy được về tenant/company, snapshot/checksum, job, kỳ dữ liệu, feature/preprocess contract, model artifact, reference/calibration nếu có, báo cáo đánh giá và bundle. Các mã có thể ẩn trong chi tiết kỹ thuật; backend vẫn phải giữ đầy đủ.

## 4. Nguồn và feature

- Chỉ đọc snapshot đã được xác nhận từ sảnh chung; không đọc file ngoài phạm vi DN hoặc tự nối DB khác để bù thiếu nguồn.
- Thống kê số giao dịch, khoảng thời gian, mức thiếu, cột không dùng được, liên kết cần thiết, lượng dữ liệu đủ điều kiện train/reference/eval. Phân biệt tổng nguồn với ứng viên phải rà.
- Với snapshot profile 35 luật, tái sử dụng bridge feature tương ứng; không lấy thẳng schema canonical cũ hoặc model hai feature cho contract 33 feature.
- Không dùng tương lai: kiểm tra event time, thời điểm nguồn được biết và `as_of`. Giao dịch đồng thời phải tuân thủ cách xây lịch sử hiện có. Không lấy master mới nhất để sửa feature quá khứ.
- Tách định danh, nhãn, nội dung bằng chứng và kết quả rà khỏi biến dự báo. ID vẫn dùng để truy vết ngoài ma trận feature.
- Fit imputer/scaler/loại cột/feature selection trên train; đóng băng khi chấm reference/eval/new snapshot. Không biến null thành 0 nếu không có semantics hợp lệ. Không cắt hoặc biến đổi âm hợp lệ để ép vừa miền model/circuit.
- Nếu thiếu nguồn quan hệ, bỏ/đánh dấu thiếu feature quan hệ theo contract và giải thích; không suy ra đồ thị không có cạnh là không có rủi ro.

## 5. Huấn luyện chạy được

- Ưu tiên IF và AE; ECOD/LOF có thể giữ trong phần mở rộng nếu adapter hiện có hỗ trợ. Không cài mô hình mặc định cho mọi DN chỉ từ một bộ demo.
- Có cấu hình rõ theo DN: thuật toán, seed, kỳ, feature set, missing policy, tham số, profile và ngân sách tài nguyên. Tham số nâng cao nằm trong phần mở rộng; mặc định phải được ghi là mặc định kỹ thuật, không phải tối ưu nghiệp vụ đã chứng minh.
- Job fit phải có trạng thái và tiến độ thật: chờ/chạy/thành công/thất bại/gián đoạn. Lưu trên backend, idempotency theo yêu cầu và cấu hình. Reload không mất job; bấm lại không tạo artifact hoặc phiên bản đang dùng trùng.
- Nếu thuật toán không thể tiếp tục optimizer sau crash, báo rõ cần chạy lại job theo cơ chế được kiểm soát; không giả vờ tiếp tục từ checkpoint không có. Artifact dở không được publish.
- Tách artifact bất biến khỏi con trỏ đang sử dụng. Ghi atomic, checksum, manifest, thư viện liên quan, contract, preprocessing, tập reference và nguyên nhân thiếu/loại cột. Chỉ load artifact do hệ thống tin cậy tạo, không nhận pickle/joblib tùy ý từ client.
- Không tự fit trong API chấm hoặc trong thao tác mở hàng đợi/giao dịch/đồ thị.

## 6. Đánh giá không có nhãn

Phải có tập thời gian giữ riêng, không trùng train/reference và không dùng để lựa chọn rồi lại gọi là tập test độc lập.

Khi thiếu nhãn thật, báo cáo được phép gồm: số dòng đủ/chưa đủ điều kiện chấm, phân phối điểm, độ ổn định top-k qua các kỳ/seed, tỷ lệ biến động thứ hạng, cảnh báo theo kịch bản, lỗi hội tụ, latency và tài nguyên được đo thực tế. Reconstruction error hoặc anomaly score không phải accuracy hay xác suất gian lận.

Khi có nhãn đã xác minh: chỉ dùng đúng đối tượng, snapshot, thời điểm và phiên bản; chưa rõ để trống. Chỉ tính precision@k, recall, F1, PR-AUC hoặc metric phù hợp khi điều kiện nhãn/sampling cho phép; báo số mẫu, số dương/âm, độ phủ nhãn, nguồn và giới hạn. Không coi giao dịch chưa được rà là âm, không dùng mã tên tệp signal/control như nhãn nghiệp vụ thật.

So sánh ứng viên trên cùng kỳ, cùng tập đủ điều kiện và cùng ngân sách **tối đa 5 giao dịch/phương án/DN** cho demo đã thống nhất. Phiếu rà hữu ích và phút kiểm tra phải từ lượt rà có ghi nhận; chưa rà thì hiển thị “Chưa đánh giá”, không tự điền 3/5 hoặc 2/5 như ảnh mẫu. Ngân sách cấp vụ của hàng đợi là chính sách riêng, không lấy 5 giao dịch thay thế.

Giữ baseline 35 luật và phương án luật + ML ưu tiên luật, ML bổ sung chỗ trống trong phép thử. Nếu không có chỗ trống, báo không đánh giá được lợi ích bổ sung bằng cách chọn này; không tự tăng tỷ trọng hoặc bỏ cảnh báo luật để tạo kết quả đẹp. Không chứng nhận hiệu quả thật từ dữ liệu mô phỏng.

## 7. Phê duyệt, phát hành, rollback và nối hàng đợi

- Tái sử dụng release store/gate/bundle. Không tạo một con trỏ model riêng trên UI để vượt gate chung.
- Chọn model ứng viên chưa thay model đang chạy. Nút phê duyệt chỉ mở khi job/artifact/đánh giá/contract còn khớp và người dùng có quyền thực tế tại backend.
- Trạng thái UI phải phân biệt: train xong, kỹ thuật đạt, chờ rà nghiệp vụ, được duyệt chạy thử, đang shadow, được phép phát hành, đang dùng, bị thu hồi/thay thế. Train xong không đồng nghĩa được sử dụng.
- Gate kiểm tra quyền, nguồn, kỳ, artifact/checksum, feature/preprocess, đánh giá, policy và lane. Không nhận `passed=true`, metric hoặc artifact tự khai từ client để vượt gate. Không vô hiệu hóa kiểm tra tương thích chỉ vì code vừa thay đổi.
- Approve/switch/rollback cần lý do, actor theo Portal, thời gian, revision/CAS và idempotency. Hai thao tác cạnh tranh không được ghi đè âm thầm. Không khẳng định tách nhiệm vụ hai người nếu Portal chỉ có actor workspace chia sẻ.
- Rollback phải khôi phục bộ tương thích gồm model, feature, preprocessing, reference/calibration, policy/ensemble liên quan. Không chỉ đổi file trọng số. Không sửa lịch sử kết quả hoặc job cũ.
- Khi chấm snapshot mới, dùng model được bundle ghim cho đúng DN. Thiếu/sai contract trả unavailable; không fit ngầm, dùng model DN khác hoặc đổi sang phiên bản mới nhất ngoài pin.
- Kết quả vẫn đi qua phối hợp → gộp vụ → chính sách/ngân sách → hàng đợi. Không đưa trực tiếp danh sách top anomaly vào khu vực A để vượt bước gộp vụ và admission.
- Giải thích điểm phải phân biệt điểm thô, điểm tham chiếu/chuẩn hóa và đóng góp theo cấu hình được duyệt; phần thiếu không tự suy ra 0. Đồ thị bối cảnh không tự tăng điểm. Không trình bày anomaly score là xác suất gian lận nếu chưa có hiệu chuẩn và kiểm chứng phù hợp.

## 8. HE và bảo mật

Yêu cầu trước đây vẫn được giữ: nếu gửi lên cloud thì cloud chỉ tính trên bản mã bằng profile HE thật. Sự tồn tại của estimator local không có nghĩa IF/AE đã có HE. Prototype train mã hóa có nhãn không tự trở thành train không nhãn IF/AE.

Phải ghi rõ từng mode: train/chấm tại node DN; HE được hỗ trợ; HE chưa khả dụng. Không gửi dữ liệu rõ/model/khóa bí mật lên worker để giả lập HE. Không chuyển mode ngầm khi chậm/lỗi. Không đưa khóa vào trình duyệt, không giảm TTL/replay policy hoặc thay khóa/model của job đang lưu.

Mỗi API cần kiểm tra scope DN, quyền model.fit/manager phù hợp, kiểm tra lại quyền trước commit/response và chống truy cập chéo qua job/artifact/report IDs. UI ẩn nút không thay thế kiểm soát server. Log không chứa dữ liệu giao dịch rõ hoặc bí mật không cần thiết.

## 9. Giao diện theo ảnh mẫu

Chỉ hai khu vực chính: **Hàng đợi & điều tra**, **Huấn luyện & mô hình**. Trang B dùng màu đỏ trầm/nền kem của Portal và không tạo thêm sidebar của sảnh chung trong iframe.

Trang B có: model đang dùng; dữ liệu đã lưu từ sảnh chung và chất lượng; thanh 5 bước Chọn dữ liệu → Đặc trưng → Huấn luyện → Đánh giá → Phê duyệt; bảng ứng viên; khung kiểm tra/phê duyệt; lịch sử/hoàn nguyên. Chi tiết kỹ thuật nằm trong phần mở rộng.

Ảnh chỉ là thiết kế. Không hard-code 24.860 giao dịch, v7/v8, 3/5, 0,8 giây hoặc trạng thái đạt. Chưa có dữ liệu phải nói chưa có; metric chưa được đo hiển thị chưa đánh giá. Không thêm upload, quản lý dataset hoặc sửa CSV tại đây. Người không có quyền quản trị không được fit/approve/switch bằng cách gọi API trực tiếp.

Không làm hỏng luồng khu vực A, URL phục hồi công ty/lần chạy, pending request, review lease, evidence, attachment, lịch sử và bộ lọc đã có.

## 10. Giai đoạn và tiêu chí nghiệm thu

1. **Khảo sát/hợp đồng:** có tài liệu hiện trạng, bảng tái sử dụng và thiết kế API/state/manifest; xác nhận luồng Portal snapshot. Chưa sửa thuật toán khi chưa hiểu contract.
2. **Backend local IF/AE:** đọc snapshot thật từ interface, fit job tách biệt, artifact/feature trace và recovery thật. Thử C001/C002 cùng ID giao dịch; lỗi source/model phải giải thích, không lẫn DN.
3. **Đánh giá/phiên bản/gate:** có báo cáo từ job thực, tập giữ riêng, số đo có nguồn; phê duyệt và rollback đầy đủ; không có nhãn thì không tự có accuracy.
4. **Giao diện và nối bundle:** nút thao tác gọi backend thật, reload còn trạng thái; model chưa duyệt không được dùng; chấm snapshot mới có pin và chạy qua cơ chế hàng đợi hiện có.
5. **Nghiệm thu/phát hành local:** backup trước cập nhật; chạy test backend và Playwright qua Portal với kho riêng; chỉ restart đúng tiến trình liên quan khi idle hoặc đã có quy trình khôi phục. Giữ dữ liệu/model/khóa/session phân tích. Không tự push, đổi branch hoặc sửa các agent khác.

Ca kiểm thử bắt buộc: chéo DN; quyền bị thu hồi khi đang thao tác; thay source/mapping/contract sau preview; train/reference/eval trùng hoặc sai thứ tự; chứng từ đến muộn; feature thiếu/all-null; NaN/inf/âm hợp lệ; AE không hội tụ; thiếu model; model sai contract; save/approve/switch bị mất phản hồi; reload; crash fit/job dở; phê duyệt cũ bị stale; hai người/CAS cạnh tranh; rollback đồng bộ; luật-only khi ML unavailable theo policy; HE unsupported phải unavailable; regression toàn khu vực A. Dùng monkeypatch chặn fit để chứng minh API inference không gọi train, nhưng không dùng mock thay estimator/job thật trong phép nghiệm thu model.

## 11. Bàn giao

Trả: tài liệu khảo sát/kiến trúc; danh sách file/API giữ–sửa–thêm; code; migration và recovery nếu có; dữ liệu demo có manifest/quyền; hướng dẫn chạy; kết quả test với lệnh/exit status; báo cáo đánh giá và giới hạn; ảnh giao diện chạy thật; bằng chứng model được bundle ghim khi chấm snapshot mới. Phân biệt rõ đã làm, đã đo và dự kiến. Nếu thiếu dữ liệu nghiệp vụ hoặc quyết định gate thì ghi blocker cụ thể, không giả số liệu hoặc tự phê duyệt để nói đã xong.

Mục tiêu cuối: người quản trị chọn đúng dữ liệu của DN, huấn luyện IF/AE, xem đánh giá có căn cứ, phê duyệt phiên bản và nối được vào luồng phân tích hiện có; kế toán tiếp tục dùng khu vực A, không phải tự cấu hình thuật toán.
