# Giao diện rà soát tài chính SME — MVP cục bộ

**Cập nhật Sprint 1.4, 18/10/2026:** đã có Cytoscape, hai nút kết luận nhanh, chế độ ưu tiên hôm nay và UI xem trước outbox Email/Zalo. [Phạm vi mới, bản mẫu, cấu hình và kiểm thử](case_management_sprint_1_4.md). Các đoạn mô tả chưa có kênh thông báo bên dưới là trạng thái MVP trước Sprint 1.4; luồng hiện tại đang nghiệm thu giả lập, chưa gửi ra ngoài.

Bước tiếp theo sau bộ luật là đưa cảnh báo thành hồ sơ có thể đối chiếu và ghi nhận kết luận. Giao diện **Sổ Soát** dùng ba snapshot đã kiểm chứng, tổng cộng **8.083 hồ sơ** (2.561 / 2.701 / 2.821 theo các bộ 0,1% / 0,3% / 0,5%). Đây là dữ liệu tổng hợp 2024–2025, chưa phải kết quả pilot tại SME thật.

## Mở và dừng ứng dụng

Trong thư mục dự án, với Python có trong PATH:

```powershell
python start_review.py
```

Mở [http://127.0.0.1:8765](http://127.0.0.1:8765) trong trình duyệt. Trên máy hiện tại, Python đi kèm có thể gọi trực tiếp:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" start_review.py
```

Launcher chạy tiến trình nền không mở cửa sổ phụ và không thay đổi execution policy của PowerShell. UI chỉ cần thư viện chuẩn Python; không phải cài thêm package hay tải thư viện giao diện từ CDN. Mô hình IF và các dependencies ML vẫn dùng khi chạy benchmark.

Dừng tiến trình đã mở bằng launcher:

```powershell
python start_review.py --stop
```

Có thể đổi cổng bằng `--port 8766`; dùng cùng cổng khi dừng. Launcher kiểm tra mã định danh phiên dịch vụ trước khi gửi yêu cầu dừng. Nếu muốn chạy trực tiếp trong terminal và dừng bằng Ctrl+C:

```powershell
python -m sme_fraud.review_server --port 8765
```

## Luồng rà soát

1. Chọn bộ dữ liệu, công ty, trạng thái, mức ưu tiên hoặc rule. Có tìm kiếm, phân trang và xuất danh sách đang lọc sang CSV.
2. Mở hồ sơ để xem số tiền, định khoản, hóa đơn, người lập/duyệt, chứng từ kế toán và các giao dịch ngữ cảnh. Số tiền chi trả chỉ cộng nghiệp vụ thực sự có chi tiền; sự kiện rà soát số dư không bị cộng thành dòng tiền.
3. Sơ đồ Cytoscape hiển thị đường đi từ bằng chứng rule; nếu không có đường đi, hiển thị quan hệ giao dịch–người nhận–tài khoản. Có phóng to, kéo nút/sơ đồ, chọn nút/cạnh và tra cứu giao dịch. Quan hệ cùng TK/SĐT chưa tự xác nhận gian lận.
4. Có hai nút nhanh **Xác nhận nghi vấn** / **Bỏ qua, hợp lệ**, kèm lý do nhanh và reviewer. Xác nhận nghi vấn lưu `confirmed_suspicion` để kết thúc sàng lọc/chuyển kiểm tra sâu, tách riêng với xác nhận gian lận. Các quyết định cũ **Cần bổ sung bằng chứng**, **Vi phạm kiểm soát**, **Xác nhận gian lận** vẫn có trong biểu mẫu. Hồ sơ cần bổ sung tiếp tục mở; các quyết định khác đóng bước rà soát, giữ toàn bộ lịch sử và có thể cập nhật với lý do mới.

Ngân sách giới hạn việc **mở hồ sơ mới để rà soát**, mặc định 5 hoặc 10 hồ sơ/công ty/bộ dữ liệu/ngày theo UTC+7. Mở lại một hồ sơ trong ngày không tính thêm. Mặc định **Ưu tiên hôm nay** chọn các hồ sơ đứng đầu trong sức chứa còn lại; bỏ chọn để đọc tồn đọng. Email/Zalo có outbox và ngân sách thông báo, đang ở chế độ giả lập theo Sprint 1.4. Chính sách sức chứa không thay đổi ngưỡng bộ luật hoặc điểm benchmark.

Giới hạn phút đi cùng là **5 lượt/120 phút** hoặc **10 lượt/240 phút**, dùng chung hợp đồng với simulator. Mặc định cấp lượt mọi ngày; khi chạy server trực tiếp có thể thêm `--working-weekdays 0,1,2,3,4` và lặp `--non-working-date YYYY-MM-DD` để cấu hình lịch. Metadata/API công bố lịch; ngoài lịch không cấp lượt mới. Lịch là cấu hình tiến trình, cần truyền lại khi khởi động. [Hợp đồng, chỉ số tồn cuối kỳ và kiểm chứng](rule_review_capacity.md).

SLA hiển thị theo ngày mở trong snapshot mô phỏng. Các hồ sơ lịch sử không được coi là giao dịch mới phát sinh hôm nay. Điểm ưu tiên không phải xác suất gian lận.

Có [bộ thử hồ sơ mẫu A4 riêng](rule_a4_pattern_trial.md), chưa thay snapshot mặc định. Tổng quan mẫu hiển thị người lập/tháng và từng khoản/NCC/ngân hàng/hóa đơn, tách thành viên với ngữ cảnh; liên kết hồ sơ có kết luận riêng, không tự đóng hoặc chuyển feedback giữa các hồ sơ. Gói reviewer chưa có xác nhận giảm việc thực tế.

## Dữ liệu, phản hồi và API

- Backend: `sme_fraud/review_server.py`, `sme_fraud/review_store.py`. Frontend: `review_ui/index.html`, `app.js`, `styles.css`.
- Snapshot nguồn là các CSV/JSONL trong `data/` và `reports/rules/`; cache SQLite có chỉ mục tại `.runtime/review/review.sqlite3`. Lần đầu nạp bằng chứng, lần sau dùng cache nếu fingerprint nguồn giữ nguyên. Phản hồi được đọc trực tiếp từ nhật ký, nên kết luận của CLI xuất hiện trong UI.
- UI không đọc `labels.csv`, `splits.csv` hoặc `features.csv`, không tiết lộ nhãn cài sẵn và không sửa dữ liệu huấn luyện. Test fixtures hoạt động không cần những file này.
- Phản hồi lưu trong `reports/rules/sme_fraud_XXX/feedback_audit.jsonl`; `case_review_states.csv` là trạng thái dẫn xuất. CLI và web dùng chung khóa ghi liên tiến trình, flush/fsync log và thay CSV trạng thái bằng file tạm. Chuỗi hash phát hiện sửa nội dung, không phải chữ ký hay lưu trữ bất biến.
- Nếu hồ sơ vừa được người khác cập nhật, UI từ chối lưu trên phiên cũ; bấm Làm mới để đọc kết luận mới. Nếu nhật ký bị thay đổi, hiển thị lỗi thay vì coi hồ sơ chưa có kết luận. Phản hồi chưa tự động đổi rule, nhãn tổng hợp hoặc train lại IF.
- Các API chính: `GET /api/meta`, `/api/cases`, `/api/case`, `/api/transaction`, `/api/coverage`, `/api/export`; `POST /api/admit`, `/api/feedback`, `/api/budget`. POST dùng token phiên và kiểm tra nguồn yêu cầu; dữ liệu biểu mẫu có giới hạn độ dài. Route chỉ phục vụ tài nguyên cho phép, không công khai thư mục dự án hay file nhãn.
- Nhật ký tiến trình nền: `.runtime/review/server_8765.out.log` và `.err.log`. Cache, bộ đếm ngày và nhật ký người dùng không đưa vào ZIP bàn giao.

Ứng dụng chỉ bind `127.0.0.1`, chưa có đăng nhập hay phân quyền nhiều người dùng. Tên người rà soát là thông tin tự nhập, chưa xác thực danh tính. Không dùng bản này như dịch vụ triển khai cho doanh nghiệp hoặc chia sẻ mạng công khai; [HTTP server chuẩn Python](https://docs.python.org/3.12/library/http.server.html) được dùng cho MVP cục bộ.

## Kiểm chứng đã thực hiện

- **35 kiểm thử đã qua**, gồm kế toán/causal/rules trước đó và kiểm thử UI API: bộ lọc, bằng chứng, không cần ground truth, giới hạn theo công ty/ngày, mở lại idempotent, quota khi lưu đồng thời, phản hồi sau restart, xung đột kết luận, CLI/web cùng nhật ký, phát hiện sửa log, CSRF/Origin/Host, route không công khai nhãn và CSV chống diễn giải ô văn bản thành công thức.
- `node --check review_ui/app.js` đã qua; chưa xác nhận luồng DOM hoặc bố cục trong trình duyệt.
- Kiểm tra read-only trên dịch vụ thật: 25 hồ sơ mỗi bộ, tổng **75 hồ sơ**, **258 chứng từ cân đối Nợ/Có**, và **445 dấu hiệu**. Các checksum dữ liệu gốc trên ba bộ giữ nguyên. [Kết quả kiểm tra API](review_ui_validation.json).
- Không nhập kết luận giả vào hồ sơ nguồn để kiểm thử; phản hồi được thử trong thư mục tạm. Không gửi thông báo hay thực hiện giao dịch tài chính.
- **Chưa kiểm tra trực quan bằng trình duyệt:** công cụ báo không có browser được kết nối. Mã giao diện và API đã có; cần mở URL để kiểm tra bố cục, thao tác biểu mẫu và sơ đồ trên trình duyệt mục tiêu.

## Việc còn lại trước pilot thực

Kiểm tra trình duyệt/viewport, thêm danh tính và phân quyền, nạp dữ liệu SME được phép sử dụng, đối chiếu chính sách duyệt chi và lịch làm việc, hiệu chỉnh sức chứa/ngưỡng trên validation hoặc phản hồi đã thẩm định. Năm rule C4/E2/F2/F3/F4 vẫn cần thêm dữ liệu nguồn. Các cổng pilot trong roadmap chưa được chứng minh bằng kết quả tổng hợp này.

## Cập nhật định danh hồ sơ R6 — 16/10/2026

Đã có ID cụm theo thành viên thay root UnionFind và migration khi nạp lại cache: hồ sơ tương đương một-một giữ phản hồi, người phụ trách và lượt nhận việc; tách/gộp hoặc đổi bằng chứng giữ lịch sử và yêu cầu rà lại. ID cũ có alias mở đúng hồ sơ mới; hồ sơ lịch sử chỉ đọc không tiêu tốn lượt nhận việc. Nhật ký hash gốc không bị viết lại, CSV trạng thái được dựng lại sau migration.

Giữ database đang dùng, `feedback_audit.jsonl`, `case_identity.json` và snapshot cũ trước khi áp queue mới; SQLite còn chứa admissions thực tế, không phải toàn bộ đều là dữ liệu cache có thể bỏ. Xem [hợp đồng, cách chạy prepare và giới hạn](rule_case_identity.md). R6 được kiểm thử trên database tạm; chưa migration database vận hành trong workspace. Bộ hồi quy hiện đạt 341/341, 7/7 probe readiness đạt; Node VM kiểm tra cú pháp/điều hướng, chưa có kiểm tra hiển thị mới trên trình duyệt.
