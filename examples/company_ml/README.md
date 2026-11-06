# Chọn pipeline ML riêng cho doanh nghiệp

Phiên local dùng chính hiện tại: **http://127.0.0.1:8765/company-ml**, nhập tệp tại `/data-import`, phiếu rà tại `/ml-reviews`. Chạy lại bằng `python -B start_review.py`; cấu hình lưu sẵn trên máy này. Các cổng demo riêng trong phần lịch sử đã dừng sau [lượt hợp nhất 07/11](../../docs/reports/app/unified_local_20261107.md).

Phiếu rà đã có trên **`/ml-reviews`**: xem dữ kiện không lộ tên model, ghi căn cứ/hành động, đo thời gian có tạm dừng và lưu kết quả theo người rà. [Hướng dẫn và cấu hình gói](../../docs/reports/ml/ml_review_web_20261105.md).

Để so sánh các thuật toán trên **cùng kỳ và cùng số giao dịch rà** của từng doanh nghiệp, dùng [runner so sánh và phiếu ghi nhận hữu ích/phút kiểm tra](../../docs/reports/ml/company_ml_comparison_20261104.md). Lượt demo đã chạy bốn thuật toán cho C001/C002; CatBoost không chạy vì thiếu nhãn train đủ điều kiện. Kết quả hữu ích và thời gian người rà còn chờ phiếu thực tế, không suy từ số cảnh báo hoặc thời gian máy chạy.

Trong web, mở **Dữ liệu & ML** hoặc `/company-ml`:

1. Chọn doanh nghiệp và bộ dữ liệu.
2. Chọn **Nhập dữ liệu từ CSV / Excel** để tải giao dịch, kiểm tra lỗi, chuẩn hóa và tạo feature trước khi lưu; hoặc **Cập nhật & kiểm tra dữ liệu** để nạp cache nguồn đã kết nối. Model đang dùng không đổi. [Quy trình nhập và giới hạn](../../docs/reports/ml/data_import_20261104.md).
3. Chọn thuật toán, kỳ train/calibration và tỷ lệ cảnh báo tham chiếu; chạy đánh giá ứng viên.
4. Đối chiếu kết quả rồi **Xác nhận dùng vN**. Ứng viên chưa được xác nhận không thay model đang dùng.
5. Chạy ML bằng phiên bản đang dùng. Có thể chọn giữ phiên bản hoặc quay lại một phiên bản từng kích hoạt.

Kế toán trưởng/giám đốc được máy chủ xác thực và cấp đúng công ty mới được ghi. Kế toán viên được xem trong phạm vi công ty. Không nhận vai trò/danh tính từ JSON hoặc các header do giao diện tự đặt. Khi chưa có tích hợp đăng nhập, bản app thông thường chỉ xem cấu hình; demo bên dưới cấp danh tính QA cố định riêng.

Giao diện kiểm tra điều kiện từ backend khi đổi kỳ train/calibration hoặc dữ liệu: CatBoost chỉ mở nếu mọi dòng train có nhãn đã xác minh, biết trước ranh giới và có cả hai lớp; nút chấm/giữ bị khóa nếu model không tương thích. Có lý do và độ phủ nhãn hiển thị ngay trên form. [Chi tiết và kiểm thử ngày 05/11](../../docs/reports/ml/company_ml_readiness_20261105.md). Cần khởi động lại server cũ để có API kiểm tra mới.

## Cài thư viện

