# Năm nâng cấp luồng nhập liệu — 21/10/2026

Phạm vi: củng cố PLAN_06 và diễn giải PLAN_12. Đây là triển khai kỹ thuật, chưa nghiệm thu chất lượng OCR trên dữ liệu độc lập và chưa nghiệm thu PLAN_14/pháp lý.

## 1. Thay đổi

| Hạng mục | Đã triển khai | Giới hạn |
|---|---|---|
| Sửa bảng trên web | Bổ sung dòng có vùng nguồn kéo trên ảnh; xóa dòng có lý do; sửa ô qua cơ chế hiện có | Mỗi lần tối đa 10 thao tác dòng, tách khỏi lần lưu ô; tối đa 500 dòng/hồ sơ. Dòng mới được thêm cuối bảng, không tự đoán thứ tự in |
| Đọc lại có mục tiêu | Thêm reader `expanded`: padding có giới hạn và phóng crop 2×; tự thử khi primary không có ứng viên và còn ngân sách | Tối đa 2 trường/4 crop cho cả chuỗi; không hứa cải thiện mọi ảnh. Ảnh phóng to không tạo lại chi tiết đã mất |
| Gán bên bán/bên mua | Vùng theo anchor rõ ràng, hỗ trợ hai cột, không lấy thứ tự đọc làm vai trò; vùng chồng lấn bất định thì bỏ qua | Không có anchor/căn cứ thì vẫn cần review; không tự đoán MST |
| Diễn giải dễ xử lý | Hướng dẫn có vấn đề, lý do, bước tiếp theo và nút về đúng mục/trường; cập nhật prompt Qwen | Hướng dẫn do server tạo từ bản đã lưu. Qwen viết lại từ facts; các guard cơ học không thay nghiệm thu ý nghĩa |
| Số liệu trên UI | Đếm trường có giá trị/thiếu/mơ hồ/đã xác nhận, số lần lưu; p50/p95 HTTP theo công đoạn | Đây không phải accuracy OCR. Chưa có nhãn độc lập để chấm đúng/sai tự động |

### Bảo vệ dữ liệu và replay

- `CorrectionCommand.item_operations` là phần mở rộng tùy chọn; lệnh cũ không cần thay đổi.
- Thêm dòng cần mô tả được in, trang thật trong tài liệu và bbox chuẩn hóa có diện tích dương. Các trường không nhập giữ chưa biết, không suy tiền/thuế suất.
- ID mới có tiền tố `manual-`, không trùng ID hiện tại hoặc ID đã xóa trong lịch sử. ID các dòng cũ không thay đổi. `line_number` dòng mới là vị trí bổ sung, không cam kết là STT in trên giấy.
- Lưu qua cùng cơ chế auth, tenant/taxpayer, task, expected revision, idempotency và transaction. Sai một thao tác thì toàn bộ lần lưu rollback.
- Thêm/xóa làm mất xác nhận bảng đầy đủ; chỉ xác nhận lại khi người dùng đối chiếu đúng số dòng và mọi trang. Xóa hết dòng không thể xác nhận COMPLETE.
- Sự kiện lưu có ảnh chụp trước/sau bảng, actor, lý do và bằng chứng. Replay phục dựng được bảng; quality xác minh provenance của trường bổ sung qua sự kiện. Bản gốc không bị sửa.
- Không trộn thao tác bảng với bản nháp ô hoặc hồ sơ nghiệp vụ. Xung đột khi lưu dòng giữ nội dung trong hộp thoại để người dùng đối chiếu lại.

### Đọc lại và đo lường

`primary → expanded → comparison` chỉ tiếp tục khi chưa có ứng viên và còn crop budget. Padding ngang tối đa 16 pixel, dọc tối đa 8 pixel; scale 2× vẫn chịu trần 1 triệu pixel/crop và 2 triệu pixel/lượt reader. Mỗi reader giữ cache riêng có binding revision, cấu hình, nguồn và implementation. Observation giữ bbox gốc, crop pixel box thực tế, page size, scale và text riêng.

Chưa bật tự xác nhận. Giá trị được reviewer xác nhận được bỏ qua trong hàng đợi tự động; ứng viên khác nhau vẫn cần đối chiếu. Đây là mở rộng trên crop từ trang đã lưu, không phải render lại trực tiếp vùng PDF ở DPI gốc cao hơn. Vùng chưa detect vẫn có thể chưa đọc được.

`capture-insights` chỉ đọc record trong scope đã xác thực. DB đo thời gian riêng, không lưu token, URL đầy đủ, OCR text hoặc giá trị trường. Giữ tối đa 1.000 thao tác HTTP thành công/đơn vị. Thời gian tính tới response headers, gồm handler và server overhead; không gồm render UI. First/subsequent request trong metadata không được gọi là model cold/warm. Các mốc load/inference OCR thật được báo riêng trong phép đo local.

## 2. Cách dùng

