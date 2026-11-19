# BIỂU MẪU THU THẬP THÔNG TIN AGENT

**Dự án:** Multi-Agent System – AI Quantum Challenge 2026
**Agent:** Agent2 – Hỗ trợ phát hiện và điều tra gian lận tài chính
**Ngày lập:** 19/11/2026, giờ Việt Nam.

## Phạm vi và cách đọc bằng chứng

- **Đã thực hiện:** có mã nguồn/chức năng và đã có lượt chạy được ghi nhận; không đồng nghĩa đã chứng minh hiệu quả tại doanh nghiệp thật.
- **Đã đo:** chỉ những con số trong báo cáo kiểm thử hoặc kiểm tra local được dẫn dưới đây.
- **Dự kiến/chưa nghiệm thu:** chưa có đủ bằng chứng xác nhận hoàn thành, dù có thể đã có thành phần backend hoặc đang có thay đổi mới.
- Mốc Git nền là `e4127f4fb1ebe771f967278145c596a30cacd139` trên `main`, cộng thay đổi local. Không coi checkout commit này là tự có toàn bộ chức năng mới. Chưa xác nhận phần thay đổi local đã được push.
- **Quan trọng:** tại lúc lập tài liệu, 7/9 tệp được đối chiếu đã khác checksum của lượt kiểm thử gần nhất. Những số test dưới đây thuộc **bản đã kiểm chứng**, không phải chứng nhận cho toàn bộ mã đang sửa. Xem [đối chiếu nguồn](evidence/investigation_20261119/source-comparison.json). Tài liệu này không chạy lại test hoặc cập nhật backend.

## A. Bài toán nghiệp vụ

**1. Tên Agent:** Agent2 – Hệ thống hỗ trợ phát hiện và điều tra gian lận tài chính; tên trong Portal: Trợ lý Giám sát.

**2. Đối tượng sử dụng:** kế toán, kiểm soát nội bộ, người rà soát được cấp quyền doanh nghiệp; quản lý mô hình/người phê duyệt cấu hình phân tích. Quyền truy cập đến từ Portal và được backend kiểm tra lại.

**3. Vấn đề thực tiễn Agent giải quyết:** nhiều giao dịch, chứng từ và thông tin nhân sự/NCC nằm ở các nguồn khác nhau. Người rà khó chọn giao dịch cần kiểm tra trước, hiểu căn cứ cảnh báo, tìm giao dịch liên quan và lưu lại kết quả đối chiếu.

**4. Nguyên nhân và tác động:** dữ liệu phân tán, lịch sử không đầy đủ, định danh không thống nhất, thay đổi hồ sơ theo thời gian và công suất kiểm tra hữu hạn có thể làm tăng thời gian rà, cảnh báo trùng hoặc bỏ sót dấu hiệu. Đây là mô tả bài toán; **chưa có khảo sát định lượng độc lập tại doanh nghiệp thật**, chưa công bố tỷ lệ tổn thất hoặc số giờ tiết kiệm. Các ca chia nhỏ, tự duyệt, liên kết tài khoản được minh họa bằng [bộ nguồn mô phỏng](../examples/full_rules/README.md).

**5. Mục tiêu và yêu cầu nghiệp vụ:** sử dụng dữ liệu được cấp quyền từ sảnh chung; ưu tiên giao dịch cần rà theo kết quả đã lưu; giải thích dấu hiệu và phần thiếu nguồn; hỗ trợ điều tra quan hệ và đối chiếu chứng từ; lưu kết luận và lịch sử. Điểm cao không tự xác nhận gian lận. Huấn luyện phải tách khỏi chấm, theo doanh nghiệp, có đánh giá và phê duyệt trước khi dùng.

**6. Kết quả kỳ vọng:** hàng đợi dễ sử dụng, hồ sơ điều tra có căn cứ và truy vết; về sau đo được số giao dịch hữu ích tìm thêm trên cùng ngân sách rà. Đây là mục tiêu, không phải kết quả hiệu quả đã đạt trên dữ liệu thật.

## B. Dữ liệu

**1. Nguồn dữ liệu, đường dẫn và quyền sử dụng:**

