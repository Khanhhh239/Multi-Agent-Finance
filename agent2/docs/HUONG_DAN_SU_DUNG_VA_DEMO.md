# Agent 2 — Hướng dẫn sử dụng và demo

Cập nhật: **07/11/2026** · Nhánh mã nguồn: **agent2-Sang**.

Tài liệu dành cho người thao tác và người trình bày demo: nhập dữ liệu doanh nghiệp, chọn model ML, chấm bất thường, rà căn cứ và ghi nhận thời gian. Toàn bộ giao diện dùng một địa chỉ **http://127.0.0.1:8765/**.

## 1. Mở ứng dụng

### Máy đang có workspace D:\agent22

Mở PowerShell tại thư mục dự án và chạy:

```powershell
Set-Location D:\agent22
python -B start_review.py
```

Khi thấy `Review UI ready` hoặc `Already running`, mở http://127.0.0.1:8765/. Lệnh dùng profile đã lưu tại `.runtime/review/server_8765.config.json` để chọn đúng môi trường Python, database và nguồn dữ liệu.

Để dừng phiên do launcher này khởi động:

```powershell
python -B start_review.py --stop
```

Nếu mới clone từ GitHub, làm theo **mục 9** trước. Database, model đã huấn luyện và profile riêng của máy không có trong Git; bản clone chưa có dữ liệu của workspace này.

### Các màn hình

| Màn hình | Địa chỉ | Thao tác chính |
| --- | --- | --- |
| Hồ sơ rà soát | http://127.0.0.1:8765/ | Xem hàng đợi và hồ sơ hiện có |
| Nhập dữ liệu | http://127.0.0.1:8765/data-import | Tải CSV/Excel, kiểm tra, xem trước, xác nhận lưu |
| Dữ liệu & ML | http://127.0.0.1:8765/company-ml | Chọn doanh nghiệp, bổ sung nhãn, đánh giá và cố định model |
| Phiếu rà ML | http://127.0.0.1:8765/ml-reviews | Rà bằng chứng, ghi hành động, đo thời gian và xuất phiếu |

Phiên local đã cấu hình dùng danh tính **MÔ PHỎNG · Quản lý phiên local** do máy chủ cấp. Bản triển khai có tài khoản thực tế cần cấp quyền và phạm vi doanh nghiệp tại máy chủ. Một địa chỉ local chỉ truy cập được trên chính máy đang chạy ứng dụng.

## 2. Quy trình sử dụng

**Chọn doanh nghiệp → nhập và kiểm tra dữ liệu → tạo feature → lưu dữ liệu → đánh giá model → xác nhận phiên bản → chấm → rà kết quả.**

Mỗi doanh nghiệp có tập ML, phiên bản và model đang dùng riêng. Thay lựa chọn ở C001 không tự đổi model của C002. Model mới chỉ trở thành model đang dùng sau khi được xác nhận.

ML hiện chạy ở chế độ **shadow**: kết quả phục vụ đối chiếu, chưa tự thay hàng đợi hồ sơ, kết luận hoặc thông báo nghiệp vụ. Một giao dịch có điểm bất thường cao vẫn cần được kiểm tra chứng từ.

## 3. Nhập giao dịch CSV/Excel

1. Mở **Nhập dữ liệu**. Chọn **Bộ dữ liệu** và **Doanh nghiệp**; demo trong tài liệu dùng bộ **003**.
2. Mở **Mã trong danh mục kết nối** để kiểm tra mã nhân viên, nhà cung cấp và khách hàng được phép dùng.
3. Bấm **Tải mẫu CSV**. Mẫu này chỉ có tiêu đề; điền giao dịch theo đúng các cột, hoặc dùng tệp mô phỏng tạo ở mục 9.
4. Chọn tệp `.csv` hoặc `.xlsx`. Chọn định dạng thời gian, mã hóa và dấu phân cách phù hợp.
5. Bấm **Kiểm tra & tạo bản xem trước**. Đọc lỗi theo dòng/cột và hướng dẫn sửa; sửa tệp rồi kiểm tra lại nếu còn lỗi.
6. Khi hợp lệ, kiểm tra doanh nghiệp, số dòng, khoảng thời gian, cảnh báo nguồn thiếu và **10 giao dịch đầu sau chuẩn hóa**. Phiên bản hiện tại tạo **194 feature** từ dữ liệu và danh mục kết nối.
7. Đọc cảnh báo thay thế, tích ô xác nhận, bấm **Lưu dữ liệu & chuyển sang chọn ML**. Trang chuyển sang đúng doanh nghiệp vừa nhập.

