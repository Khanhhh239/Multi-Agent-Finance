# Triển khai bộ luật từ rule_class_1.md

File nguồn có **6 nhóm A–F, tổng cộng 31 quy tắc**, cùng yêu cầu gom điểm, SLA và phản hồi hồ sơ. Pipeline mới đọc dữ liệu v2 theo thời điểm `posted_at`; không thay đổi database, nhãn, splits hoặc mô hình IF đã lưu.

## Phạm vi hiện có

- A1/A2 quét 3/30 ngày theo người nhận và người lập; A3 dùng cụm TK/SĐT/người đại diện đã quan sát; A4 đếm khoản 80–99% hạn mức trong tháng lịch (hoặc 30 ngày khi cấu hình tường minh). Tổng gồm giao dịch đang chấm, còn mọi giao dịch ngữ cảnh phải có thời điểm trước đó. A1/A2/A4 chỉ loại nghĩa vụ chi có request/PO/hóa đơn/hợp đồng hoặc lịch định kỳ gắn đúng đối tượng, được duyệt/as-of và tổng đã trả chưa vượt trần; thiếu nguồn giữ cảnh báo hiện tại.
- A5 dùng trung bình/độ lệch chuẩn số tiền lịch sử theo NCC+loại nghiệp vụ, dự phòng bằng công ty+loại; ít nhất 20 mẫu. A6 chỉ cảnh báo thanh toán làm tròn vượt hóa đơn số lẻ, không suy ra gian lận từ số tròn đơn lẻ.
- B1/B2/B5/E4 đối chiếu dữ liệu chủ chuẩn hóa, không ghép giá trị trống. Đồ thị có cạnh và thời điểm quan sát để truy vết NCC → người đại diện → SĐT → nhân viên. Địa chỉ chung đơn lẻ có điểm thấp và không dùng làm cạnh gom thanh toán mạnh.
- B3 cần giao dịch lớn đầu tiên với NCC dưới 90 ngày; ghi nhận ngoại lệ có hồ sơ/giao nhận. B4 chỉ dùng trạng thái đã công bố, phân biệt trạng thái ngày phát hành và ngày thanh toán. B6 cần ít nhất 20 giao dịch trước, ngừng thanh toán 180 ngày và khoản mới trên P90 lịch sử.
- B6 đối chiếu thêm lịch thanh toán năm/mùa đã duyệt và tổng tiền trong đúng lần xuất hiện; lịch sai cửa sổ, tương lai hoặc vượt trần không cấp ngoại lệ. C2/C3 dùng ma trận thẩm quyền đầy đủ/as-of khi coverage được xác nhận; thiếu coverage giữ proxy cũ để tương thích.
- B7 kiểm tra đổi TK trong 14 ngày; callback, thời điểm xác minh và người duyệt độc lập là ngoại lệ. C2 đối chiếu quyền tự duyệt đã biết; C1 là tín hiệu bổ trợ theo giờ/lịch vận hành và cả thời điểm lập/duyệt. C3 xét duyệt dưới 60 giây với khoản thuộc cấp cao theo cấu hình.
- E1 chỉ chạy khi chấm công kỳ lương đã được quan sát; bằng chứng làm việc từ xa là ngoại lệ. E3 dùng `difflib.SequenceMatcher` trên tên chuẩn hóa, là phương pháp gần đúng được công bố trong coverage.
- F1 dùng `txn_type=adjustment` làm đại diện bút toán thủ công, 5 ngày cuối tháng, trọng yếu theo cấu hình công ty hoặc hạn mức người lập. Không kết luận từ cặp tài khoản hoặc cuối tuần đơn lẻ.
- D1–D6 xuất chẩn đoán theo tháng và phân đoạn người lập: tối thiểu mẫu, ít nhất 100 số tiền khác nhau, khoảng giá trị ≥100 lần, không có một mức tiền chiếm >20%, tần suất kỳ vọng mỗi ô ≥5. Đây là các bộ lọc thực dụng, chưa chứng minh tập dữ liệu phù hợp Benford. Kiểm định có hiệu chỉnh BH tại từng mốc thời gian. D4 dùng baseline đuôi số kỳ trước vì số tiền SME có thể được làm tròn tự nhiên. Nhóm D không cộng điểm cho giao dịch riêng lẻ.