- Nguồn vận hành: sảnh chung của Portal, qua cầu `portal/agent2_intake.py`, hợp đồng chung trong `shared/finance_input`, kho snapshot theo doanh nghiệp và API được xác thực. Không lấy quyền doanh nghiệp từ lựa chọn do trình duyệt tự khai.
- Nguồn demo: [full_rules](../examples/full_rules/README.md), [rule_bridge_models](../examples/rule_bridge_models/README.md). Đây là dữ liệu mô phỏng, không phải chứng từ gốc của doanh nghiệp thật.
- Kho local đang dùng nằm trong `agent2/.runtime/`; cấu hình và đường dẫn phụ thuộc máy. Không đưa database, khóa, token hay cấu hình riêng lên GitHub.
- Chưa có hồ sơ cấp quyền sử dụng bộ giao dịch thật của một doanh nghiệp để công bố kết quả thực tế. Cần xác nhận quyền và phạm vi sử dụng trước khi tiếp nhận.

**2. Quy mô dữ liệu:** một bộ demo ML bridge có **45 giao dịch nguồn mỗi doanh nghiệp: 32 lịch sử train, 8 reference, 5 ứng viên**; kỳ ứng viên 01–05/08/2025, nguồn khóa 06/08/2025 00:00 UTC+07. Đây là quy mô riêng của bộ demo, không phải tổng dữ liệu toàn dự án. Bộ full-rules có gói **120 tệp C001/C002**, mỗi tệp là một kịch bản nguồn; không được hiểu là 120 giao dịch. Định dạng đầu vào gồm CSV/XLSX được Portal chuyển đổi và JSON theo hợp đồng. [Nguồn quy mô demo ML](../examples/rule_bridge_models/README.md), [nguồn gói luật](../examples/full_rules/README.md).

**3. Phân loại:** dữ liệu dùng cho các bằng chứng của báo cáo này là **giả lập/tổng hợp theo kịch bản**. Không gọi đó là dữ liệu thật hoặc nhãn gian lận đã xác minh.

**4. Làm sạch, chuẩn hóa:** kiểm tra cột, kiểu, định danh trùng, quyền doanh nghiệp, liên kết nguồn và thời điểm; chuẩn hóa theo hợp đồng; lưu snapshot có checksum. Feature chỉ sử dụng thông tin được biết trong phạm vi thời gian hợp lệ. Tiền điều chỉnh âm hợp lệ được giữ theo contract; thiếu dữ liệu được biểu diễn bằng trạng thái/lý do thiếu. Tiền xử lý và xử lý thiếu được fit trên train, lưu theo model; không học lại từ giao dịch đang chấm.

**5. Chất lượng trước/sau xử lý:** đã có cơ chế kiểm tra và từ chối/báo thiếu nguồn; **chưa có bảng đo tỷ lệ lỗi, tỷ lệ thiếu, sai liên kết trước–sau cho dữ liệu doanh nghiệp thật**. Demo bridge có contract 33 cột, trong bộ minh họa có 8 cột chưa có nguồn phù hợp nên vẫn null; không biến thành số 0 hoặc thông tin có thật. Không suy ra “dữ liệu sạch 100%” từ việc parser chấp nhận tệp.

**6. Chia dữ liệu, chống rò rỉ:** chia theo thời gian, tách train/reference/đánh giá; xử lý feature theo `as_of` và thời điểm nguồn được biết; giữ nhóm giao dịch đồng thời đúng quy tắc lịch sử. Chỉ fit imputer/scaler/feature selection trên train. Không dùng mã định danh, nhãn và nội dung bằng chứng làm biến dự báo; không coi giao dịch chưa rà là nhãn 0. Tập kịch bản không thay thế tập nghiệm thu độc lập.

## C. Thuật toán và công nghệ

**1. Mô hình/thuật toán:**