**Bước xem trước chưa lưu tập giao dịch. Bản xem trước có hiệu lực 20 phút.** Nếu đổi dữ liệu, danh mục hoặc model sau khi xem trước, cần kiểm tra lại trước khi lưu.

### Quy tắc chuẩn bị tệp

| Nội dung | Yêu cầu |
| --- | --- |
| Dung lượng/số dòng | Tối đa 10 MB và 10.000 giao dịch mỗi tệp |
| Excel | `.xlsx`, đúng một sheet, dòng đầu là tên cột; dán giá trị, không dùng công thức |
| Mã định danh | Mã giao dịch duy nhất trong tệp. Mã nhân viên, NCC, khách hàng thuộc đúng doanh nghiệp và đã tồn tại tại thời điểm giao dịch |
| Mã và tài khoản trong Excel | Lưu kiểu **Text** để giữ số 0 đầu. Đổi định dạng sau khi đã mất số 0 không khôi phục được mã |
| Thời gian | ISO, ví dụ `2024-01-02T12:00:00+07:00`; hoặc chọn định dạng `DD/MM/YYYY HH:MM[:SS]`. Không có múi giờ được hiểu là giờ Việt Nam |
| Thứ tự thời gian | Tạo ≤ duyệt ≤ ghi sổ; thời điểm ghi sổ không ở tương lai |
| Tiền | Số nguyên VND, không dấu phân nhóm/ký hiệu tiền. Ví dụ `1000000`; `amount_vnd` và `approval_limit_vnd` phải lớn hơn 0 |
| Dữ liệu thiếu | Bổ sung trường bắt buộc từ nguồn gốc. Trường tùy chọn thiếu được thông báo; không tự suy đoán chứng từ hoặc số tiền |

Các cột bắt buộc hiện tại được liệt kê dưới đây. Xem **Cột và loại giao dịch được hỗ trợ** trên web để biết danh sách tùy chọn và loại giao dịch hợp lệ.

```text
transaction_id,posted_at,created_at,approved_at,txn_type,
amount_vnd,approval_limit_vnd,creator_id,approver_id,
is_financial_entry,debit_account,credit_account,journal_signature,
accounting_purpose,recognised_input_vat_vnd,recognised_output_vat_vnd,
writeoff_provision_vnd,production_cost_vnd
```

Đây là danh sách để tra cứu; dùng tệp mẫu tải từ web để có một dòng tiêu đề CSV đúng. Với dòng không phải bút toán tài chính (`is_financial_entry=0`), các cột tài khoản/chữ ký vẫn có trong tiêu đề nhưng có thể để trống theo bộ kiểm tra.

### Hiểu đúng thao tác cập nhật

| Thao tác | Ảnh hưởng |
| --- | --- |
| Xem trước tệp giao dịch | Kiểm tra và tạo feature; chưa thay tập ML đã lưu |
| Xác nhận nhập CSV/Excel | **Thay toàn bộ tập ML của doanh nghiệp**, không nối thêm; cần tải đủ lịch sử. Nhãn trong tập thay thế được xóa và phải nhập lại nếu còn phù hợp |
| Bổ sung CSV nhãn ở màn hình ML | Ghép theo mã giao dịch, giữ nhãn không có trong tệp; xem trước và xử lý rõ xung đột |
| Cập nhật nguồn đã kết nối | Nạp nguồn máy chủ đã cấu hình; giữ nhãn cho giao dịch và feature không đổi |

Các thao tác trên giữ lựa chọn model đang dùng. Nếu định dạng nguồn hoặc hợp đồng feature không tương thích, nút chấm bị khóa; cần đánh giá và xác nhận phiên bản phù hợp. Dữ liệu CSV nhập chưa cung cấp mọi lịch sử nghiệp vụ; feature bằng 0 do thiếu nguồn không chứng minh giao dịch không có rủi ro.

## 4. Chọn, đánh giá và cố định model