Năm rule **C4, E2, F2, F3, F4** chưa đánh giá được: cần lịch nghỉ phép/log thao tác, ngày chấm dứt hợp đồng và chi trả cuối cùng, log ghi đè, sổ đăng ký/hủy số chứng từ, liên kết thu tiền–hóa đơn và giải trình công nợ. Thiếu dữ liệu được ghi `not_evaluable`, không thể hiện thành “0 vi phạm”.

P1/T1/T2 là bổ sung ngoài file nguồn để giữ phạm vi sáu nhóm gian lận ban đầu: thanh toán vượt tổng giá trị cùng hóa đơn (khóa công ty+NCC+số hóa đơn, độc lập ERP invoice_id), tạm ứng quá hạn theo hạn/gia hạn đã biết và xóa nợ thiếu hồ sơ. Thanh toán từng phần chưa vượt hóa đơn và xóa nợ có hồ sơ được xét ngoại lệ.

## Điểm, hồ sơ và phản hồi

Trọng số là chính sách mô phỏng theo mức độ trong file nguồn. Cùng nhóm tín hiệu lấy điểm cao nhất; B5/E4/E3 cùng nhóm để hạn chế cộng trùng. Có tối đa 3 điểm tái diễn từ các cảnh báo trước của cùng đối tượng trong 30 ngày. Tự duyệt, giờ muộn, NCC mới, số tiền tròn hoặc kết quả Benford không tự động xác nhận gian lận.

`operational_score=7` tạo hàng đợi rà soát ban đầu, chưa hiệu chỉnh theo sức chứa của SME. Hồ sơ gộp đối tượng trong 30 ngày từ lúc mở; điểm, mức ưu tiên, người phụ trách gợi ý và lịch sử mở/nâng mức đều được lưu. Snapshot toàn kỳ có thể chứa giao dịch sau lần mở hồ sơ; snapshot không được dùng làm feature hoặc đánh giá cảnh báo tại thời điểm mở.

SLA mô phỏng dùng giờ lịch kể từ lúc mở: cao nhất 24h, cao 48h, trung bình 168h. Đã có [giao diện rà soát cục bộ](review_ui.md); chưa tích hợp lịch công tác đầy đủ, ERP hay gửi thông báo; không đóng băng giao dịch tự động.

Phản hồi do người dùng nhập qua CLI hoặc UI, gồm `confirmed_fraud`, `non_compliance`, `false_positive`, `information_gap`, người rà soát, thời điểm và lý do. Cả hai dùng chung khóa ghi và log có chuỗi hash để phát hiện sửa nội dung; chuỗi hash không phải chữ ký hay hệ thống lưu trữ bất biến. `information_gap` giữ hồ sơ chờ bổ sung. Phản hồi chưa tự động đổi ngưỡng hoặc train lại mô hình.

## Chạy pipeline

Với Python đã cài các dependencies trong requirements.txt:

```powershell
python -m sme_fraud.run_rules --data data/sme_fraud_003 --output reports/rules_new/sme_fraud_003 --if-model reports/sme_fraud_003/isolation_forest.joblib
```

Chạy cả ba tỷ lệ và tổng hợp:

```powershell
.\run_rules_benchmark.ps1 -OutputRoot reports/rules_new
```

Script tìm Python trong PATH hoặc runtime đi kèm; có thể truyền `-PythonExecutable`. Thư mục output phải trống để giữ các lần thử độc lập. Truyền `--config path.json` cho CLI hoặc `-Config path.json` cho script để thay ngưỡng chính sách; các khóa được định nghĩa trong `sme_fraud/rules.py`. Chỉ hiệu chỉnh trên train/validation hoặc phản hồi đã được thẩm định, không dùng nhãn test để chọn luật/trọng số.