- Catalog **35 luật nghiệp vụ**; thống kê/đối chiếu lịch sử; đồ thị liên kết định danh/đối tượng.
- Backend model không nhãn có Isolation Forest, ECOD, LOF, Autoencoder trong [ml_estimators.py](../sme_fraud/ml_estimators.py). Autoencoder hiện là mạng bottleneck dùng `MLPRegressor`, không mặc định yêu cầu GPU.
- Demo bridge tài liệu hóa C001 dùng Isolation Forest, C002 dùng ECOD, RobustZ riêng cho thống kê. Đây không phải chứng nhận mọi model đều đang được kích hoạt trong bản Portal hiện tại.
- Có các nhánh/prototype HE và train mã hóa riêng. **Không có căn cứ trong lượt nghiệm thu giao diện này để nói IF/AE/ECOD/LOF hoặc toàn bộ 35 luật/33 feature đã chạy HE end-to-end.**

**2. Lý do lựa chọn:** luật thể hiện kiểm soát có căn cứ; thống kê và ML không nhãn hỗ trợ tìm khác thường khi thiếu nhãn tin cậy; đồ thị hỗ trợ đối chiếu các đối tượng/giao dịch có liên quan. Chưa thể kết luận model nào tối ưu cho mọi doanh nghiệp; cần chọn bằng validation tương thích với nghiệp vụ và nguồn.

**3. Pipeline:**

`Sảnh chung → kiểm tra/chuẩn hóa → snapshot bất biến → feature đúng thời điểm → nhánh phân tích khả dụng → phối hợp theo bundle được duyệt → gộp vụ → chính sách/ngân sách cấp vụ → hàng đợi giao dịch → điều tra quan hệ/chứng từ → kết quả và lịch sử.`

Luồng model tách riêng: `snapshot → kiểm tra độ phù hợp → chia kỳ → fit feature/preprocess/model → đánh giá → lưu artifact/manifest → gate → phê duyệt → chọn bundle dùng để chấm`. Các phần backend đã có được giữ lại; **màn hình quản trị không giám sát thống nhất theo ảnh thiết kế vẫn cần khảo sát/nghiệm thu riêng**, không coi là hoàn thành chỉ vì có ảnh hoặc hàm fit.

**4. Tham số/cấu hình chính:** tenant/company, snapshot/checksum, `as_of`, kỳ train/reference/evaluation, thuật toán, seed, cột feature, missing policy, feature/preprocess contract, model artifact, bundle, chính sách và ngân sách. Không có một tỷ trọng luật/ML cố định được chứng minh tối ưu. Ngân sách so sánh trước đây đã chốt **tối đa 5 giao dịch/phương án/doanh nghiệp**; đây không phải ngân sách hàng đợi cấp vụ. Tham số thực tế phải lấy từ manifest/bundle của đúng lần chạy.

**5. Giả định và điều kiện hoạt động:** dữ liệu có phạm vi quyền đúng; định danh và timestamp đủ để đối chiếu; model tương thích feature; nguồn còn thiếu được báo rõ; có người hiểu nghiệp vụ rà và xác nhận. Cloud chỉ được dùng cho profile hỗ trợ tính trên bản mã thật; thiếu hỗ trợ trả chưa khả dụng, không âm thầm gửi/chấm dữ liệu rõ.

**6. Input/Output – ba ví dụ rút gọn:**

| Ví dụ | Input | Output/diễn giải đúng |
|---|---|---|
| Liên kết NCC–nhân viên | Nguồn C001 có hồ sơ NCC và nhân viên tham chiếu cùng tài khoản; xem `C001_B1_signal.json` trong bộ full-rules | Có tín hiệu/liên kết kèm tham chiếu nguồn để đối chiếu. Chưa xác nhận gian lận chỉ bằng liên kết. |
| Thiếu phạm vi lịch sử | `C001_coverage_unknown.json` | Phần kiểm tra cần nguồn đó trả chưa khả dụng/lý do thiếu, không coi là không vi phạm. |
| Điều tra và ghi kết quả | Giao dịch thuộc packet đã tiếp nhận, cùng `snapshot_id`, `run_id`, `bundle_id`; người rà ghi Chưa đủ căn cứ và tài liệu cần bổ sung | Kết quả có revision/history trên server; trạng thái cần bổ sung. Đây là kết quả nghiệp vụ, không tự tạo nhãn gian lận cho model. |

Các ví dụ trên là diễn giải, không phải toàn bộ JSON schema. Xem [API điều tra](../sme_fraud/investigation_api.py), [nguồn demo](../examples/full_rules/README.md).

