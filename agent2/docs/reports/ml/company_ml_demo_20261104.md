# Thử trọn luồng Company ML — 04/11/2026

**Đạt 50 kiểm tra trên Chrome headless 156.0.8078.80 qua Playwright**, theo yêu cầu thử C001 dùng Isolation Forest và C002 dùng ECOD. Mọi thao tác cập nhật, đánh giá, kích hoạt, giữ và chấm được bấm trên giao diện thật ở `http://127.0.0.1:8851/company-ml`; API GET chỉ dùng đối chiếu kết quả. Không mock phản hồi API hoặc thay thế thao tác web bằng POST trực tiếp.

Đây là demo mô phỏng riêng `.runtime/company_ml_demo_20261104/`, có danh tính QA cố định; không có dữ liệu doanh nghiệp thật, người rà độc lập hoặc phút xử lý thực tế. Máy chủ demo đã được khởi động lại vì tiến trình cũ không còn chạy, chỉ bind loopback 8851/8852.

## Kết quả

| Doanh nghiệp | Model đang dùng | Dòng nguồn trước → sau | Dòng được chấm trước → sau | Vượt ngưỡng trước → sau |
| --- | --- | ---: | ---: | ---: |
| C001 | Isolation Forest **v3** | 37 → 38 | 8 → 9 | 1 → 1 |
| C002 | ECOD **v1** | 31 → 32 | 7 → 8 | 1 → 1 |

C001 đã có hai phiên bản trước lượt thử; lịch sử được giữ và ứng viên mới là v3. C002 chưa có phiên bản, ứng viên mới là v1. Đánh giá không tự kích hoạt: chỉ sau khi bấm **Xác nhận dùng** thì binding mới đổi. Kích hoạt/chạy ở một công ty không thay model của công ty còn lại.

Sau khi chấm lần đầu, reload trang và chọn lại doanh nghiệp: đúng model/version, SHA256 artifact và ngưỡng. Trang reload mặc định về C001; C002 được chọn lại để kiểm tra binding của C002. Bộ chọn thuật toán là lựa chọn cho ứng viên mới; thẻ **Đang dùng** và bảng phiên bản mới thể hiện binding đã xác nhận.

## Cập nhật có dữ liệu mới thật trong demo

Đã thêm **một giao dịch mô phỏng mới cho mỗi công ty** vào cache nguồn kết nối của chính demo, đặt sau giao dịch cuối của công ty và sao chép vector feature của một giao dịch mô phỏng cùng công ty. Lưu bản sao và SHA256 của `transactions.csv`, `features.csv`, `manifest.json` trước/sau; cập nhật manifest đúng hợp đồng. Không thay nguồn trong `data/`, model lịch sử hoặc database demo nghiệp vụ khác.

Sau khi bấm cập nhật dữ liệu trên web:

- Revision dữ liệu đổi, số dòng tăng đúng một ở mỗi công ty.
- Binding vẫn là Isolation Forest v3 / ECOD v1; số phiên bản không tăng (C001 có 3, C002 có 1).
- Bấm **Giữ model hiện tại** rồi chấm: dùng đúng phiên bản; thêm một giao dịch mới vào kết quả.
- Điểm và cờ vượt ngưỡng của toàn bộ giao dịch cũ không đổi (đối chiếu sai số số học ≤ 1e-12).
- Reload lại: SHA256 artifact, ngưỡng, phiên bản và lịch sử lượt chấm vẫn giữ.

Hai dòng thêm mới được giữ trong demo để người dùng xem lại; bản sao trước thay đổi nằm trong thư mục bằng chứng. “Vượt ngưỡng” là tín hiệu mô hình trên dữ liệu mô phỏng, không phải xác nhận gian lận hoặc chất lượng thực địa.

## Các kiểm tra bổ sung

- Viewport desktop 1365×1000 và mobile 390×844: không tràn ngang toàn trang; bảng có vùng cuộn riêng.
- Cổng 8852: kế toán viên chỉ thấy C001 và không được cập nhật, đánh giá hoặc chấm.
- Không có lỗi JavaScript chưa được xử lý trong hai luồng đã thử.
- Không thay đổi mã sản phẩm trong đợt nghiệm thu này.

## Bằng chứng cục bộ

- [Kết quả 50 kiểm tra và thông số phiên bản](../../../.runtime/company_ml_e2e_20261104/run_1793801300614/results.json).
- [C001 toàn trang](../../../.runtime/company_ml_e2e_20261104/run_1793801300614/C001_final.png), [C002 toàn trang](../../../.runtime/company_ml_e2e_20261104/run_1793801300614/C002_final.png).
- [C001 mobile](../../../.runtime/company_ml_e2e_20261104/run_1793801300614/C001_mobile.png), [C002 mobile](../../../.runtime/company_ml_e2e_20261104/run_1793801300614/C002_mobile.png).
- Script chạy và thay đổi nguồn nằm trong `.runtime/company_ml_e2e_20261104/`; chỉ dùng cho workspace demo có marker đúng loại. Không dùng script thêm dòng cho dữ liệu thật.

Phạm vi này là hai luồng ML trên Chrome headless và hai viewport đã nêu. Không suy thành nghiệm thu toàn app, trình duyệt khác, điện thoại vật lý, đăng nhập thật hoặc hiệu quả ML trên doanh nghiệp thật.