1. Khởi động lại `OPEN_AGENT3.cmd`, làm mới trình duyệt bằng Ctrl+F5.
2. Ở **Dữ liệu hóa đơn**, lưu hoặc bỏ bản nháp ô trước khi sửa cấu trúc bảng.
3. Chọn **Bổ sung dòng hàng**; nhập các ô có thật trên giấy. Số tiền theo định dạng Việt Nam; KCT/KKKNT không kèm rate số.
4. Chọn **Chọn vùng trên hóa đơn**, kéo bao quanh đúng một dòng trên ảnh gốc. Nhấn Escape nếu muốn quay về hộp nhập mà chưa chọn xong.
5. Ghi căn cứ, chọn **Lưu dòng bổ sung**. Để sửa giá trị của dòng đã lưu, dùng các ô/checkbox và nút lưu hiện có. Để xóa dòng nhận nhầm, chọn **Xóa dòng**, ghi rõ lý do.
6. Xem lại tất cả trang, đối chiếu bảng trước khi xác nhận đủ dòng. Hồ sơ/kiểm tra/diễn giải cũ không tự coi là kết quả của revision mới.
7. Trường đọc sai: **Xem nguồn → Đọc vùng rộng và phóng to**, hoặc chạy hàng đợi **Kiểm tra và đọc lại vùng lỗi**. Kết quả vẫn là ứng viên cần đối chiếu.
8. Mở **Chất lượng dữ liệu và thời gian xử lý** để xem số liệu; chọn **Cập nhật số liệu** sau các thao tác mới.
9. Ở **Diễn giải**, các hướng dẫn có nút **Mở phần cần xử lý**. Nút kiểm tra revision trước khi đưa người dùng về trường liên quan.

## 3. Kiểm thử

Các fixture hóa đơn/chữ ký/nghiệp vụ trong test là tổng hợp, không dùng làm bằng chứng độ chính xác trên hóa đơn thật.

- Backend: thêm/xóa, số vượt giới hạn integer JavaScript, KCT, source ownership, ID lịch sử, exact count/page proof, rollback, idempotency, stale revision, scope, verified review event và audit replay.
- Layout: MST/địa chỉ hai cột, đảo thứ tự blocks, nhãn tách value, vùng chồng lấn, vùng bảng và vùng trước anchor.
- Recovery: cache giữa primary/expanded riêng, scale và provenance, giới hạn ngân sách chung, không tự sửa HUMAN_CONFIRMED.
- Metrics: phiên bản/scope, mẫu số, p50/p95, không lộ MST, xác nhận không đồng nghĩa accuracy.
- Chrome: thêm bằng kéo vùng, xem lại highlight, xóa có lý do, bảng 0 dòng, xung đột giữ bản nháp, hiển thị số liệu và kiểm tra mobile.
- Chạy tiếp hồi quy đầy đủ các bộ cũ để kiểm tra luồng nghiệp vụ, tax engine và diễn giải.

Kết quả cuối: **518 test Python, 65 nhóm Chrome, 11 kiểm tra JavaScript đạt**. Chạy lại riêng 64 test diễn giải sau lần chỉnh prompt cuối cũng đạt; không cộng trùng vào mẫu số 518. Runtime source hashes trong báo cáo đã đối chiếu lại với file cuối. `validation_summary.json` và các file `browser_*.json` do runner sinh; không coi test double là model thật.

Chrome có thử mất phản hồi sau khi server commit: bấm lại vẫn chỉ có một dòng bổ sung, dùng lại ID/idempotency key. Các lượt test được thực hiện trên kho tạm, không sửa DB người dùng.

Chạy lại:

```powershell
cd D:\financial
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_capture_upgrade.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\benchmark_capture_upgrade.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\evaluate_automation_pilot.py --output agent3_tax_compliance/data/capture_upgrade/pilot_score.json
```

## 4. Phép đo thật và giới hạn

- Replay pilot cũ: 15 biến thể/9 nhóm trang hóa đơn có tương quan, gồm mẫu đào tạo tách riêng. Tổng kết chưa đổi so với baseline round 3: MST 28/30, số/ký hiệu 29/30, ngày 14/15, tổng tiền 44/44, tên 22/30. Nhóm tên vẫn có 4 trường sai được điền và 4 thiếu/mơ hồ. Không lấy dev đã sửa làm holdout.
- Thử recognizer thật trên cùng một crop tên khó đã dùng phát triển: 1× và resize 2× đều 0/1 exact match. Lượt cuối load khoảng 5,37–5,94 giây, inference khoảng 1,40–1,44 giây; không suy p95 từ hai lượt. Thử resize-only này chưa đo hiệu quả padding/field binding hoặc toàn bộ recovery.
- Qwen local ban đầu đưa ý của notice vào summary nhưng chỉ dẫn nguồn summary/scope/coverage; guard từ chối. Đã tách inputs theo từng đoạn, giữ nguyên validator. Lượt cuối Qwen3:8b thật qua guard cấu trúc/nguồn trong khoảng 56,32 giây; đây chưa phải nghiệm thu ý nghĩa/nghiệp vụ. Facts thử là tổng hợp, không gửi hóa đơn thật. `real_runtime.json` lưu kết quả cuối; lỗi guard vẫn dùng fallback, không bỏ guard để ép hiện model.
- Holdout mới vẫn thiếu; địa chỉ/toàn bộ ô bảng chưa được gán nhãn độc lập. Không tuyên bố nhận đủ mọi trường, không bật auto-accept, không promote profile full-page chậm và không thay model chính.

Dữ liệu nguồn, vùng crop, output Qwen/raw OCR, DB và ảnh chụp web để trong thư mục local bị ignore; Git chỉ nhận mã, contract, test và số liệu tổng hợp.
