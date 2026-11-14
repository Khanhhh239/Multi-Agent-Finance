# Phụ lục tương lai — không nạp mặc định trong R0–R6

**BẮT BUỘC:** RULE-LABEL-01, RULE-TIME-01, RULE-HE-01 và state contract 04. **CHƯA CHỐT:** các quyết định HE ở D-11/D-12. Phần này mô tả F1–F3; không tự thực hiện khi đang sửa runtime. Nội dung công thức/giao thức cần kiểm chứng backend thật. Các đoạn “đề xuất” là ứng viên benchmark.

## Chốt lại ý nghĩa hai trường hợp huấn luyện

| Nội dung | TH1 — Synthetic có nhãn | TH2 — N DN học chung bằng HE |
|---|---|---|
| Dữ liệu gốc | Sổ giả lập có kịch bản kiểm soát | Sổ và nhãn thật được xác nhận tại từng DN |
| Tạo đặc trưng | Tái chạy feature pipeline sau tiêm ca | Chạy cùng feature contract tại mỗi DN |
| Nhãn y | 1: ca rủi ro theo kịch bản; 0: ca hợp lệ đã biết | 1: rủi ro xác nhận; 0: hợp lệ xác nhận; chưa kết luận không tham gia supervised train |
| Nơi train | Môi trường phát triển được phép | Cloud tính trên ciphertext theo giao thức đã chọn |
| Model | Logistic và LightGBM để benchmark | Logistic dùng sigmoid xấp xỉ; LightGBM gốc không nhận ciphertext trực tiếp |
| Đầu ra train | Artifact model, tiền xử lý, báo cáo | Trọng số model mã hóa, manifest phiên và kết quả kiểm chứng |
| Chuyển vào runtime | Qua validation thật, shadow và release gate | Mở model có kiểm soát, validation tại DN, shadow và release gate |

### Sửa rõ mô tả “bảng xác suất rồi train logistic”

Phân biệt ba đối tượng:

1. **X:** ma trận đặc trưng; một dòng là một giao dịch ở mốc chấm.
2. **y:** nhãn thật theo định nghĩa mục tiêu; không phải điểm do model tự tạo.
3. **p:** đầu ra dự đoán từ trọng số hiện tại; dùng cùng y để tính sai lệch.

Logistic train bằng các vòng: trọng số → z → p → sai lệch p-y → gradient → trọng số mới. Vì vậy cloud thực hiện đủ vòng cập nhật trên ciphertext là **đã train logistic**, không cần thêm một lượt logistic thông thường từ bảng p.

DN không “thêm xác suất để xác nhận” nhãn. Người có thẩm quyền xác nhận tình trạng nghiệp vụ dựa trên bằng chứng. Nếu DN tự tính p trong một giao thức tương tác, đó là một bước tính toán, không phải gán nhãn.

Trong công thức gradient, “bảng so sánh” chính là y. Trong đánh giá, nó là bộ nhãn giữ lại để so với p/điểm vụ. Confusion matrix là kết quả đếm sau khi chọn ngưỡng, không phải dữ liệu thay thế X để train model gốc.



## TH1 — Huấn luyện có giám sát bằng synthetic

### S1. Sinh sổ nền hợp lệ

Sinh DN giả lập đa dạng về quy mô, mùa vụ, NCC, hóa đơn, hợp đồng, hạn thanh toán, nhân viên, hạn mức, lịch sử tài khoản, các lần thanh toán và chứng từ. Giữ hard negatives: chia đợt đúng hợp đồng, đổi tài khoản đã xác minh, ứng trước, hoàn/hủy và chi lớn có căn cứ. Giữ nhất quán định danh và sổ phân bổ.

### S2. Tiêm sự kiện rủi ro

Ví dụ HD78 đã trả đủ bởi T096; thêm T105 thanh toán lần hai. Sửa ledger/event thật của sổ giả lập, không chỉ sửa một cột feature. Lưu injection manifest riêng: DN, scenario family/template, seed, dòng bị thay đổi, nhãn và căn cứ. T096 giữ nhãn hợp lệ nếu bản chất không bị thay đổi.

### S3. Tạo lại đặc trưng theo thời gian

Replay sổ sau tiêm bằng đúng feature pipeline runtime. Các dòng về sau cũng có thể bị thay đổi lịch sử tham chiếu; phải tính lại theo sự kiện. Chạy kiểm tra toàn vẹn nghiệp vụ và nhãn trước export.

### S4. Tách tập chống dấu vết bộ sinh

