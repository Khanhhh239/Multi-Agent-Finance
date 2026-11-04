# Chọn pipeline ML riêng cho doanh nghiệp

Trong web, mở **Dữ liệu & ML** hoặc `/company-ml`:

1. Chọn doanh nghiệp và bộ dữ liệu.
2. **Cập nhật & kiểm tra dữ liệu**: nạp cache nguồn đã kết nối vào không gian ML riêng. Model đang dùng không đổi.
3. Chọn thuật toán, kỳ train/calibration và tỷ lệ cảnh báo tham chiếu; chạy đánh giá ứng viên.
4. Đối chiếu kết quả rồi **Xác nhận dùng vN**. Ứng viên chưa được xác nhận không thay model đang dùng.
5. Chạy ML bằng phiên bản đang dùng. Có thể chọn giữ phiên bản hoặc quay lại một phiên bản từng kích hoạt.

Kế toán trưởng/giám đốc được máy chủ xác thực và cấp đúng công ty mới được ghi. Kế toán viên được xem trong phạm vi công ty. Không nhận vai trò/danh tính từ JSON hoặc các header do giao diện tự đặt. Khi chưa có tích hợp đăng nhập, bản app thông thường chỉ xem cấu hình; demo bên dưới cấp danh tính QA cố định riêng.

## Cài thư viện