1. Mở **Dữ liệu & ML**, kiểm tra lại bộ dữ liệu và doanh nghiệp.
2. Kiểm tra số giao dịch, feature, nhãn và khoảng thời gian. Nếu đang dùng dữ liệu CSV/Excel đã nhập, không cần nạp lại nguồn kết nối.
3. Chọn thuật toán và đặt **Cuối kỳ train**, **Cuối kỳ calibration**, **Tỷ lệ cảnh báo tham chiếu trên calibration (%)**.
4. Bấm **Huấn luyện & đánh giá ứng viên**. Chờ lưu ứng viên rồi xem kết quả ở **Xác nhận phiên bản**.
5. Đối chiếu kỳ đánh giá, số dòng, tỷ lệ cảnh báo và chỉ số có nhãn nếu có. Bấm **Xác nhận dùng vN** cho phiên bản đã chọn.
6. Bấm **Chạy ML với phiên bản đang dùng**. Kiểm tra số giao dịch đã chấm, số vượt ngưỡng và lịch sử lượt chạy.
7. Tải lại trang, chọn lại doanh nghiệp và kiểm tra phiên bản đang dùng vẫn được giữ.

| Thuật toán | Điều kiện cần lưu ý |
| --- | --- |
| Isolation Forest | Không yêu cầu nhãn gian lận để train |
| Autoencoder | Không yêu cầu nhãn; đọc cảnh báo chưa hội tụ nếu xuất hiện |
| ECOD | Không yêu cầu nhãn; sử dụng tham chiếu đã học từ train |
| Local Outlier Factor (LOF) | Chạy chế độ novelty để chấm giao dịch ngoài kỳ học |
| CatBoost | Cần thư viện tùy chọn và nhãn đã xác minh cho **mọi dòng train**, đủ hai lớp 0/1; thời điểm biết nhãn phải trước cuối kỳ train |

Ứng dụng kiểm tra điều kiện CatBoost theo kỳ train đang chọn. Nếu chưa đủ, đọc lý do hiển thị và bổ sung nguồn nhãn hợp lệ; không biến điểm luật, điểm model hoặc nhận xét “hữu ích” thành nhãn gian lận.

**Train** dùng để học model và tiền xử lý; **calibration** dùng để chọn ngưỡng; **evaluation** dùng để đối chiếu trên dữ liệu về sau. Ranh giới là thời điểm loại trừ: dòng đúng thời điểm cuối train thuộc calibration, dòng đúng thời điểm cuối calibration thuộc evaluation. Cần tối thiểu **5 dòng train, 2 calibration và 2 evaluation**.

**Giữ model hiện tại** giữ phiên bản phù hợp đang dùng. **Quay lại vN** chỉ mở cho phiên bản từng kích hoạt và còn tương thích. Điểm giữa các thuật toán không cùng thang đo; số cảnh báo thấp hơn hoặc thời gian máy chạy nhanh hơn chưa đủ để chọn model tốt hơn.

## 5. Bổ sung nhãn đã xác minh

Chỉ nhập kết luận đã được người có trách nhiệm xác minh và có căn cứ. Trên màn hình ML, chọn CSV ở **Nhãn đã rà soát · tùy chọn**, rồi bấm nút cập nhật dữ liệu/nhãn của phần này. Tệp phải có các cột:

```csv
company_id,transaction_id,label,reviewer_id,reviewed_at,evidence_ref,verified
```

- `label`: `0` hợp lệ; `1` gian lận đã xác nhận. `verified`: `1`.
- `transaction_id`: giao dịch trong tập ML hiện hành của đúng doanh nghiệp.
- `reviewer_id`, `reviewed_at`, `evidence_ref`: người rà, thời điểm có múi giờ và tham chiếu căn cứ thực tế.

Đọc số nhãn hiện có, nhãn thêm, trùng và xung đột trước khi bấm **Lưu nhãn**. Nếu xung đột, chọn **Giữ nhãn cũ, chỉ thêm nhãn mới** hoặc **Sửa các nhãn xung đột theo tệp mới**. Trường hợp sửa phải nhập lý do và tích xác nhận đã đối chiếu căn cứ. Thay đổi người rà, thời điểm hoặc căn cứ cũng được xem là xung đột, kể cả khi lớp 0/1 giống nhau.

