# BIỂU MẪU THU THẬP THÔNG TIN AGENT

**Dự án:** Multi-Agent System – AI Quantum Challenge 2026

**Agent:** Agent2 – Hệ thống hỗ trợ phát hiện và điều tra gian lận tài chính

**Ngày cập nhật:** 19/11/2026

**Phiên bản đối chiếu:** [ebadc6b – mã nguồn đã đẩy lên nhánh main](https://github.com/Khanhhh239/Multi-Agent-Finance/commit/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16).

**Cách đọc báo cáo:** “Đã thực hiện” là chức năng đã có và có bằng chứng chạy trong phạm vi nêu rõ. “Đã đo” là số liệu của một phép thử cụ thể. “Dự kiến/chưa nghiệm thu” là phần chưa có đủ bằng chứng hoàn thành. Dữ liệu minh chứng hiện là dữ liệu mô phỏng; kết quả kiểm thử kỹ thuật chưa chứng minh độ chính xác phát hiện gian lận tại doanh nghiệp thật.

Bản này thay thế nội dung biểu mẫu cũ khi mô tả hiện trạng. Giữ nguyên các báo cáo cũ để đối chiếu lịch sử. Hai tệp bằng chứng của mốc trên nằm tại [verification.json](evidence/release_ebadc6b/verification.json) và [browser-report.json](evidence/release_ebadc6b/browser-report.json), được bổ sung vào repository cùng báo cáo này.

**Bổ sung sau mốc ebadc6b:** có chỉnh hiển thị nguồn điểm, trọng số và phần đóng góp theo kết quả đã lưu, đồng thời rút gọn thuật ngữ trên giao diện. Lượt kiểm tra riêng cho thay đổi này đạt **11 test backend và 7 kiểm tra trình duyệt**; xem [bằng chứng cập nhật](evidence/followup_20261119/verification.json). Không cộng hai lượt kiểm thử để công bố tổng test riêng biệt, và không coi lượt này là nghiệm thu native TFHE hoặc độ chính xác gian lận.

## A. Bài toán nghiệp vụ

**1. Tên Agent:** Agent2 – Hệ thống hỗ trợ phát hiện và điều tra gian lận tài chính. Tên hiển thị trong hệ thống có thể là **Trợ lý Giám sát** hoặc **Agent2 – Giám sát**.

**2. Đối tượng sử dụng:** kế toán, kiểm soát nội bộ, người điều tra/rà soát giao dịch và người phụ trách xử lý sai lệch. Khu vực huấn luyện, đánh giá và phê duyệt mô hình dành cho người có quyền quản trị mô hình của doanh nghiệp.

**3. Vấn đề thực tiễn Agent giải quyết:** hỗ trợ chọn giao dịch cần kiểm tra trước trong một tập giao dịch lớn; chỉ ra dấu hiệu cần làm rõ; kết nối giao dịch với hóa đơn, nhân viên, người phê duyệt, nhà cung cấp và tài khoản ngân hàng; lưu chứng từ, kết quả và lịch sử rà soát trong cùng hồ sơ.

**4. Nguyên nhân và tác động của vấn đề:** dữ liệu kế toán thường nằm ở nhiều bảng; thông tin đối tượng thay đổi theo thời gian; nguồn lịch sử hoặc chứng từ có thể thiếu; người rà chỉ có một lượng thời gian nhất định. Việc kiểm tra rời rạc có thể gây bỏ sót liên kết, rà trùng hoặc mất thời gian tìm căn cứ. **Chưa có khảo sát định lượng tại doanh nghiệp thật** để công bố mức tổn thất, tỷ lệ bỏ sót hoặc số giờ tiết kiệm. Dự án minh họa các vấn đề bằng [các kịch bản nguồn 35 luật](../examples/full_rules/README.md), không dùng kịch bản mô phỏng làm số liệu tổn thất thực tế.

**5. Mục tiêu và yêu cầu nghiệp vụ:**

- Sử dụng dữ liệu từ sảnh chung, theo đúng quyền và phạm vi doanh nghiệp.
- Ưu tiên kiểm tra theo điểm và chính sách của đúng lần phân tích; giải thích được nguồn điểm và phần chưa đủ dữ liệu.
- Cho phép xem quan hệ, giao dịch liên quan, chứng từ và lịch sử thao tác.
- Lưu kết luận có căn cứ; không tự coi điểm cao hoặc mối liên hệ là bằng chứng gian lận.
- Huấn luyện tách khỏi chấm điểm; mô hình theo doanh nghiệp phải được đánh giá, phê duyệt và có khả năng hoàn nguyên.

**6. Kết quả kỳ vọng:** một quy trình thống nhất **Hàng đợi ưu tiên → Chọn giao dịch → Phân tích quan hệ → Đối chiếu bằng chứng → Ghi nhận kết luận**. Mục tiêu hiệu quả là tìm thêm giao dịch đáng xử lý trong cùng ngân sách rà, giảm cảnh báo trùng và giảm thời gian tìm hồ sơ. Các lợi ích này cần được đo bằng thử nghiệm nghiệp vụ độc lập; chưa công bố mức cải thiện thực tế.

## B. Dữ liệu

**1. Nguồn dữ liệu, đường dẫn và quyền sử dụng:**

- Nguồn vận hành dự kiến/đang tích hợp là dữ liệu được nhập tại sảnh chung của Portal: giao dịch, doanh nghiệp, nhà cung cấp/khách hàng, hóa đơn, phân bổ thanh toán, nhân viên/phê duyệt, chứng từ và lịch sử liên quan.
- Dữ liệu đi qua [cầu tiếp nhận Agent2](../../portal/agent2_intake.py), [hợp đồng dữ liệu dùng chung](../../shared/finance_input) và kho snapshot có phạm vi doanh nghiệp. Backend kiểm tra quyền, không tin riêng mã doanh nghiệp trình duyệt gửi lên.
- Nguồn demo có thể kiểm tra trong [full_rules](../examples/full_rules/README.md) và [rule_bridge_models](../examples/rule_bridge_models/README.md).
- Cấu hình local, database chạy, model và khóa nằm ngoài phạm vi công khai. **Chưa có hồ sơ cấp quyền sử dụng dữ liệu thật để công bố nghiệm thu thực tế.** Bộ dữ liệu tự sinh phục vụ phát triển/demo; quyền phân phối mã nguồn hoặc tài liệu phải theo giấy phép/thỏa thuận của repository, không suy ra từ việc xem được trên GitHub.

**2. Quy mô dữ liệu – các bộ minh họa đã tài liệu hóa:**

| Bộ dữ liệu | Quy mô và kỳ dữ liệu | Ý nghĩa |
|---|---|---|
| ML bridge C001 | 45 giao dịch nguồn: 32 lịch sử train, 8 reference, 5 ứng viên ngày 01–05/08/2025 | Một bộ demo của một doanh nghiệp |
| ML bridge C002 | Cùng cấu trúc 45 giao dịch; nguồn khóa tại 06/08/2025 00:00 UTC+07 | Không phải dữ liệu thật của doanh nghiệp thứ hai |
| Full-rules C001/C002 | Gói 120 tệp nguồn JSON theo kịch bản | 120 tệp không đồng nghĩa 120 giao dịch hoặc mỗi tệp đủ cả 35 luật |

Các định dạng nguồn được hỗ trợ qua các đường tiếp nhận gồm CSV, XLSX và JSON theo hợp đồng. Không phải mọi tệp CSV có thể chạy đủ mọi luật. [Bằng chứng quy mô ML](../examples/rule_bridge_models/README.md), [bằng chứng gói luật](../examples/full_rules/README.md).

**3. Dữ liệu thật, công khai, tổng hợp hay giả lập:** dữ liệu dùng cho các kết quả kỹ thuật trong báo cáo là **mô phỏng/tổng hợp theo kịch bản**. C001/C002 là mã doanh nghiệp demo. Chứng từ demo và nhãn kịch bản không phải chứng từ gốc hoặc kết luận gian lận đã được doanh nghiệp thật xác minh.

**4. Cách làm sạch, chuẩn hóa và xử lý:** kiểm tra quyền, cột bắt buộc, kiểu dữ liệu, mã trùng, liên kết và thời điểm nguồn; chuẩn hóa theo hợp đồng; xác nhận lưu thành snapshot có checksum. Giữ số âm của khoản điều chỉnh hợp lệ. Khi tạo đặc trưng, chỉ dùng thông tin đã biết tại thời điểm cho phép; thiếu nguồn phải có trạng thái/lý do thiếu. Bộ xử lý thiếu và scaler được fit trên tập train, lưu cùng model và sử dụng lại khi chấm.

**5. Chất lượng dữ liệu trước và sau xử lý:** đã có kiểm tra/từ chối lỗi và báo giới hạn nguồn. Chưa có bảng đo trước–sau trên dữ liệu thật về tỷ lệ thiếu, mã trùng hoặc sai liên kết. Trong demo bridge, hợp đồng có **33 cột đặc trưng**, trong đó **8 cột chưa có cấu trúc nguồn phù hợp vẫn null**; bộ tiền xử lý loại các cột toàn thiếu theo train và xử lý phần thiếu theo cấu hình đã lưu. Không coi null là bằng chứng giá trị bằng 0. [Mô tả nguồn và giới hạn](../examples/rule_bridge_models/README.md).

**6. Chia dữ liệu và phòng tránh rò rỉ:** tách lịch sử huấn luyện, tập tham chiếu/validation và kỳ đánh giá; kiểm tra theo `as_of` và thời điểm nguồn được biết. Các giao dịch đồng thời cùng nhìn lịch sử trước nhóm. Fit scaler, xử lý thiếu và chọn đặc trưng chỉ trên train. Giữ mã định danh, nhãn và bằng chứng ngoài biến dự báo. Không tự coi giao dịch chưa rà là nhãn 0. Cần duy trì một tập nghiệm thu độc lập khi chọn mô hình và cấu hình; việc có dữ liệu kịch bản chưa thay thế được yêu cầu này.

## C. Thuật toán và công nghệ

**1. Mô hình AI/thuật toán sử dụng:**

| Thành phần | Hiện trạng có thể xác nhận | Giới hạn |
|---|---|---|
| Luật nghiệp vụ | Catalog 35 luật thuộc A/B/C/D/E/F/P/T, có adapter theo nguồn snapshot | Đủ catalog không có nghĩa đủ nguồn cho mọi luật trên mọi snapshot |
| Thống kê | Benford, MAD/RobustZ và các phép so với lịch sử/nhóm phù hợp | Cần nguồn và cỡ mẫu phù hợp; không phải mọi giao dịch có đủ điều kiện |
| Quan hệ | Dựng đồ thị định danh/đối tượng; giao diện có mở rộng nút, đọc cạnh và nguồn | Liên kết là căn cứ điều tra, không tự xác nhận thông đồng/gian lận |
| ML không nhãn | Isolation Forest, ECOD, LOF, Autoencoder trong backend; luồng IF/AE trên giao diện quản lý được thử end-to-end | Chưa chứng minh model tốt nhất hoặc hiệu quả trên dữ liệu thật |
| ML có nhãn | Có prototype Logistic Regression, adapter suy luận và kho quản lý phiên bản | Cần chuẩn hóa ý nghĩa nhãn và nghiệm thu độc lập trước sử dụng nghiệp vụ |
| Mã hóa đồng cấu – HE | Có các profile/worker và prototype chấm/train mã hóa riêng; lượt mới có kiểm tra tính tương đương CKKS cục bộ | Chưa nghiệm thu toàn pipeline, 35 luật, IF/AE/ECOD/LOF và 33 feature cùng chạy HE |

Nền tảng gồm Python, NumPy/SciPy, scikit-learn, NetworkX, SQLite, HTML/CSS/JavaScript và Portal; các nhánh mã hóa dùng thư viện/môi trường riêng. [Estimator](../sme_fraud/ml_estimators.py), [quản lý model](../sme_fraud/model_lifecycle.py), [suy luận LR](../sme_fraud/lr_inference.py), [train LR](../sme_fraud/lr_fhe_training.py).

**2. Lý do lựa chọn:** luật biểu diễn kiểm soát và căn cứ nghiệp vụ; thống kê/ML không nhãn tìm khác thường khi chưa có đủ nhãn tin cậy; đồ thị giúp phát hiện và giải thích liên kết. Isolation Forest có cơ chế cô lập điểm khác thường; Autoencoder đo sai số tái tạo. LR là prototype có giám sát và có thể nghiên cứu trên các circuit giới hạn. Việc triển khai một thuật toán chưa chứng minh thuật toán đó phù hợp nhất cho mọi doanh nghiệp.

**3. Pipeline các bước xử lý:**

**Phân tích:** Sảnh chung → dữ liệu chuẩn hóa → snapshot bất biến → feature đúng thời điểm → các nhánh khả dụng → phối hợp theo cấu hình/bundle → gộp vụ → xét chính sách và ngân sách cấp vụ → hàng đợi → điều tra/chứng từ → kết quả rà và lịch sử.

**Huấn luyện:** chọn snapshot từ sảnh chung → xem chất lượng và kỳ dữ liệu → chuẩn bị feature → fit model theo doanh nghiệp → đánh giá trên tập tách riêng → lưu phiên bản/model/config → người có quyền xác nhận → chạy thử hoặc sử dụng theo quyền/gate → theo dõi, hoàn nguyên khi cần.

Hai luồng đã có các thành phần và lượt chạy kỹ thuật. Kết nối với cloud mã hóa chỉ được công bố theo đúng profile đã nghiệm thu; không xem luồng train cục bộ là train HE. [Bằng chứng 8 bước kiểm tra giao diện](evidence/release_ebadc6b/browser-report.json).

**4. Các tham số, cấu hình chính:**

- Doanh nghiệp/tenant, snapshot/checksum, `as_of`, kỳ train/validation/đánh giá, contract và phiên bản feature, xử lý thiếu, model artifact và bundle.
- Mặc định estimator hiện có: `random_state=42`; IF `n_estimators=100`, `max_samples=min(2048, n_train)`; LOF có `novelty=True`, số láng giềng tối đa 20 và nhỏ hơn số mẫu; AE dùng `MLPRegressor` bottleneck, `tanh`, `max_iter=200`. Đây là mặc định mã nguồn, cấu hình thực dùng phải đối chiếu artifact. [Nguồn tham số](../sme_fraud/ml_estimators.py).
- Ngưỡng, tỷ trọng các nguồn điểm, điều kiện bắt buộc và ngân sách phải gắn cấu hình đã chọn/phê duyệt; không có bằng chứng để đặt một tỷ lệ luật/ML tối ưu chung.
- Phép so sánh nghiệp vụ đã thống nhất: **tối đa 5 giao dịch/phương án/doanh nghiệp**, ưu tiên luật rồi ML bổ sung chỗ trống. Ngân sách tiếp nhận **vụ** được cấu hình riêng; không đồng nhất 5 giao dịch với 5 vụ.

**5. Giả định và điều kiện hoạt động:** có dữ liệu được cấp quyền, định danh và thời gian đủ tin cậy; nguồn lịch sử được khai rõ; model khớp doanh nghiệp, feature và bộ tiền xử lý; có người có chuyên môn đối chiếu. Nguồn/model thiếu phải trả trạng thái chưa khả dụng; chấm điểm không tự fit. Với cloud, nhánh chưa có HE không được tự chuyển sang xử lý dữ liệu rõ. Điểm không mặc định là xác suất gian lận.

**6. Input và Output – ba ví dụ:**

| Tình huống | Input minh họa | Output/diễn giải |
|---|---|---|
| NCC liên quan nhân viên | Nguồn `C001_B1_signal.json` có định danh/tài khoản liên quan | Tín hiệu B1 và liên kết kèm nguồn; người rà mở đồ thị, đối chiếu hồ sơ/ủy quyền. Chưa kết luận gian lận |
| Thiếu lịch sử | Nguồn `C001_coverage_unknown.json` chưa xác nhận phạm vi lịch sử | Luật cần phần lịch sử đó báo `unavailable` và lý do; không trả thành “không vi phạm” |
| Train và đổi phiên bản | Snapshot mô phỏng, model IF đang ghim; tạo ứng viên AE, đánh giá và duyệt | Test giao diện tạo C001-v2, chấm vào hàng đợi có truy vết, rồi rollback về IF C001-v1. Các mã v1/v2 là phiên bản trong kho test tạm |

Hai ví dụ đầu là kịch bản nguồn, không phải nhãn gian lận thật. [Nguồn demo](../examples/full_rules/README.md), [bằng chứng luồng model](evidence/release_ebadc6b/browser-report.json).

**7. Cách tương tác với Agent khác:** Agent2 dùng phiên đăng nhập, quyền doanh nghiệp và dữ liệu nguồn từ Portal; truy cập qua interface/API có kiểm quyền. Portal điều phối các phân hệ. Chưa có bằng chứng trong lượt nghiệm thu này về một chu trình tự động hoàn chỉnh để Agent1/3/4 tiếp nhận kết luận Agent2 và tự hành động; không công bố tính năng đó là đã hoàn thành. [Cầu Portal](../../portal/agent2_bridge.py).

## D. Prototype và kiểm thử

**1. Chức năng đã hoàn thành trong phạm vi prototype đã thử:**

- **Khu vực A:** hàng đợi giao dịch từ kết quả đã lưu; lọc/tìm kiếm và trạng thái; giải thích điểm; mở điều tra; đồ thị có mở rộng nút và căn cứ cạnh; giao dịch liên quan, bản ghi nguồn; bắt đầu/khôi phục phiên rà; đính kèm và tải bằng chứng; ghi kết quả, lịch sử, chống lưu trùng.
- **Khu vực B:** đọc dữ liệu chia sẻ, xem chất lượng/33 feature và phần thiếu; train ứng viên không nhãn; đánh giá; lưu phiên bản; yêu cầu xác nhận/lý do phê duyệt; kết nối bản được duyệt vào hàng đợi; hoàn nguyên phiên bản trước. Test trình duyệt đã chạy từ IF ghim sẵn sang ứng viên AE và rollback.
- **Backend/tích hợp:** quyền doanh nghiệp và quyền model; kiểm tra artifact/contract; các adapter LR, registry và thành phần thử nghiệm HE có mã nguồn/test theo phạm vi.

[Kiểm thử hiện tại](evidence/release_ebadc6b/verification.json), [kịch bản giao diện](evidence/release_ebadc6b/browser-report.json), [nguồn commit](https://github.com/Khanhhh239/Multi-Agent-Finance/tree/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2).

**2. Chức năng chưa hoàn thành/chưa đủ bằng chứng nghiệm thu:** độ chính xác gian lận trên nguồn thật; lợi ích tăng thêm của ML trên baseline 35 luật; toàn pipeline chạy cloud hoàn toàn trên bản mã; toàn catalog luật/model/33 feature được HE hỗ trợ; triển khai production và tải đồng thời; xác minh danh tính từng người trong workspace chia sẻ; cài mới tái lập trên máy sạch. Ba ca native Concrete/worker nêu dưới đây không chạy lại trong lượt trước push, không suy ra chúng đã đạt ở phiên bản này.

**3. Kịch bản demo từng bước:**

1. Trên máy đã cấu hình, mở Portal `http://127.0.0.1:8800`, đăng nhập và chọn doanh nghiệp được cấp quyền.
2. Chuẩn bị dữ liệu qua sảnh chung; chọn snapshot/lần phân tích hợp lệ. Máy mới phải có cấu hình, model/bundle và nguồn phù hợp trước khi chạy; không bỏ qua gate để tạo demo.
3. Vào Agent2 → **Hàng đợi & điều tra** → chọn nguồn kết quả → chọn giao dịch → đọc lý do → **Mở điều tra**.
4. Chọn nút để mở rộng đồ thị, chọn cạnh để xem căn cứ; xem giao dịch liên quan và chứng từ. Giữ rõ dữ liệu mô phỏng/chứng từ chưa xác minh.
5. Bắt đầu rà → đính kèm tài liệu demo → ghi giải thích, căn cứ và hành động → lưu → tải lại để xem trạng thái/lịch sử. Thiếu nguồn thì chọn **Chưa đủ căn cứ**.
6. Với quyền quản trị model, vào **Huấn luyện & mô hình** → chọn dữ liệu → xem chất lượng/feature → train ứng viên IF hoặc AE → xem đánh giá → xác nhận và nhập lý do → duyệt chạy thử.
7. Xem kết quả hàng đợi có dấu vết phiên bản; thử hoàn nguyên về bản trước. Lặp kiểm tra phạm vi với C002, xác nhận không đọc được dữ liệu ngoài quyền.

**4. Số lượng và loại test đã chạy trước khi push `ebadc6b`:**

| Phạm vi | Kết quả | Cách hiểu |
|---|---|---|
| Bộ backend Agent2 được chọn | Lượt đầu: **97 đạt, 2 lỗi, 3 loại khỏi lượt chạy**, 17 subtest đạt | Không phải toàn bộ test repository |
| Hai ca chạy lại có mục tiêu | **2/2 đạt** | CKKS chạy lại bằng venv Agent2 có TenSEAL; test Portal batch cập nhật hai tiêu đề cũ |
| Tổng ca riêng biệt đã đạt sau xử lý/chạy lại | **99**, cùng 17 subtest từ bộ đầu | Không phải một lần chạy đầy đủ mới đạt 99/99; không cộng hai lần CKKS thành hai test khác nhau |
| Portal: 3 module hồi quy liên quan | **81 test, 3 subtest đạt** | Quyền, dashboard/intake và tiếp nhận ngân hàng |
| Trình duyệt trọn luồng hai khu vực | **8 bước kiểm tra đạt**, danh sách lỗi JavaScript ghi nhận rỗng | Kho tạm, dữ liệu mô phỏng, có train AE tại doanh nghiệp; không phải native TFHE |
| Hồi quy riêng sau sửa giải thích điểm | **11 test backend và 7 kiểm tra trình duyệt đạt** | Ghi nhận riêng tại [followup_20261119](evidence/followup_20261119/verification.json); không cộng với bộ trước để suy ra tổng test riêng biệt |

Ba ca không chạy lại: vòng đời worker Linux; Concrete FHE end-to-end/checkpoint; huấn luyện chung hai doanh nghiệp trên worker Concrete thật. Tên test đầy đủ, thời gian và dấu vết nguồn có trong [verification.json](evidence/release_ebadc6b/verification.json). Không cộng các số test cũ để công bố tổng kiểm thử phiên bản mới.

**5. Metric đánh giá và kết quả đo được:**

| Nhóm metric | Kết quả hiện có | Giới hạn |
|---|---|---|
| Hoạt động chức năng | Các kết quả test ở D.4; luồng train–duyệt–chấm–rollback chạy trong browser test | Không đo độ chính xác gian lận |
| Thời gian kiểm thử | Bộ Agent2 đầu: 447,37 giây; Portal: 10,09 giây; ca CKKS chạy lại xác nhận exit 0: 20,708 giây | Đây là thời gian **test**, không phải latency xử lý một giao dịch |
| Phát hiện gian lận: precision/recall/F1/PR-AUC | Chưa có số đo trên tập thật đủ tin cậy để công bố | Các metric tính được từ test/kịch bản chỉ kiểm chứng cách tính và luồng |
| Lợi ích nghiệp vụ | Chưa đo đủ số giao dịch hữu ích tìm thêm, phút rà hoặc chi phí tiết kiệm | Cần rà độc lập trên cùng kỳ/ngân sách |
| HE | Ca tương đương CKKS cục bộ đạt | Không chứng nhận native TFHE training, cloud LR hoặc toàn pipeline HE |

Các số đồ thị/queue trong [lượt nghiệm thu local trước](evidence/investigation_20261119/live-acceptance.json) chỉ có giá trị lịch sử, không được đổi thành recall, hiệu quả hoặc số liệu của lần chạy mới.

**6. Baseline và kết quả so sánh:** baseline dự kiến nghiệm thu là **35 luật** so với **35 luật + ML**, cùng snapshot, kỳ đánh giá và tối đa **5 giao dịch/phương án/doanh nghiệp**. Giữ cách chọn đã thống nhất: ưu tiên cảnh báo luật, ML bổ sung chỗ trống. Đo số giao dịch được xác minh hữu ích, phần hữu ích tìm thêm/bị thay mất, cảnh báo không hữu ích và thời gian rà. **Chưa có kết quả nghiệp vụ đủ căn cứ để công bố ML cải thiện bao nhiêu phần trăm.** Khi luật đã chiếm đủ 5 chỗ, phương án bổ sung chỗ trống có thể không thay đổi danh sách; cần ghi nhận trung thực điều đó.

**7. Ví dụ chạy thành công:** browser test tạo ứng viên Autoencoder C001-v2, đánh giá, yêu cầu người dùng xác nhận/lý do trước duyệt, chấm kết quả sang khu vực A có dấu vết phiên bản và hoàn nguyên về Isolation Forest C001-v1. Đây là phiên bản trong môi trường test riêng, không phải tuyên bố model production đang dùng. [Bằng chứng](evidence/release_ebadc6b/browser-report.json).

**8. Ví dụ thất bại/kết quả sai đã ghi nhận:**

- Chạy test CKKS bằng Python hệ thống thiếu TenSEAL trả `TENSEAL_UNAVAILABLE`; chạy đúng venv Agent2 đã đạt. Không có fallback âm thầm sang chấm rõ để làm test đạt.
- Test batch Portal tìm hai tiêu đề cũ nên lỗi sau khi giao diện chuyển sang từ phổ thông; cập nhật kỳ vọng đúng và chạy lại đạt.
- Nguồn thiếu hoặc model sai contract phải trả chưa khả dụng, không xác nhận giao dịch hợp lệ. Đây là hành vi an toàn cần giữ.
- Chưa có tập kết luận thật độc lập để báo cáo false-positive/false-negative gian lận có ý nghĩa thống kê.

**9. Link GitHub, demo, video, ảnh và pipeline:**

- [Repository](https://github.com/Khanhhh239/Multi-Agent-Finance) · [commit đã công bố](https://github.com/Khanhhh239/Multi-Agent-Finance/commit/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16).
- [Mã giao diện điều tra](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/sme_fraud/investigation.py) · [pipeline quản lý mô hình](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/sme_fraud/model_lifecycle.py) · [script demo kiểm thử hai khu vực](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/scripts/check_two_area_ui.py).
- [Demo local](http://127.0.0.1:8800/#agent2): cần máy đang chạy dịch vụ và tài khoản hợp lệ; chưa có URL demo công khai được xác nhận.
- Ảnh ứng dụng ở lượt kiểm thử điều tra trước: [hàng đợi](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/docs/evidence/investigation_20261119/01-queue.png), [điều tra](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/docs/evidence/investigation_20261119/02-investigation.png), [mobile](https://github.com/Khanhhh239/Multi-Agent-Finance/blob/ebadc6b867c2f2f8a3613b66b7dc1809199ccf16/agent2/docs/evidence/investigation_20261119/03-mobile.png). Không dùng mockup làm bằng chứng số liệu.
- Bảng kết quả mới: [verification.json](evidence/release_ebadc6b/verification.json), [8 kiểm tra trình duyệt](evidence/release_ebadc6b/browser-report.json). Video: chưa có đường dẫn đã xác nhận.

**10. Cách cài đặt và chạy lại:**

Tham khảo [README Agent2](../README.md), [setup_all.ps1](../../setup_all.ps1), [run_web.ps1](../../run_web.ps1), [hướng dẫn điều tra](INVESTIGATION_WORKFLOW.md). Từ thư mục gốc trên Windows có Python 3.12/PowerShell:

```powershell
git clone https://github.com/Khanhhh239/Multi-Agent-Finance.git
Set-Location Multi-Agent-Finance
git checkout ebadc6b867c2f2f8a3613b66b7dc1809199ccf16
.\setup_all.ps1
# Thiết lập cấu hình local, tài khoản/quyền, nguồn và artifact theo hướng dẫn dự án.
.\run_web.ps1
```

`run_web.ps1` khởi động nền tảng chung và có bước dừng tiến trình cũ trên các cổng của nền tảng. Dùng khi đã sẵn sàng khởi động lại. Máy mới không tự có database demo, model đã fit, khóa hoặc cấu hình private chỉ nhờ clone. Nhánh HE cần cài thêm dependency/môi trường Linux/WSL và tạo/quản lý khóa theo profile; không thuộc một lệnh cài Python cơ bản.

Chạy lại kiểm thử giao diện bằng kho tạm, không dùng dữ liệu live:

```powershell
.\agent2\.venv\Scripts\python.exe -X utf8 agent2/scripts/check_two_area_ui.py --output .runtime/agent2-two-area-recheck
```

Cần dependency Playwright và trình duyệt kiểm thử đã cài. Chưa nghiệm thu cài mới trọn gói trên một máy sạch trong lượt báo cáo này.

## E. Ứng dụng thực tế

**1. Cách người dùng vận hành:** kế toán nhập dữ liệu tại sảnh chung. Quản trị model chọn dữ liệu, huấn luyện/đánh giá và duyệt phiên bản thích hợp. Pipeline tạo kết quả theo cấu hình/phạm vi đã chọn. Người rà mở hàng đợi, kiểm tra quan hệ và chứng từ, ghi kết luận/hành động; quản lý theo dõi việc còn thiếu. Phản hồi chỉ phục vụ học lại khi được xác minh và đưa vào một chu kỳ huấn luyện mới có kiểm soát.

**2. Lợi ích và cơ sở ước tính hiệu quả:** kỳ vọng giảm thời gian tìm hồ sơ, hợp nhất căn cứ và ưu tiên việc cần rà; giữ lịch sử kiểm tra, hạn chế rà trùng. **Chưa có số giờ hoặc số tiền tiết kiệm đã đo tại doanh nghiệp thật.** Cần đo song song quy trình hiện tại và Agent2 trên cùng kỳ/cùng ngân sách; ghi tỷ lệ kết quả hữu ích, phần tìm thêm, phút rà, thời gian chờ và công sức quản trị. Không dùng tỷ lệ test đạt để suy ra ROI.

**3. Chi phí triển khai/vận hành:** chưa có benchmark chi phí hoặc báo giá. Các hạng mục gồm máy doanh nghiệp, CPU/RAM/lưu trữ, sao lưu, vận hành Portal, công sức rà/xác minh, quản trị model/khóa và worker cloud nếu dùng. HE có chi phí tính toán/truyền/lưu khóa riêng; chưa có cơ sở để cam kết rẻ, nhanh hoặc mức phí trên mỗi giao dịch.

**4. Yêu cầu phần cứng/phần mềm:** môi trường phát triển/demo hiện là Windows, Python 3.12, Portal, SQLite và các thư viện trong requirements; kiểm thử giao diện dùng Playwright/trình duyệt. Nhánh mã hóa cần các thư viện HE tương thích và Linux/WSL theo profile. AE hiện dùng `MLPRegressor`, không mặc định đòi GPU. Chưa có cấu hình CPU/RAM tối thiểu hay số người dùng đồng thời được đo để cam kết production.

**5. Rủi ro nghiệp vụ, bảo mật và kiểm soát:**

| Rủi ro | Biện pháp hiện có/yêu cầu cần giữ |
|---|---|
| Coi bất thường hoặc điểm cao là gian lận | Giải thích điểm, ghi giới hạn; yêu cầu đối chiếu và kết luận của người có thẩm quyền |
| Thiếu lịch sử/chứng từ | Trạng thái chưa khả dụng và lý do thiếu; không tự quy về 0 hoặc “hợp lệ” |
| Đọc nhầm doanh nghiệp hoặc dùng thông tin tương lai | Scope backend, snapshot/định danh theo doanh nghiệp, feature đúng thời điểm |
| Model/config sai phiên bản | Contract/checksum/artifact, phê duyệt, dấu vết run và khả năng rollback |
| Ghi đè/lưu trùng kết luận | Revision, idempotency, lịch sử thao tác và lưu bằng chứng tại backend |
| Lộ/mất khóa hoặc cloud dùng dữ liệu rõ | Giữ bí mật tại doanh nghiệp theo profile; kiểm chứng tách node/worker; không fallback rõ; cần quy trình backup/phục hồi khóa |
| Nhãn sai ý nghĩa | Xác minh định nghĩa nhãn trước train; không lấy giao dịch chưa rà làm nhãn 0 |

Test đã có không thay cho kiểm toán bảo mật độc lập hoặc chứng nhận tuân thủ. Trong prototype phản hồi LR, `confirmed_risk` đang được ánh xạ thành 1; **“có vấn đề/vi phạm” chưa tự đồng nghĩa “gian lận đã xác minh”**. Cần chốt và kiểm soát điểm này trước khi dùng nhãn đó để tuyên bố train model gian lận. [Nguồn ánh xạ nhãn](../sme_fraud/lr_fhe_training.py).

**6. Khả năng mở rộng:** có thể thêm nguồn, luật/model và profile qua adapter, kho artifact, bundle và API có scope. Khả năng chịu tải production chưa được chứng minh từ hai doanh nghiệp demo. Đồ thị điều tra hiện có giới hạn 10.000 bản ghi nguồn mỗi lần dựng và 80 nút mỗi lượt hiển thị; cần báo rõ khi vượt giới hạn, không cắt ngầm rồi khẳng định đã phân tích đầy đủ. [Giới hạn đồ thị](INVESTIGATION_WORKFLOW.md).

**7. Hạn chế hiện tại:** dữ liệu minh chứng là mô phỏng; thiếu nhãn thật và đánh giá nghiệp vụ độc lập; chưa định lượng hiệu quả, latency production, chi phí/tải; mức đủ nguồn khác nhau theo luật; HE mới ở các profile giới hạn; chưa chạy lại ba ca native trong lượt push; danh tính workspace chưa chắc là danh tính từng cá nhân; nhãn phản hồi LR còn cần chuẩn hóa ý nghĩa; chưa nghiệm thu cài mới và vận hành dài ngày trên hạ tầng thật.

**8. Hướng cải tiến tiếp theo:** ưu tiên thu thập nguồn được cấp quyền và chốt định nghĩa nhãn; nghiệm thu độc lập các ca có vấn đề/hợp lệ/thiếu nguồn/không áp dụng; đo 35 luật so với 35 luật + ML cùng ngân sách; kiểm tra gate/phê duyệt/rollback cùng cấu hình pipeline; nghiệm thu native HE từng profile với đối chiếu rõ–mã hóa, crash/recovery và thời gian; chuẩn hóa danh tính người rà, đóng gói cài đặt, đo tải và chi phí. Chỉ mở rộng sử dụng thực tế khi có bằng chứng phù hợp, không tăng tỷ trọng ML dựa trên dữ liệu demo hoặc số test đạt.