**7. Tương tác với agent khác:** Portal cung cấp phiên đăng nhập, phạm vi doanh nghiệp, hồ sơ và luồng nhập dữ liệu dùng chung. Agent2 đọc dữ liệu qua interface được cấp quyền; không có bằng chứng ở lượt này rằng kết luận Agent2 đã tự động được Agent1/3/4 tiêu thụ trong một workflow liên agent hoàn chỉnh. Không nói “các agent tự học chéo” nếu chưa có contract và nghiệm thu.

## D. Prototype và kiểm thử

**1. Chức năng đã hoàn thành tại bản có bằng chứng:** hàng đợi từ điểm giao dịch đã lưu; bộ lọc/trạng thái; giải thích nguồn điểm; trang điều tra; mở rộng nút/đọc căn cứ đường nối; giao dịch liên quan; xem nguồn và dấu vết model khi có; bắt đầu và khôi phục phiên rà; đính kèm/tải bằng chứng; lưu kết quả, lịch sử, chống gửi trùng; bảo vệ nội dung chưa lưu và quyền doanh nghiệp. [Báo cáo kiểm chứng](evidence/investigation_20261119/verification.json), [hướng dẫn](INVESTIGATION_WORKFLOW.md).

**2. Chưa hoàn thành/chưa đủ bằng chứng:** quản trị IF/AE thống nhất theo mẫu mới, luồng phê duyệt–rollback–bundle đầy đủ trên màn hình này, đo hiệu quả gian lận bằng dữ liệu thật/nhãn độc lập, hiệu quả ML bổ sung vượt baseline trên doanh nghiệp thật, HE cho mọi thuật toán/nguồn. Mã nguồn hiện có thêm thay đổi sau nghiệm thu, cần chạy lại trước phát hành. Xem [prompt phần quản lý mô hình](PROMPT_ANTIGRAVITY_MODEL_MANAGEMENT.md).

**3. Kịch bản demo:** mở Portal 8800 → đăng nhập → Agent2 → chọn C001 → chọn nguồn kết quả → chọn dòng → Mở điều tra → mở rộng một nút → xem căn cứ → xem bằng chứng/giải thích điểm → Bắt đầu rà → đính kèm PDF/PNG/JPEG → ghi kết quả/hành động → lưu → tải lại → kiểm tra lịch sử. Lặp với C002 và thử truy cập C001 bằng phạm vi C002 để xác nhận bị chặn. Chỉ thao tác kết luận thử trên dữ liệu mô phỏng được phép.

**4. Số lượng/loại kiểm thử đã ghi nhận:**

| Phạm vi | Kết quả bản đã kiểm chứng | Bằng chứng |
|---|---|---|
| Backend mới và regression liên quan | 24 test đạt; gồm kiểm tra điểm nguồn, nguồn thiếu, đồ thị đúng thời điểm, tách DN, lưu/khôi phục/hủy quyền | [verification.json](evidence/investigation_20261119/verification.json), `test_investigation.py` và bộ test liên quan |
| Portal | 64 test đạt | [verification.json](evidence/investigation_20261119/verification.json) |
| Trình duyệt end-to-end | 6 tình huống đạt: hàng đợi; đồ thị; căn cứ; khôi phục/đính kèm/lưu idempotent; bộ lọc/đổi DN; quyền/mobile | [browser-report.json](evidence/investigation_20261119/browser-report.json) |

Không cộng với các test của những pipeline cũ để công bố tổng test bản hiện tại. Sáu tình huống giao diện không phải sáu test FHE; báo cáo ghi rõ `actual_fhe=false`.

**5. Metric và số đo được:**

| Chỉ số | Số đo | Diễn giải/giới hạn |
|---|---|---|
| Hàng đợi C001 khi kiểm tra local | 4 dòng giao dịch/vụ; queue/detail HTTP 200 | Phạm vi kết quả đã tiếp nhận, không phải 4 gian lận |
| Hàng đợi C002 khi kiểm tra local | 3 dòng; queue/detail HTTP 200 | Không phải tổng giao dịch nguồn hoặc recall |
| Thành phần đồ thị của giao dịch được chọn C001 | 155 nút, 293 cạnh | Một lượt mở chi tiết; không phải toàn graph của doanh nghiệp |
| Thành phần đồ thị của giao dịch được chọn C002 | 173 nút, 323 cạnh | Cùng giới hạn diễn giải trên |
| Bảo toàn khi cập nhật local | 14 DB được sao lưu; kiểm tra bảng nguồn/model và cấu hình không đổi | Không phải chứng nhận bảo mật tổng thể |
| Precision/recall/F1/AUC gian lận; tiết kiệm thời gian rà | Chưa có số đo đủ căn cứ để công bố | Thiếu tập nhãn thật/đánh giá nghiệp vụ độc lập |