Ghi phản hồi thật sau khi rà soát một case:

```powershell
python -m sme_fraud.feedback --report reports/rules/sme_fraud_003 --case-id RC_ID_THUC_TE --decision information_gap --reviewer "Kế toán trưởng" --reason "Cần đối chiếu biên bản giao nhận"
```

Đọc ID thật từ `case_queue.csv`. Lệnh này không gửi thông tin cho người khác và không cập nhật các nhãn mô phỏng.

## Đánh giá

So sánh Rules trực tiếp, IF, Rules+Graph và Rules+Graph+IF. Phương án cuối dùng trọng số đặt trước: 80% thứ hạng luật + 20% thứ hạng IF; phân phối tham chiếu chỉ lấy từ validation. Không chọn mô hình tốt nhất hay hiệu chỉnh trọng số theo test.

Điểm luật rời rạc có nhiều trường hợp bằng nhau. Ngưỡng phân vị validation giữ mọi điểm bằng ngưỡng nên có thể vượt ngân sách. Benchmark bổ sung cùng sức chứa 75 cảnh báo test (0,3% ×25.000), định trước khi đọc nhãn; hòa điểm theo SHA256(transaction_id). Đây là phép đo xếp hạng, không dùng phân vị test để đặt ngưỡng vận hành. AP xử lý hòa điểm theo định nghĩa thư viện; Precision@k có thể nhạy với cách phá hòa.

Các kết quả đo theo giao dịch, từng loại gian lận, hard negatives, chế độ kế toán và vụ việc có nhãn. Recall theo vụ là “ít nhất một quan sát gian lận được cảnh báo”, không phải đánh giá chất lượng gộp hồ sơ. Chưa đo thời gian phát hiện sớm nhất, thử công ty chưa từng thấy hoặc nhiều seed. Cần một tập mới giữ kín và dữ liệu SME thực để nghiệm thu.

Nguồn kỹ thuật kiểm định: [SciPy chisquare](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html). Ngưỡng nghiệp vụ/Benford lấy từ file nguồn và được công bố như cấu hình mô phỏng, không tuyên bố là yêu cầu pháp luật hoặc bằng chứng đủ để kết luận gian lận.

## Kiểm chứng đã chạy

29 kiểm thử đã qua: kế toán, tính tái lập, chống đọc giao dịch/dữ liệu chủ tương lai, giao dịch cùng thời điểm, cách ly nhãn, ngoại lệ hợp lệ, đường đi đồ thị, điều kiện Benford và lưu phản hồi có kiểm tra chuỗi hash. Ba bộ đã chạy và được đối soát 300.000 quan sát: mọi checksum dữ liệu gốc giữ nguyên; bằng chứng giao dịch đều thuộc quá khứ; các cạnh đồ thị đã được quan sát; điểm ngoại lệ, thành viên hồ sơ, AP, quyết định theo ngưỡng và thứ hạng cùng sức chứa khớp file kết quả. Mỗi thư mục báo cáo có `validation.json`.

Xem [kết quả tổng hợp](rules/summary_vi.md). Phương án kết hợp IF mặc định có kết quả thấp hơn bộ luật ở cùng sức chứa trong cả ba bộ; báo cáo giữ nguyên kết quả, không hiệu chỉnh trọng số theo test. Ở bộ 0,3%, Rules+Graph phát hiện 44/75 giao dịch gian lận trong 75 cảnh báo; IF phát hiện 5, tổ hợp phát hiện 30. Ngưỡng nghiệp vụ 7 tạo 2.701 hồ sơ trên toàn kỳ ở bộ này, cần hiệu chỉnh sức chứa trước khi dùng vận hành.