Ví dụ: đang có 15 nhãn, thêm một giao dịch chưa có nhãn thì được 16; tải lại một nhãn giống hệt thì vẫn 15. Các nhãn không liên quan không bị thay bằng nội dung của tệp mới.

## 6. Rà cảnh báo và đo thời gian

Phiếu rà cần một **gói so sánh đã khóa** được máy chủ nhập. Chạy chấm trên màn hình ML không tự tạo gói này. Workspace hiện có gói C001/C002; demo mới tạo gói theo mục 10.

1. Mở **Phiếu rà ML**, chọn **Lượt đánh giá**, **Doanh nghiệp** và một phiếu.
2. Bấm **Bắt đầu / tiếp tục** trước khi đối chiếu dữ kiện và chứng từ. Bấm **Tạm dừng** khi nghỉ.
3. Chọn một kết quả: **Hữu ích · có hành động cụ thể**, **Không cần hành động · đã đủ căn cứ** hoặc **Chưa đủ căn cứ / cần thêm tài liệu**.
4. Ghi nhận xét/căn cứ và tham chiếu đã kiểm tra. Nếu chọn hữu ích, ghi hành động cụ thể, ví dụ đối chiếu khoản nghi trả trùng và yêu cầu điều chỉnh khi được xác nhận.
5. Bấm **Lưu bản nháp** nếu chưa hoàn tất. Khi hoàn tất, kiểm tra thời gian, tích xác nhận trực tiếp rà và bấm **Xác nhận đã rà**.
6. Tải lại để kiểm tra nội dung đã lưu và thời gian đã được máy chủ xác nhận. Người có quyền quản lý dùng **Tải CSV phiếu…**; bảng tên model chỉ mở khi hoàn tất toàn bộ phiếu trong phạm vi tài khoản.

Tên model, điểm và thứ hạng được ẩn khi rà để người dùng nhận xét từ dữ kiện. Một giao dịch trùng giữa nhiều model chỉ cần rà một lần. “Chưa đủ căn cứ” được ghi riêng; không tự đổi thành “không hữu ích”.

Đồng hồ do máy chủ ghi nhận, tạm dừng khi tab bị ẩn. Mất kết nối quá 30 giây sẽ dừng phiên và bỏ phần thời gian chưa được xác nhận. Nếu thấy **Dừng phiên cũ để tiếp tục**, thực hiện rồi bắt đầu lại; kiểm tra nội dung và đồng hồ trước khi chốt. Phiếu chỉ có dữ liệu mô phỏng cần ghi rõ tình trạng đó, không trình bày thành kết quả rà doanh nghiệp thực tế.

Gói khóa đúng tập bằng chứng theo manifest. Nếu có tệp thừa, thiếu hoặc sai checksum, dừng nhập gói và kiểm tra nguồn; cần tạo lượt so sánh mới khi thay tập bằng chứng.

## 7. Kịch bản demo 15–20 phút

Để thử **nhập/lưu, kích hoạt và xác nhận phiếu**, dùng bộ mô phỏng riêng ở mục 9–10. Nếu chỉ giới thiệu workspace hiện có, có thể xem cấu hình và xem trước tệp rồi dừng trước bước xác nhận thay thế.

### Chuẩn bị

- Mở sẵn bốn địa chỉ ở mục 1 trên cùng cổng 8765.
- Dùng bộ **003**, C001 và C002. Với demo mới, chuẩn bị `SIMULATED_C001.csv`, `SIMULATED_C002.xlsx` và `SIMULATED_C001_ERRORS.csv` tạo ở mục 9.
- Ghi số dòng, số nhãn và phiên bản đang dùng của từng công ty trước khi thao tác. Bản hợp nhất local ngày 07/11 có 30 giao dịch mỗi công ty, C001 dùng Isolation Forest, C002 dùng ECOD; trạng thái có thể thay đổi sau các lần sử dụng.