[Nguồn số đo local](evidence/investigation_20261119/live-acceptance.json). Không dùng thời gian chạy test làm latency chấm model, không dùng số node/cạnh làm thước đo phát hiện gian lận.

**6. Baseline và so sánh:** baseline cần dùng là **35 luật** đối chiếu **35 luật + ML**, cùng snapshot, kỳ, tiêu chí hữu ích và tối đa 5 giao dịch/phương án/DN; ưu tiên luật rồi ML bổ sung chỗ trống theo phương án đã thống nhất. Chưa có kết quả trong bộ bằng chứng này để công bố phần trăm cải thiện hay khẳng định ML thắng luật. Chất lượng kỹ thuật và chất lượng nghiệp vụ được báo cáo riêng.

**7. Ví dụ chạy thành công:** kịch bản mất phản hồi sau khi backend đã lưu rồi gửi lại vẫn chỉ có một revision kết quả; tệp bằng chứng tải về khớp nội dung; trạng thái và lịch sử còn sau reload. Kiểm tra local C001/C002 đọc được chi tiết và nguồn khớp hàng đợi. [Kịch bản trình duyệt](evidence/investigation_20261119/browser-report.json).

**8. Ví dụ lỗi/giới hạn:** trước sửa, reload làm mất lease trong trình duyệt trong khi server vẫn giữ phiên, khiến bấm bắt đầu bị chặn tạm thời; đã bổ sung khôi phục phiên và kiểm tra lại trong bộ test ghi nhận. Nguồn thiếu, model sai contract hoặc nhánh chưa hỗ trợ không được tự trả “hợp lệ”; không được tự fit. Các lỗi mới sau khi source thay đổi chưa được loại trừ bởi báo cáo cũ. Không có tập kết luận thật để liệt kê false-positive/false-negative có giá trị thống kê.

**9. Link GitHub/demo/ảnh/video:**

