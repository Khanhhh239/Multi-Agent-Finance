# Phương pháp Rule Audit

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

Mục tiêu là xác định mỗi rule đang phát hiện gì, tạo bao nhiêu cảnh báo trên dòng hợp lệ, có khớp mô tả trong `rule_class_1.md` không và góp thêm bao nhiêu cảnh báo vào hàng đợi. Đợt này giữ nguyên bộ luật, ngưỡng và ba bộ dữ liệu v2; không train hoặc chấm mô hình ML.

## Phạm vi

| Đơn vị | Số rule chính | Cách đánh giá |
| --- | ---: | --- |
| Giao dịch có implementation | 20 | TP/FP/precision/FPR, bao phủ kịch bản, ngoại lệ, đối chứng logic |
| Chẩn đoán tập/cửa sổ Benford D1–D6 | 6 | Số cửa sổ đủ điều kiện, bỏ qua, phát tín hiệu; chưa có nhãn cấp tập để tính precision |
| Thiếu nguồn hoặc implementation | 5 | C4/E2/F2/F3/F4: N/A, không coi số hit 0 là đúng 100% |
| P1/T1/T2 | Phụ lục ngoài 31 | Báo cáo riêng; giữ trong baseline hàng đợi hiện tại |

Mỗi bộ có 100.000 quan sát, tỷ lệ gian lận mô phỏng 0,1%/0,3%/0,5%; cùng seed nên ba bộ không phải ba mẫu độc lập. Audit giữ các kỳ train 2024, validation nửa đầu 2025 và test nửa cuối 2025. Báo cáo theo công ty và TT133/TT200 có trong JSON.

## Chỉ số và nhãn

- **Hit độc lập**: rule còn điểm sau ngoại lệ. Hit thấp điểm vẫn được tính khi đánh giá riêng rule.
- **TP/FP theo ý đồ gian lận**: hit trên dòng nhãn `is_fraud=1/0`. Nhãn này chưa xác nhận có/không có mọi vi phạm nghiệp vụ; một hit trên dòng 0 chưa đủ chứng minh predicate sai.
- **Precision**: TP/(TP+FP). Không có hit thì N/A.
- **FPR**: FP/(FP+TN). Báo cáo cả toàn tập và phạm vi đầu vào của rule; không dùng tổng số hit làm mẫu số.
- **Bao phủ kịch bản**: tỷ lệ dòng/vụ gian lận thuộc family/variant đã khai báo bị rule bắt. Đây là proxy theo nhãn kịch bản, chưa phải sensitivity của điều kiện rule được gán nhãn độc lập. Các dòng ngữ cảnh mang nhãn 0 không được biến thành TP.
- **Hard negatives**: 13 loại nghiệp vụ hợp lệ, đo hit còn điểm và số ngoại lệ đã loại riêng từng loại.
- **Ngoại lệ**: ghi lại số ứng viên trước/sau loại và số dòng gian lận bị loại nhầm.
- **95% Wilson**: khoảng mô tả precision theo dòng, không hiệu chỉnh tương quan giữa các dòng cùng vụ/NCC. Không dùng khoảng này để khẳng định chất lượng thực địa.

Accuracy tổng thể chỉ để đối soát. Với gian lận 0,1%, rule không cảnh báo gì vẫn có accuracy xấp xỉ 99,9%, nên chỉ số này không phù hợp để xếp hạng.

Nguồn định nghĩa: [precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_score.html), [recall](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.recall_score.html). Bộ audit tự tính bằng thư viện chuẩn Python; không gọi sklearn để chấm điểm.

## Kiểm tra bằng chứng và đóng góp vào hàng đợi

Audit đối chiếu SHA-256 dữ liệu nguồn với manifest, khóa giao dịch/nhãn/kỳ, thời gian bằng chứng, ngoại lệ có điểm 0 và phát lại toàn bộ điểm đã lưu. Các giao dịch cùng timestamp không thấy nhau; điểm tái diễn chỉ dùng cảnh báo trước đó trong 30 ngày.