Dùng CPython 3.12 và môi trường review đã chọn:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt
# Bổ sung khi muốn sử dụng CatBoost:
.\.venv\Scripts\python.exe -m pip install -r requirements-company-ml.txt
$env:PYTHONPATH = "$PWD;$PWD/tests"
```

Bốn adapter đầu sử dụng numpy/scipy/sklearn của môi trường hiện tại. CatBoost là phụ thuộc tùy chọn; giao diện hiện rõ khi chưa cài. Không tự thay CatBoost bằng thuật toán khác.

## Nguồn đầu vào

Bước cập nhật trên web đọc `data_root/sme_fraud_<scenario>/` được cấu hình ở máy chủ. Cần `manifest.json`, `transactions.csv`, `features.csv` đúng hợp đồng feature hiện tại, checksum hợp lệ và ID khớp. Đây là cập nhật từ nguồn đã kết nối, chưa phải màn hình upload CSV kế toán thô hoặc kết nối ERP. Dữ liệu từng doanh nghiệp được lọc theo `company_id`; holdout 005 bị từ chối trước khi đọc.

Web không tự sửa nguồn, dựng lại feature hoặc sửa snapshot detector. Cache cũ cần được dựng lại bằng quy trình nguồn phù hợp trước khi nạp. Những thiếu hụt bằng chứng đã được mã hóa trong hợp đồng feature được giữ nguyên.

CSV nhãn tùy chọn chọn tại bước cập nhật có đúng các cột:

```csv
company_id,transaction_id,label,reviewer_id,reviewed_at,evidence_ref,verified
```

`label=0`: hợp lệ; `label=1`: gian lận đã xác nhận. `verified=1`; người rà và căn cứ không trống; thời điểm rà có múi giờ, sau giao dịch và không ở tương lai. Chỉ nhập nhãn thuộc công ty/giao dịch hiện có, không trùng. Nguồn nhãn này do bên nhập chịu trách nhiệm xác nhận; phần mềm không biến việc tải CSV thành nghiệm thu độc lập. Không tự đọc `labels.csv`, `splits.csv`, oracle hoặc biến điểm luật thành nhãn.

Khi cập nhật mà không chọn tệp nhãn, chỉ giữ nhãn cũ nếu cùng bộ dữ liệu, cùng hợp đồng và giao dịch/feature không đổi. CatBoost cần đủ hai lớp trong train, nhãn cho mọi dòng train và thời điểm biết nhãn trước cuối kỳ train. Precision/recall chỉ được tính trên các dòng evaluation đã có nhãn; thiếu mẫu số giữ null và không suy rộng thành chất lượng thực địa.

## Năm pipeline

| Thuật toán | Tiền xử lý / điểm |
| --- | --- |
| Isolation Forest | Fit trên train, 100 cây, điểm đối dấu `score_samples` |
| Autoencoder | StandardScaler fit trên train; MLP tái tạo qua lớp nén, điểm MSE; cảnh báo khi chưa hội tụ |
| ECOD | Biến thể tham chiếu cố định: ECDF hai đuôi và độ lệch học từ train; không gộp batch mới vào ECDF |
| LOF | StandardScaler fit trên train; `novelty=True`, chỉ chấm ngoài train/calibration |
| CatBoost | Phân loại hai lớp bằng nhãn đã xác minh; điểm xác suất lớp 1 |

ECOD tham khảo [công trình gốc](https://arxiv.org/abs/2201.00382) và [PyOD](https://pyod.readthedocs.io/en/latest/_modules/pyod/models/ecod.html); khác PyOD ở việc cố định phân phối train khi suy luận. Autoencoder dùng [MLPRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html); LOF dùng [chế độ novelty](https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.LocalOutlierFactor.html).

Train trước ranh giới đầu; calibration giữa hai ranh giới; evaluation sau ranh giới cuối. Ngưỡng là quantile `higher` của calibration theo ngân sách tham chiếu; cảnh báo khi điểm **lớn hơn** ngưỡng. Giá trị bằng ngưỡng không tự thành cảnh báo, nên trường hợp nhiều điểm bằng nhau có thể không đạt đúng tỷ lệ tham chiếu. Evaluation không fit model, scaler hoặc chọn ngưỡng. Không tự gọi model ít cảnh báo hơn là model tối ưu.

Web giới hạn 100.000 dòng nguồn/công ty và 20.000 dòng train/lượt; ít nhất 5 train, 2 calibration và 2 evaluation. Huấn luyện chạy đồng bộ với thông báo đang xử lý; một lượt/mỗi instance máy chủ. Không có hàng đợi huấn luyện nền hoặc tự tiếp tục một lượt bị dừng khi restart. Khi mất kết nối, tải lại cấu hình để kiểm tra ứng viên đã được lưu; giao diện không tự lặp POST.

## Cố định và lưu trữ

Các bảng `company_ml_*` trong cùng SQLite lưu snapshot ML, nhãn đã nhập, artifact gồm tiền xử lý/model/ngưỡng, phiên bản, binding theo doanh nghiệp, lịch sử hash chain và kết quả từng lượt. Artifact do máy chủ tạo, lưu SHA256 và phiên bản Python/numpy/sklearn/joblib/CatBoost tương ứng. Không có endpoint nạp pickle/joblib của người dùng.

Cập nhật dữ liệu không đổi binding và không fit. Kích hoạt ứng viên cần đúng revision đã đánh giá; thay đổi ở tab khác bị từ chối. Quay lại chỉ cho phiên bản từng dùng, cùng công ty và còn tương thích. Khi đổi bộ dữ liệu, phải cập nhật bộ đang chọn trước khi đánh giá/chạy. Chấm chỉ lấy giao dịch sau calibration của phiên bản; không chấm lại train/calibration. Kết quả hiện ở shadow, không ghi đè hàng đợi, luật, graph, A5, kết luận hay outbox.

Backup/restore SQLite hiện có giữ cả artifact và cấu hình; đã có kiểm thử khôi phục rồi chấm cùng kết quả. Máy khôi phục cần đúng môi trường và cài CatBoost nếu phiên bản đó sử dụng nó. Lịch sử cấu hình chỉ là nhật ký kỹ thuật, không xác nhận chất lượng ML hoặc kết luận kế toán.

## Demo cách ly

```powershell
.\.venv\Scripts\python.exe -B tests/company_ml_demo.py --port 8851
```

- `http://127.0.0.1:8851/company-ml`: kế toán trưởng mô phỏng, hai công ty C001/C002.
- `http://127.0.0.1:8852/company-ml`: kế toán viên mô phỏng, chỉ xem C001.
- Dữ liệu/database nằm riêng trong `.runtime/company_ml_demo_20261104/`. CSV nhãn **mô phỏng** để thử CatBoost được tạo tại đó, không phải nhãn thực địa.

Launcher từ chối ghi đè một workspace không có marker QA đúng loại, không đụng database demo hiện hành và chỉ bind loopback. Giữ cửa sổ chạy server mở trong khi sử dụng.

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_company_ml test_company_ml_web -v
node --test tests/company_ml_ui.test.js
```

Kiểm chứng bản triển khai ngày 04/11/2026: 88 test Python liên quan (gồm 26 test Company ML/API mới), 116 kiểm tra JavaScript trong 10 bộ (12 kiểm tra Company ML mới), không lỗi/skip. Cả năm adapter đã fit, serialize/nạp lại và chấm bằng code thật trên fixture; CatBoost 1.2.10 được cài trong môi trường test cục bộ. API, luồng DOM và giữ bản nháp khi mất kết nối đã kiểm tra tự động. Chưa xác minh trực quan Chrome/viewport do công cụ điều khiển trình duyệt lỗi điều hướng; không gộp kết quả này với nghiệm thu Chrome lịch sử của app cũ.