| Bước | Thao tác trình bày | Kết quả cần kiểm tra |
| --- | --- | --- |
| 1 · Tổng quan | Mở trang hồ sơ, chuyển qua nhập dữ liệu, ML và phiếu rà | Tất cả cùng cổng 8765 |
| 2 · Chặn lỗi | Chọn C001, tải `SIMULATED_C001_ERRORS.csv`, bấm kiểm tra | Báo mã giao dịch trùng, tiền sai định dạng và thời gian sai; chưa lưu dữ liệu lỗi |
| 3 · Nhập đúng | Đổi sang `SIMULATED_C001.csv`, xem trước và xác nhận lưu | 30 giao dịch, 194 feature, chuyển sang ML của C001 |
| 4 · C001 | Chọn Isolation Forest, đặt kỳ dưới đây, đánh giá → xác nhận vN → chấm | Model đang dùng đúng IF; chấm phần ngoài train/calibration |
| 5 · C002 | Nhập `SIMULATED_C002.xlsx`, chọn ECOD, đánh giá → xác nhận → chấm | C002 dùng ECOD; lựa chọn C001 vẫn giữ nguyên |
| 6 · Lưu cấu hình | Tải lại trang, đổi C001/C002 | Hai model vẫn cố định đúng từng doanh nghiệp |
| 7 · Cập nhật lại | Trong bộ demo riêng, nhập lại đầy đủ tệp C001 cùng định dạng | Model đang dùng giữ cùng phiên bản; nút chấm mở nếu còn tương thích. Nhãn của tập thay thế bị xóa theo cảnh báo |
| 8 · CatBoost | Xem lựa chọn CatBoost khi chưa có nhãn train | Bị khóa và giải thích thiếu điều kiện |
| 9 · Phiếu rà | Dùng gói tạo ở mục 10, bắt đầu đo, ghi căn cứ, lưu nháp rồi tải lại | Nháp và thời gian đã xác nhận được giữ; xác nhận kết quả chỉ sau khi trực tiếp rà |

**Kỳ dùng cho 30 dòng mẫu từ 01–30/01/2024:**

| Trường trên web | Giá trị giờ Việt Nam | Số dòng mỗi công ty |
| --- | --- | ---: |
| Cuối kỳ train | `19/01/2024 12:00` | Train: 18 |
| Cuối kỳ calibration | `25/01/2024 12:00` | Calibration: 6 |
| Tỷ lệ cảnh báo tham chiếu | `10` (%) | Evaluation: 6 |

Trình duyệt có thể hiển thị thứ tự ngày/tháng khác theo ngôn ngữ máy; kiểm tra đúng **19 tháng 1** và **25 tháng 1**. Tỷ lệ calibration 10% khác với ngân sách **5 giao dịch/model/doanh nghiệp** của gói so sánh. Danh sách top 5 có thể chứa giao dịch dưới ngưỡng; không gọi toàn bộ top 5 là cảnh báo vượt ngưỡng.

Gói local đã khóa có **40 vị trí chọn** (2 doanh nghiệp × 4 model × 5), gộp thành **12 giao dịch duy nhất**. Bốn model là IF, Autoencoder, ECOD và LOF; CatBoost bị bỏ qua do thiếu nhãn train. Để kết luận model phù hợp hơn cần kết quả hữu ích và thời gian kiểm tra của người rà trên cùng kỳ và cùng ngân sách; dữ liệu mô phỏng này chưa chứng minh chất lượng trên doanh nghiệp thật.

**Kiểm tra kịch bản ngày 07/11/2026:** đã tạo tệp theo script trong tài liệu trên database tạm; mẫu lỗi báo đúng 3 lỗi; CSV C001 và Excel C002 đều nhập 30 dòng/194 feature; IF và ECOD train/calibration/evaluation đúng 18/6/6 và chấm 6 dòng. Nhập lại giữ phiên bản đang dùng. Gói so sánh tạo đủ 8 kết quả model, 40 vị trí chọn và 12 phiếu duy nhất, qua kiểm tra manifest. Lượt kiểm tra này chạy qua backend trên dữ liệu tạm.