Đối chứng bỏ từng rule giữ nguyên hit của các rule khác, gộp max theo nhóm tương quan như engine và **tính lại lịch sử tái diễn**. Ngưỡng vận hành cố định là 7; không chọn ngưỡng mới theo test. Kết quả là số FP giảm và TP mất trong hàng đợi, khác với số FP độc lập của rule.

Các delta bỏ rule không cộng được với nhau do rule chồng lặp và max theo nhóm. Bỏ hai rule cùng lúc cần chạy đối chứng riêng. B5/E4/E3 hiện chung nhóm điểm, nên hit trùng không tự tạo thêm ba lần điểm.

Sáu rule D không cộng điểm giao dịch. Cửa sổ chẩn đoán được gán kỳ theo ngày kết thúc cửa sổ đã đóng: cutoff 01/07/2025 thuộc validation, cutoff 01/01/2026 thuộc test. Không gán một cửa sổ là gian lận chỉ vì chứa một dòng gian lận.

## Đối chứng nghiệp vụ độc lập

51 tình huống nằm ngoài dữ liệu đánh giá, chạy qua chứng từ nguồn, template kế toán và engine thật. Kỳ vọng được khai báo trước khi chấm; không tạo feature giả để ép rule kích hoạt. Mỗi trong 20 rule giao dịch có ít nhất một tình huống dương và một tình huống âm.

`scope` phân biệt kỳ vọng nghiệp vụ (`business_expectation`), mô tả literal cần thống nhất (`literal_spec`), tính thời gian (`causal_temporal`) và thay đổi có chủ đích để phù hợp hard negatives (`documented_adaptation`). Kết quả lệch là phát hiện audit; không che bằng việc thay đổi kỳ vọng theo output.

Không chia số fixture khớp cho tổng fixture để gọi đó là precision thực tế. Fixture không thay thế mẫu gian lận dương riêng cho A5/A6/B6/B7/C1/C3/E3, dữ liệu SME thật hoặc nhãn cấp tập cho D1–D6.

## Chạy và đọc kết quả

Chỉ cần Python 3.10+ và thư viện chuẩn:

```powershell
python -m sme_fraud.rule_audit --output reports/rule_audit_new
python -m unittest discover -s tests -p test_rule_audit.py -v
```

Trong máy này có thể gọi Python tại:

```powershell
& 'C:\Users\Technical Support\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m sme_fraud.rule_audit --output reports/rule_audit_new
```

CLI không ghi đè thư mục audit có nội dung. Nó đọc `data/sme_fraud_001/003/005` và `reports/rules/sme_fraud_001/003/005`, không sinh lại dataset hoặc chạy benchmark ML. Đây là audit các hit baseline đã lưu; replay xác minh cách gộp điểm, đối chứng xác minh các predicate tại tình huống đã khai báo, chưa phải tái chạy predicate toàn bộ 300.000 dòng.

- [Tổng hợp và bảng đủ 31 rule](../../../reports/rule_audit/summary_vi.md).
- [Ma trận theo tỷ lệ/kỳ/rule](../../../reports/rule_audit/rule_metrics.csv).
- [Ví dụ TP/FP/bỏ sót và bằng chứng](../../../reports/rule_audit/examples.csv).
- [Tác động bỏ rule](../../../reports/rule_audit/ablation.csv).
- [Chồng lặp](../../../reports/rule_audit/overlap.csv).
- [51 đối chứng](../../../reports/rule_audit/controlled_cases.csv).
- [Chi tiết và dấu vân tay nguồn](../../../reports/rule_audit/audit.json).

Test hiện tại đã được xem trong các lượt phát triển trước. Sửa logic/ngưỡng trên train/validation và đối chứng nghiệp vụ; dùng một test mới được giữ kín để nghiệm thu sau tối ưu. [Hướng dẫn tránh rò rỉ dữ liệu](https://scikit-learn.org/stable/common_pitfalls.html).