- Tách DN mô phỏng, nhóm template kịch bản và thời gian; lưu manifest cố định.
- Tạo holdout riêng kiểm tra mẫu kịch bản mới; báo riêng nếu loại rủi ro chưa có trong train.
- Không để bản sao/biến thể gần cùng một nghĩa vụ xuất hiện nhiều tập.
- Fit imputer/scaler/model trên train; validation chọn tham số; calibration/ngưỡng có tập phù hợp riêng; test giữ kín đến khi khóa cấu hình.
- Nếu sinh lại hoặc thay pipeline sau test, ghi phiên bản và tạo kế hoạch đánh giá mới.

### S5. Train và so sánh

Train Logistic và LightGBM trên cùng tập train, target và feature thông tin tương đương. Model có thể có adapter tiền xử lý riêng được version. Ghi class balance, sample/class weights, seed và hyperparameters. Tỷ lệ synthetic không được đọc thành tỷ lệ rủi ro thực tế.

Artifacts: model, preprocess, feature contract, label definition, split manifest, generator version, báo cáo và data provenance. Cả hai là ứng viên; chọn theo chất lượng vụ ở cùng ngân sách, không chỉ accuracy.

### S6. Chuyển miền sang dữ liệu thật

Chạy shadow, không ảnh hưởng cảnh báo active. Dùng nhãn thật đủ chất lượng để đánh giá/cân chỉnh và chọn ngưỡng. Nếu ít nhãn, ghi rõ chưa đủ bằng chứng phát hành. Có thể giữ luật/detector hiện tại làm bản active.



## TH2 — Huấn luyện Logistic trên dữ liệu mã hóa nhiều DN

### Mô hình dữ liệu và mô hình khóa

Thiết kế chính giả định **horizontal partition**: mỗi DN có các dòng giao dịch riêng, cùng cột feature/target. Nếu các DN nắm các cột khác nhau của cùng thực thể, đó là bài toán vertical khác; không áp trực tiếp đặc tả này.

BẮT BUỘC chọn một backend với semantics rõ:

| Phương án | Cách khóa hoạt động | Trạng thái |
|---|---|---|
| True multi-key HE | Mỗi DN mã hóa bằng public key riêng; phép tính liên khóa theo giao thức hỗ trợ; đầu ra phụ thuộc tập khóa | Phù hợp yêu cầu khóa độc lập, nhưng phải có backend chứng minh được |
| Collective/threshold HE | Các bên giữ secret share; dữ liệu mã hóa theo public key chung của phiên | Phương án triển khai khác, chỉ dùng nếu nhóm chấp nhận thay đổi mô hình khóa |

Không cộng ciphertext từ các key/context không tương thích. Không coi tài liệu threshold/multiparty của thư viện là bằng chứng đã có đúng multi-key backend. Không mặc định một DN tự mở được model chung. Không mặc định n-of-n hỗ trợ t-of-n hoặc rút bên giữa phiên.

**CHƯA CHỐT:** thư viện/giao thức true multi-key cụ thể. AI được phép xây interface và plain simulator; phải ghi backend_not_implemented cho HE chưa có, không tự chuyển sang plaintext để báo thành công.

### Hợp đồng phiên trước khi nhận ciphertext

TrainingManifest cần có session_id, participants, protocol/backend version, key_epoch/key identifiers, context fingerprint, schema/feature hash, split policy, label definition, preprocessing, objective, learning rate, regularization, initialization, rounds/batches, participant weighting, polynomial coefficients/domain, packing/layout, crypto parameters, refresh schedule, quyền mở model, điều kiện thiếu bên, tài nguyên dự kiến và acceptance thresholds.

- Secret key/secret share ở DN; public/evaluation key theo giao thức được gửi đúng nơi.
- Chọn bảo mật mục tiêu và thông số qua công cụ/giao thức được kiểm chứng; không tự phát minh tham số.
- Định nghĩa threat model: cloud chỉ tò mò hay có thể sửa dữ liệu; DN nào có thể thông đồng; có xét poisoning không. Cơ chế không chống được phải ghi rõ.
- Key epoch gắn với mọi ciphertext; thêm/bớt DN phải tạo phiên/luồng chuyển khóa được hỗ trợ, không sửa participants giữa phiên tùy ý.

### H1. Chuẩn bị tại DN

Mỗi DN tạo snapshot, FeatureRows và nhãn confirmed; tách train/validation/test theo thời gian/case. Validation/test ở lại DN, không lẫn vào train cloud. Map thứ tự cột và biến đổi số thống nhất. Chỉ giữ dòng train có target đúng định nghĩa.