## 8. Xử lý tình huống thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không mở được 8765 | Chạy launcher ở mục 1, chờ thông báo sẵn sàng. Xem `.runtime/review/server_8765.err.log` nếu khởi động lỗi |
| Cổng đã có phiên khác | Dừng đúng phiên sở hữu cổng trước khi chạy phiên mới. Launcher chỉ dừng phiên khớp bản ghi; tránh dừng tiến trình theo số PID cũ |
| Nút chọn tệp bị khóa | Đọc thông báo cạnh ô tệp. Chờ tải doanh nghiệp, chọn doanh nghiệp có quyền nhập; dùng **Thử tải lại dữ liệu nhập** hoặc **Tải lại danh mục** khi lỗi kết nối |
| Excel bị từ chối | Kiểm tra đúng một sheet, không công thức, mã ở dạng Text; máy chủ cần `requirements-data-import.txt` |
| Mã không thuộc danh mục | Kiểm tra doanh nghiệp, mã và thời điểm tồn tại trong nguồn danh mục. Tệp giao dịch không tự tạo nhân viên/NCC/khách hàng |
| Bản xem trước hết hạn hoặc dữ liệu đã đổi | Tải lại đúng doanh nghiệp và kiểm tra tệp lại trước khi lưu |
| Không đánh giá được | Kiểm tra tối thiểu 5/2/2 dòng theo thời gian và lý do trên màn hình; CatBoost còn cần nhãn và thư viện |
| Nút chấm bị khóa | Đọc lý do kiểm tương thích. Kiểm tra có phiên bản đang dùng, đúng bộ dữ liệu, định dạng/feature phù hợp và giao dịch ngoài kỳ học |
| Precision/recall báo chưa đủ nhãn | Cần nhãn evaluation đã xác minh; số cảnh báo không thay thế được chỉ số này |
| Chưa thấy phiếu rà | Cần gói so sánh hợp lệ được cấu hình tại máy chủ và đúng phạm vi doanh nghiệp; làm mục 10 với demo mới |
| Tổng hợp chưa hiện tên model | Hoàn tất toàn bộ phiếu trong phạm vi và dùng tài khoản có quyền quản lý |
| Báo phiên thay đổi/xung đột | Tải lại trạng thái, kiểm tra dữ liệu đã lưu trước khi thao tác lại; ứng dụng không tự gửi lại thao tác ghi |

## 9. Dựng demo riêng từ bản Git

Phần này dành cho người cài đặt. Dùng Python **3.12** và PowerShell. Nếu dùng ngay máy đang chạy workspace chính, dừng phiên đó bằng launcher trước; vẫn chỉ dùng một cổng 8765. Các tệp dưới đây nằm trong thư mục mới và không dùng database của workspace chính.

### 9.1. Clone và cài môi trường

```powershell
git clone --branch agent2-Sang --single-branch https://github.com/Khanhhh239/Multi-Agent-Finance.git Agent2-Sang-demo
Set-Location Agent2-Sang-demo
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt -r requirements-data-import.txt
$env:PYTHONPATH = "$PWD;$PWD/tests"
$env:PYTHONDONTWRITEBYTECODE = '1'
```

Tùy chọn, nếu muốn thử điều kiện và train CatBoost khi có đủ nhãn:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-company-ml.txt
```

### 9.2. Tạo dữ liệu mô phỏng và tệp để tải lên

Chạy tại thư mục clone. Script dừng nếu thư mục đích đã tồn tại để giữ nguyên lần demo trước; muốn bắt đầu bộ mới thì đổi đường dẫn demo nhất quán ở các lệnh sau.

```powershell
@'
from pathlib import Path
from test_data_import import import_fixture, upload_rows, csv_bytes, xlsx_bytes

root = Path('.runtime/huong_dan_demo_20261107')
if root.exists():
    raise FileExistsError('Chon thu muc demo moi; khong ghi de du lieu cu.')
root.mkdir(parents=True)
store, _ = import_fixture(root)
store.prepare()
for company in ('C001', 'C002'):
    rows = upload_rows(company, count=30)
    (root / f'SIMULATED_{company}.csv').write_bytes(csv_bytes(rows))
    (root / f'SIMULATED_{company}.xlsx').write_bytes(xlsx_bytes(rows))

bad = upload_rows('C001', count=30)
bad[1]['transaction_id'] = bad[0]['transaction_id']
bad[2]['amount_vnd'] = '1,000,000'
bad[3]['approved_at'] = '2023-12-31 09:00'
(root / 'SIMULATED_C001_ERRORS.csv').write_bytes(csv_bytes(bad))
print('Demo files:', root.resolve())
'@ | .\.venv\Scripts\python.exe -B -
```

### 9.3. Chạy server demo

```powershell
.\.venv\Scripts\python.exe -B -m sme_fraud.review_server `
  --data-root .runtime/huong_dan_demo_20261107/data `
  --reports-root .runtime/huong_dan_demo_20261107/reports `
  --database .runtime/huong_dan_demo_20261107/review.sqlite3 `
  --port 8765 --qa --demo-ml-manager