- [Repository](https://github.com/Khanhhh239/Multi-Agent-Finance); mốc nền `e4127f4`, còn thay đổi local. Không khẳng định các tài liệu/ảnh mới đã được push.
- [Demo local](http://127.0.0.1:8800/#agent2), chỉ truy cập khi máy đang chạy dịch vụ; không phải địa chỉ demo công khai.
- Ảnh chụp ứng dụng trong môi trường kiểm thử: [hàng đợi](evidence/investigation_20261119/01-queue.png), [điều tra](evidence/investigation_20261119/02-investigation.png), [mobile](evidence/investigation_20261119/03-mobile.png).
- Video: chưa có đường dẫn được xác nhận. Ảnh mockup trước đây chỉ là thiết kế, các số 88/100, 3/5, 24.860… trong mockup không phải kết quả đo của ứng dụng.

**10. Cài đặt/chạy lại:** xem [README Agent2](../README.md), [hướng dẫn điều tra](INVESTIGATION_WORKFLOW.md), `setup_all.ps1`, `run_web.ps1` ở gốc repo. Môi trường dự án dùng Python 3.12 và dependency trong requirements/lock; HE cần môi trường Linux/WSL và cấu hình/khóa phù hợp. Máy mới phải thiết lập cấu hình local, quyền, dữ liệu và artifact hợp lệ, không thể chỉ clone rồi có khóa demo.

Trên máy đã cấu hình: chạy `./run_web.ps1` từ gốc rồi mở Portal. Script chạy chung có thao tác dừng tiến trình trên các cổng nền tảng; chỉ dùng khi đã chốt thời điểm restart, tránh làm gián đoạn công việc đang chạy. Các lệnh test riêng ở `INVESTIGATION_WORKFLOW.md` dùng kho tạm. Chưa chạy lại cài mới trên một máy sạch trong lượt lập báo cáo này.

## E. Ứng dụng thực tế

**1. Vận hành thực tế:** người dùng nhập dữ liệu qua sảnh chung; người quản lý chuẩn bị/duyệt phiên bản thích hợp; pipeline tạo nguồn kết quả và tiếp nhận vụ theo chính sách; kế toán rà giao dịch, truy quan hệ, bổ sung chứng từ và lưu kết quả; quản lý theo dõi việc còn thiếu. Việc rà cần người có chuyên môn và nguồn gốc chứng từ đáng tin cậy.

**2. Lợi ích và cơ sở ước tính:** kỳ vọng giảm thời gian tìm/chắp nối hồ sơ, giúp ưu tiên kiểm tra và giữ dấu vết. Chưa định lượng tiền/giờ tiết kiệm. Muốn ước tính cần đo baseline thủ công và Agent2 trên cùng kỳ/ngân sách, ghi số vụ hữu ích, cảnh báo không hữu ích, phút rà, thời gian chờ và chi phí vận hành; không suy từ test mô phỏng thành ROI thật.

**3. Chi phí:** chưa có bảng đo để báo giá. Các hạng mục gồm máy doanh nghiệp, CPU/RAM/lưu trữ, backup, quản trị quyền/khóa, công sức rà, vận hành worker và chi phí cloud nếu dùng. Không có căn cứ nói HE rẻ/nhanh hơn chấm rõ hoặc không cần tài nguyên bổ sung.

**4. Phần cứng/phần mềm:** đã vận hành demo local trên Windows với Python, thư viện khoa học dữ liệu, SQLite và Portal; nhánh HE dùng Linux/WSL/Concrete theo môi trường riêng. Playwright/Chrome dùng cho test giao diện. Chưa có cấu hình phần cứng tối thiểu được benchmark độc lập hoặc cam kết tải đồng thời. Autoencoder hiện có không mặc định đòi GPU; điều này không chứng minh CPU đủ cho mọi quy mô.

**5. Rủi ro và kiểm soát:** cảnh báo nhầm/bỏ sót → rà nghiệp vụ, không coi điểm là kết luận; thiếu nguồn → unavailable/lý do thiếu; rò rỉ theo DN/thời gian → scope server và nguồn bất biến; model không tương thích → contract/checksum/gate; kết luận bị ghi đè → revision/idempotency/lịch sử; khóa lộ/mất → giữ tại DN, bảo vệ và quy trình backup/khôi phục. Việc có code/test không thay thế kiểm toán bảo mật hoặc chứng nhận tuân thủ pháp lý.

**6. Khả năng mở rộng:** kiến trúc cho phép thêm nguồn, model và profile qua adapter, kho artifact và bundle. Khả năng chịu tải thực tế chưa được chứng minh. Đồ thị hiện có giới hạn 10.000 bản ghi nguồn mỗi lượt dựng và 80 nút mỗi lượt hiển thị mở rộng; vượt giới hạn phải báo rõ. Không tuyên bố hỗ trợ vô hạn hay multi-tenant production chỉ từ hai DN demo.

**7. Hạn chế:** dữ liệu minh chứng là mô phỏng; thiếu nhãn gian lận thật xác minh độc lập; thiếu kết quả hiệu quả và chi phí; nguồn nhiều luật không luôn đầy đủ; danh tính Portal có thể là workspace chia sẻ; HE chỉ có các profile giới hạn; quản trị model theo thiết kế mới chưa có nghiệm thu hoàn chỉnh trong bộ bằng chứng này; code hiện tại đã khác bản test gần nhất.

**8. Hướng cải tiến:** hoàn thiện khu vực B theo [prompt giao việc](PROMPT_ANTIGRAVITY_MODEL_MANAGEMENT.md); đánh giá không giám sát có kiểm soát; phê duyệt/rollback đúng bundle; thử với nguồn được cấp quyền và người rà độc lập; đo luật so với luật + ML cùng ngân sách; kiểm thử lại phiên bản cuối, đóng gói nguồn/artifact/test và video demo; mở rộng HE theo từng profile có kiểm chứng riêng.