Log số dòng bị loại/missing/nhãn chưa kết luận. Nếu kiểm tra đầu vào diễn ra ở client không tin cậy, cloud không tự chứng minh tính đúng của ciphertext/nhãn chỉ bằng HE; cần cơ chế riêng nếu threat model yêu cầu.

### H2. Mã hóa và tải lên

Đóng gói X_i, y_i theo layout đã duyệt, mã hóa và tải lên kho phiên. Padding có mask để không tính dòng giả vào gradient. Cloud lưu object ciphertext kèm metadata; không vận hành truy vấn SQL/rule engine trên chúng như bảng rõ.

Cloud không nhận transaction_id thật nếu không cần; mapping row-token về giao dịch giữ ở DN. Bảo vệ nội dung và xác thực kênh truyền; hash/chữ ký dùng để ràng buộc phiên, không thay cho chứng minh phép tính đúng.

### H3. Train trực tiếp trên ciphertext

Với m dòng, d đặc trưng, trọng số w và bias b:

```text
z = X w + b
p_exact = sigmoid(z) = 1 / (1 + exp(-z))
p_approx = q3(z) = a0 + a1*z + a2*z^2 + a3*z^3
residual = p_approx - y
grad_w = X^T residual / m + lambda*w
grad_b = sum(residual) / m
w_next = w - eta*grad_w
b_next = b - eta*grad_b
```

Đây là công thức logic rõ để đối chiếu. Triển khai HE phải xác định ciphertext nào chứa từng đối tượng, các phép rotation, sum, multiply và chuyển khóa tương ứng. Bias không regularize trong baseline này.

- Cộng và nhân là phép tính **trên dữ liệu đã mã hóa**, không phải bản thân cách mã hóa.
- ĐỀ XUẤT xấp xỉ trực tiếp sigmoid; không chỉ thay exp bằng cubic rồi bỏ qua phép nghịch đảo trong sigmoid.
- q3 là đa thức xấp xỉ trên miền hữu hạn [-L,L], không tự bảo đảm giá trị luôn thuộc [0,1]. Gọi là approx_score khi chưa chứng minh miền/range và hiệu chỉnh.
- Không chốt hệ số cubic tùy ý. Lưu miền, thuật toán chọn hệ số, sai số cực đại và kiểm tra gần biên.
- Kiểm soát scale dữ liệu, regularization, learning rate và số vòng để tránh z vượt miền; nếu không kiểm tra z trên ciphertext được, phải nêu giới hạn của chứng minh/kiểm thử rõ. Clip plaintext tại client phải là phần transform đã chốt; clip ciphertext cần giao thức so sánh riêng.
- Chia m công khai là nhân 1/m; m và kích thước batch có thể làm lộ metadata. Nếu yêu cầu giấu m, cần thiết kế khác.
- Có thể chọn trọng số theo số dòng hoặc cân bằng theo DN; phải chốt trước vì đây là hai mục tiêu học khác nhau. Dữ liệu lệch lớp và DN lớn không được âm thầm chi phối.
- Sau mỗi vòng, model/gradient tiếp tục ở ciphertext. Không gửi bảng p rõ về cloud để “train tiếp” theo mặc định.
- Theo dõi chiều sâu nhân, modulus/scale/noise budget và chi phí refresh. Chọn số vòng cố định từ benchmark rõ nếu không có giao thức dừng sớm bảo mật.
- Refresh/bootstrapping phải dùng cơ chế đã định; không giải mã gradient/trạng thái trung gian cho cloud để làm mới.

Kết thúc H3 tạo **encrypted model weights + bias**, không chỉ “một bảng mã hóa” không có semantics. Nếu một backend xuất intermediate p/gradient, artifact phải khai báo chính xác loại và bước sử dụng; không gọi nó là model.

### H4. Mở model được phép

Phiên chính đề xuất mở đúng final model cho các DN được cấp quyền để inference tại chỗ. Các bên đóng góp giải mã/chuyển khóa theo backend; kết quả rõ chỉ tới người nhận được duyệt. Nếu protocol không đáp ứng hạn chế người nhận, không coi yêu cầu đã hoàn thành.

- Ràng buộc request với session, artifact, circuit/job và quyền mở.
- Không xây endpoint giải mã ciphertext bất kỳ. Chỉ signature/hash của cloud chưa chứng minh ciphertext là kết quả phép tính đã duyệt; cần nêu cơ chế xác minh hoặc giả định tin cậy tương ứng.
- Audit, giới hạn số lần mở, xử lý replay và participant dropout.
- Muốn một DN nhận model dưới key riêng cần authorized key switching/recipient protocol; không tự lấy secret key từng bên.
- Model rõ có thể rò thông tin qua suy luận; HE không tự giải quyết model leakage, poisoning hoặc máy DN bị xâm nhập.
- Nếu yêu cầu model luôn mã hóa: thiết kế encrypted inference/decryption riêng; không bật inference rõ trái yêu cầu.