```

Giữ cửa sổ này mở. Vào `/data-import`, nhập CSV của C001 và Excel của C002 từ thư mục vừa tạo, rồi làm kịch bản ở mục 7. Đây là dữ liệu mô phỏng, không có nhãn gian lận thực tế; model và phiếu rà chưa tồn tại cho đến khi được tạo.

Server trực tiếp ở mục này dừng bằng **Ctrl+C** trong cửa sổ chạy lệnh. Chạy lại cùng lệnh sẽ dùng lại database demo. Cờ `--demo-ml-manager` yêu cầu `--qa`; dùng cho demo local. Launcher workspace chính và server demo này là hai cách khởi động khác nhau; chọn cách phù hợp với database muốn mở.

## 10. Tạo gói so sánh để demo phiếu rà

Thực hiện sau khi đã nhập đủ 30 giao dịch cho **cả C001 và C002** ở mục 9. Dừng server demo bằng Ctrl+C; trong cùng cửa sổ PowerShell đã đặt `PYTHONPATH`, chạy:

```powershell
.\.venv\Scripts\python.exe -B -m sme_fraud.company_ml_comparison run `
  --database .runtime/huong_dan_demo_20261107/review.sqlite3 `
  --output .runtime/huong_dan_comparison_20261107/run_01 `
  --companies C001 C002 --scenario 003 `
  --train-start 2024-01-01T00:00:00+07:00 `
  --train-end 2024-01-19T12:00:00+07:00 `
  --calibration-end 2024-01-25T12:00:00+07:00 `
  --evaluation-end 2024-01-31T00:00:00+07:00 `
  --review-count 5 --calibration-rate 0.1 --source-kind synthetic_demo
```

Lượt này so sánh cùng kỳ và tối đa 5 giao dịch/model/doanh nghiệp, ghi gói ra thư mục riêng, không tự thay model đang dùng. Thư mục kết quả phải tách khỏi cây thư mục chứa database/nguồn. Nếu kết quả đã có, dùng tên mới như `run_02`. Giữ nguyên nội dung gói đã khóa sau khi tạo.

Chạy lại server với cùng database và thêm gói vừa tạo:

```powershell
.\.venv\Scripts\python.exe -B -m sme_fraud.review_server `
  --data-root .runtime/huong_dan_demo_20261107/data `
  --reports-root .runtime/huong_dan_demo_20261107/reports `
  --database .runtime/huong_dan_demo_20261107/review.sqlite3 `
  --port 8765 --qa --demo-ml-manager `
  --ml-review-comparison .runtime/huong_dan_comparison_20261107/run_01
```

Mở http://127.0.0.1:8765/ml-reviews và thực hiện mục 6. Xuất CSV từ web để lấy các kết quả đã lưu trong database; file `human_reviews.csv` trong gói nguồn không tự được cập nhật theo web.

Khi muốn quay lại workspace chính trên máy hiện tại, dừng server demo bằng Ctrl+C, trở về `D:\agent22` và chạy `python -B start_review.py`. Giữ lại thư mục demo nếu cần tiếp tục các model/phiếu đã lưu.

## 11. Tài liệu tra cứu

- [Cài đặt, phạm vi bản Git và kiểm thử](AGENT2_GITHUB.md).
- [Biên bản hợp nhất về cổng 8765](reports/app/unified_local_20261107.md).
- [Chi tiết nhập CSV/Excel](reports/ml/data_import_20261104.md).
- [Điều kiện CatBoost và kiểm tương thích model](reports/ml/company_ml_readiness_20261105.md).
- [Ghép nhãn và xử lý xung đột](reports/ml/company_ml_labels_20261106.md).
- [So sánh cùng kỳ và cùng ngân sách](reports/ml/company_ml_comparison_20261104.md).
- [Phiếu rà web và bộ đếm thời gian](reports/ml/ml_review_web_20261105.md).
- [Khóa tập bằng chứng của gói phiếu](reports/ml/ml_review_packet_lock_20261106.md).

Các biên bản cũ có thể nhắc cổng demo lịch sử; địa chỉ dùng theo hướng dẫn hiện tại là **8765**.