Dùng CPython 3.12 và môi trường review đã chọn:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt
# Bổ sung khi muốn sử dụng CatBoost:
.\.venv\Scripts\python.exe -m pip install -r requirements-company-ml.txt
# Bổ sung để nhập Excel .xlsx (CSV dùng thư viện chuẩn):
.\.venv\Scripts\python.exe -m pip install -r requirements-data-import.txt
$env:PYTHONPATH = "$PWD;$PWD/tests"
```

Bốn adapter đầu sử dụng numpy/scipy/sklearn của môi trường hiện tại. CatBoost là phụ thuộc tùy chọn; giao diện hiện rõ khi chưa cài. Không tự thay CatBoost bằng thuật toán khác.

## Nguồn đầu vào

Bước cập nhật nguồn kết nối đọc `data_root/sme_fraud_<scenario>/` được cấu hình ở máy chủ. Cần `manifest.json`, `transactions.csv`, `features.csv` đúng hợp đồng feature hiện tại, checksum hợp lệ và ID khớp. Để nhập giao dịch CSV/Excel theo mẫu, mở `/data-import`: xem lỗi và bản chuẩn hóa trước khi xác nhận thay thế toàn bộ tập ML của doanh nghiệp. Luồng nhập dùng danh mục kết nối, chưa tự ánh xạ ERP hoặc nhập thêm lịch sử bằng chứng. Dữ liệu từng doanh nghiệp được lọc theo `company_id`; holdout 005 bị từ chối trước khi đọc.

Luồng nạp nguồn kết nối không sửa nguồn hoặc dựng lại feature. Luồng CSV/Excel tạo feature cho tập nhập trong không gian ML riêng, không sửa snapshot detector. Cache kết nối cũ vẫn cần dựng lại bằng quy trình nguồn phù hợp trước khi nạp. Những thiếu hụt bằng chứng được giữ nguyên và nêu trước khi lưu.

CSV nhãn tùy chọn chọn tại bước cập nhật có đúng các cột:

```csv
company_id,transaction_id,label,reviewer_id,reviewed_at,evidence_ref,verified
```

`label=0`: hợp lệ; `label=1`: gian lận đã xác nhận. `verified=1`; người rà và căn cứ không trống; thời điểm rà có múi giờ, sau giao dịch và không ở tương lai. Chỉ nhập nhãn thuộc công ty/giao dịch hiện có, không trùng. Nguồn nhãn này do bên nhập chịu trách nhiệm xác nhận; phần mềm không biến việc tải CSV thành nghiệm thu độc lập. Không tự đọc `labels.csv`, `splits.csv`, oracle hoặc biến điểm luật thành nhãn.

Khi cập nhật từ nguồn kết nối, chỉ giữ nhãn cũ nếu cùng bộ dữ liệu, cùng hợp đồng và giao dịch/feature không đổi; CSV nhãn kèm theo được gộp và bị chặn nếu xung đột. Khi thay thế tập giao dịch CSV/Excel, nhãn cũ không được giữ. Để bổ sung nhãn cho tập ML hiện hành, chọn CSV nhãn ở bước 1, xem trước rồi bấm **Lưu nhãn**: giao dịch/feature/model đang dùng giữ nguyên, các nhãn không có trong tệp được giữ lại. Nhãn trùng cả kết luận và nguồn rà không tạo revision mới. Khác kết luận, người rà, thời điểm hoặc căn cứ là xung đột: chọn giữ nhãn cũ hoặc sửa theo tệp, nhập lý do và xác nhận. Xem trước hết hiệu lực khi nội dung CSV hoặc revision thay đổi; tệp rỗng không xóa nhãn. [Chi tiết bản sửa 06/11](../../docs/reports/ml/company_ml_labels_20261106.md).

CatBoost cần đủ hai lớp trong train, nhãn cho mọi dòng train và thời điểm biết nhãn trước cuối kỳ train. Precision/recall chỉ được tính trên các dòng evaluation đã có nhãn; thiếu mẫu số giữ null và không suy rộng thành chất lượng thực địa.

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

Kiểm chứng bản triển khai ngày 04/11/2026: 88 test Python liên quan (gồm 26 test Company ML/API mới), 116 kiểm tra JavaScript trong 10 bộ (12 kiểm tra Company ML mới), không lỗi/skip. Cả năm adapter đã fit, serialize/nạp lại và chấm bằng code thật trên fixture; CatBoost 1.2.10 được cài trong môi trường test cục bộ. API, luồng DOM và giữ bản nháp khi mất kết nối đã kiểm tra tự động. Sau đó đã chạy **50 kiểm tra trên Chrome headless qua Playwright**, gồm thao tác web cho C001/IF v3, C002/ECOD v1, dữ liệu nguồn tăng thật một dòng mỗi công ty, giữ model/điểm cũ khi cập nhật và reload, viewport desktop/390px và quyền chỉ xem. [Biên bản và bằng chứng cục bộ](../../docs/reports/ml/company_ml_demo_20261104.md). Phạm vi hai luồng này không thay cho nghiệm thu toàn app, trình duyệt khác hoặc dữ liệu thật.