### H5. Xác suất và đánh giá tại DN

Sau khi nhận w,b được phép, DN chấm X nội bộ. Lưu `prediction_link`: polynomial q3 hay exact sigmoid. Đổi từ q3 lúc train sang sigmoid lúc inference là một lựa chọn phải đo riêng, không mặc định tương đương.

Tách ba loại giá trị: model_raw_score, calibrated_probability (chỉ khi hiệu chỉnh/kiểm tra phù hợp), percentile để phối hợp. Không đổi tên q3 chưa kiểm định thành xác suất đáng tin cậy.

DN so dự đoán với nhãn validation/test thật. Chỉ chia sẻ metric tổng hợp được duyệt; không mặc định gửi bảng p theo từng giao dịch. Metric nhóm nhỏ vẫn có nguy cơ lộ thông tin; chốt phạm vi và cơ chế tổng hợp theo threat model.

Model học chung phải so với TH1 và baseline tại DN. Có thể phát hành cho DN đủ điều kiện và giữ model cũ ở DN khác; không bắt buộc mọi DN dùng một threshold/model.

### Nếu nhóm thực sự muốn DN tính p mỗi vòng

Đây là **giao thức tương tác khác**, không phải bước thêm tự do vào H3:

1. Gửi model/intermediate đã định đến các DN theo quyền mở.
2. DN tính p hoặc gradient trên dữ liệu local.
3. DN mã hóa gradient hoặc cập nhật; cloud tổng hợp bảo mật và cập nhật trọng số.
4. Lặp, xác định ai nhìn thấy model mỗi vòng và xử lý DN vắng mặt.

Nếu dữ liệu ở lại DN và chỉ cập nhật được gửi, đây là hướng federated training với secure aggregation/HE, khác thiết kế cloud nhận Enc(X,y). Đặc tả chính chọn H1–H5. Không kết hợp hai giao thức nếu chưa chốt ranh giới tin cậy và đối tượng truyền.



## Kiểm chứng TH2 theo ba baseline

| Baseline | Mục đích |
|---|---|
| B0: Logistic rõ với sigmoid chuẩn | Mốc chất lượng ML tham khảo |
| B1: Logistic rõ dùng đúng q3, init, batch, objective và rounds của HE | Tách ảnh hưởng xấp xỉ thuật toán |
| B2: Logistic HE cùng thuật toán B1 | Đo sai số và chi phí của mã hóa |

Trên synthetic nhỏ có quyền mở trong môi trường test: so B1/B2 ở trọng số, logit, score, thứ hạng và quyết định cảnh báo; báo B0/B1 để thấy tổn thất do xấp xỉ. Không yêu cầu B0 và B2 có trọng số y hệt khi thuật toán khác nhau.

Đo thời gian mã hóa/upload/train/refresh/mở model, bộ nhớ, kích thước ciphertext, số vòng, số DN, số dòng và d. Đặt tolerance/giới hạn tài nguyên trước chạy acceptance; chưa đạt thì giữ trạng thái experimental. Kiểm tra sai context/key epoch, thiếu bên, replay và request mở không được phép.



## Những quyết định nhóm phải chốt cho TH2

- Khóa độc lập true multi-key là bắt buộc hay chấp nhận collective threshold? Backend cụ thể nào đáp ứng?
- Model cuối ai được thấy: mỗi DN, cloud, hay chỉ mô hình mã hóa? Có chấp nhận DN nhìn model mỗi vòng không?
- n-of-n hay t-of-n? Khi bên rời phiên/mất khóa thì xử lý thế nào theo giao thức thực có?
- Threat model và giới hạn thông đồng, giả mạo kết quả tính và poisoning là gì?
- Feature transform chung, weighting theo DN, polynomial/domain, refresh, round budget và mức tài nguyên nào được chấp nhận?
- Validation có đủ nhãn/độ bao phủ không? Metric nào được chia sẻ và ai được nhận?

AI được tiếp tục phần không phụ thuộc các quyết định này. HE thật và active release phải giữ trạng thái blocked/experimental ở chỗ chưa đáp ứng.



## Nguồn nghiên cứu

- MK-HELR: https://doi.org/10.1038/s41598-024-63393-1 . Nguồn tham khảo, chưa chọn làm backend.
- OpenFHE: https://openfhe-development.readthedocs.io/en/latest/ . Cần phân biệt threshold HE và khóa độc lập; xác minh phiên bản khi chọn backend.
