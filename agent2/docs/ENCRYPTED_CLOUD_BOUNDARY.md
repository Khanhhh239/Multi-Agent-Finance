# Yêu cầu cloud chỉ tính trên bản mã — CR-028

CR-030 đã nối [đọc/export model Mahalanobis đã fit từ kho DN](HE_REGISTRY_EXPORT.md) vào worker HE thử nghiệm; chưa chuyển API nhập JSON hoặc bốn nhánh web sang cloud.

**Yêu cầu đã được người dùng chọn ngày 12/11/2026.** CR-029 đã có [thử nghiệm HE inference độc lập](HE_INFERENCE_EXPERIMENT.md); chưa có dịch vụ cloud/web HE cho pipeline nghiệp vụ. Tài liệu này là hợp đồng ranh giới, không phải thông báo đã chuyển bốn nhánh lên cloud. Pipeline bốn nhánh CR-027 vẫn xử lý dữ liệu rõ trong môi trường local hiện tại; không được chuyển lên cloud rồi gọi đó là chế độ ciphertext-only.

## Luồng bắt buộc

```text
Tại doanh nghiệp                            Cloud
Tệp/sổ gốc
  → kiểm tra, snapshot, feature theo as_of
  → mã hóa bằng khóa của phiên
  → bản mã + metadata được phép ──────────→ kiểm tra envelope/quyền/context
                                             → tính trực tiếp trên bản mã
                                             → kết quả vẫn là bản mã
  ←─────────────────────────────────────── trả bản mã kết quả
  → kiểm tra ràng buộc request/kết quả
  → giải mã tại doanh nghiệp
  → ghép lại giao dịch/chứng từ và hiển thị
```

Khóa bí mật hoặc secret share ở doanh nghiệp. Cloud chỉ được nhận public/evaluation keys mà giao thức cần, không nhận khóa có thể giải mã. Không giải mã trung gian tại cloud, không gửi kết quả rõ về cloud để tính tiếp, không chuyển sang xử lý dữ liệu rõ khi HE không hỗ trợ. AES/Fernet/TLS bảo vệ lưu/truyền khác với phép tính HE; Base64/serialize/checksum không thay thế mã hóa.

Việc chuẩn bị dữ liệu rõ xảy ra trong môi trường doanh nghiệp được phép. Nếu dùng giao diện SaaS, thao tác chọn tệp phải chuyển cho node doanh nghiệp; API upload JSON hiện tại không phải endpoint cloud HE. Chưa xác định vị trí triển khai và đường đi dữ liệu thì chưa dùng dữ liệu thật cho thử nghiệm cloud.

## Hợp đồng phiên cần có trước khi gửi

Các trường dưới đây là yêu cầu thiết kế; chưa có API/schema giao thức được triển khai hoặc chốt version để sử dụng:

- Quyền tenant/doanh nghiệp, phiên và request ID, nonce/expiry và ràng buộc chống replay; handle giao dịch là opaque và mapping với mã gốc giữ tại doanh nghiệp.
- Backend/protocol/scheme version; context fingerprint, key ID/key epoch, bộ public/evaluation keys; không có private key trong gói cloud.
- Feature contract, thứ tự cột, missing mask, chuẩn hóa/miền giá trị/packing/mask padding và circuit/model version. Missing vẫn khác số 0. Số tiền điều chỉnh giữ dấu; các phép đối chiếu tiền phải có miền số và kiểm tràn chính xác.
- Snapshot/as_of và model gắn với phiên bằng identifier/commitment được thiết kế tránh lộ nội dung; không mặc định công bố hash dữ liệu rõ ít khả năng có thể đoán ngược.
- Ciphertext có giới hạn kích thước/tài nguyên, output type, đúng người nhận và đúng phép tính cho phép; kết quả gắn request/context/key/model/feature version. Không cung cấp endpoint giải mã ciphertext bất kỳ.
- Phạm vi metadata cloud nhìn thấy (DN, kích thước, thời điểm, số dòng nếu không padding) phải được khai báo. Yêu cầu ciphertext-only không tự che toàn bộ metadata.

Kiểm quyền và chữ ký/checksum không tự chứng minh cloud đã tính đúng. Cần chốt giả định cloud chỉ tò mò hay có thể sửa kết quả, cùng cơ chế kiểm chứng tương ứng trước nghiệm thu; HE riêng lẻ không giải quyết tính đúng nghiệp vụ hoặc đầu vào độc hại.

## Khả năng của bốn nhánh hiện tại

| Nhánh | Phép tính trong code hiện tại | Việc cần kiểm chứng trước khi hỗ trợ HE |
|---|---|---|
| Luật | Đối chiếu VND nguyên có dấu; P1 liên kết/phân bổ và so sánh; E3 xử lý tên | Biên dịch phép so sánh/chuỗi/liên kết thành circuit và kiểm tính đúng; không đưa nhầm sai số số thực vào đối chiếu tiền |
| Thống kê | Biến đổi/chuẩn hóa, trị tuyệt đối, đuôi và thứ hạng theo reference | Xác định phép toán hỗ trợ, miền giá trị/sai số và reference có phải dữ liệu bí mật hay không |
| Đồ thị | Định danh, tìm/nối cạnh, nhóm và căn cứ nguồn | Xác định cách truy cập/nối trên ciphertext; không gửi đồ thị hoặc định danh rõ lên cloud như một cách thay thế |
| ML không nhãn | IF có nhánh cây; ECOD có CDF/so sánh/log; LOF có khoảng cách/hàng xóm; AE hiện dùng tanh | Cần adapter/circuit HE riêng cho từng model. Thay tanh bằng đa thức hoặc đổi cách tính phải thành model/version mới và được đo lại; không coi tương thích chỉ vì cùng tên model |

Bảng này mô tả phụ thuộc từ code hiện tại, không khẳng định các thuật toán bất khả thi với HE. Backend chưa chứng minh phép tính nào thì trả **unavailable / backend_not_implemented**, không bịa điểm hoặc chạy sklearn/plaintext trên cloud. Artifact 33 feature hiện có không tự trở thành model HE.

## Phạm vi đã được người dùng chọn

Người dùng đã chọn: **cloud chỉ chấm bằng model đã fit riêng tại doanh nghiệp**. Chưa yêu cầu huấn luyện trên cloud trong giai đoạn này; CR-029 xây proof-of-concept inference theo lựa chọn đó.

Nếu bắt đầu từ inference, mỗi DN có thể dùng phiên khóa riêng; đây chưa phải quyết định true multi-key hoặc collective cho việc học chung nhiều DN. Tính bảo mật của tham số model/reference cũng cần chốt riêng: không mặc định chúng được gửi rõ lên cloud.

Nếu cần training, phải bổ sung phương pháp train không nhãn và giao thức cụ thể. TH2 ở phụ lục 90 đang mô tả Logistic **có nhãn** và multi-party; không áp nguyên sang yêu cầu bốn nhánh/ML không nhãn và không tự sinh nhãn để dùng lại.

## Mốc kiểm chứng đầu tiên được đề xuất

Làm thử nghiệm độc lập trên dữ liệu mô phỏng với **một circuit nhỏ được định nghĩa trước**, sau khi chọn phạm vi/backend:

1. DN tạo khóa, chuẩn bị và mã hóa đầu vào; cloud nhận gói không có secret key hoặc feature rõ.
2. Worker riêng chỉ tải context public/evaluation keys và tính trên ciphertext; trả ciphertext. Không giả lập encrypt/decrypt bằng JSON/Base64 và không cài đường fallback dữ liệu rõ.
3. DN xác minh context/request rồi giải mã. Kiểm thử worker không thể tự giải mã.
4. Đối chiếu B0 thuật toán rõ gốc, B1 circuit rõ tương ứng và B2 circuit mã hóa: tách thay đổi thuật toán/xấp xỉ khỏi sai số HE. Miền số, tolerance và giới hạn tài nguyên phải ghi trước khi chạy, chưa bịa số nghiệm thu ở đây.
5. Kiểm sai DN/key/context/epoch/version, replay, sửa gói/kết quả, missing, số âm, quá miền số và quá tài nguyên. Từ chối tường minh, không gọi xử lý rõ để vượt ca lỗi.
6. Đo thời gian, bộ nhớ, kích thước bản mã, sai số và số dòng/feature. Chỉ ghi PASS có evidence thực; chưa qua thì HE chưa khả dụng, chưa thay pipeline local hoặc kết nối hàng đợi.

## Nguồn kỹ thuật đã đối chiếu

- [Microsoft SEAL](https://github.com/microsoft/SEAL): BFV/BGV cho số nguyên, CKKS cho số thực xấp xỉ; thư viện không tự biến chương trình/model sklearn thành circuit HE.
- [TenSEAL](https://github.com/OpenMined/TenSEAL): phép toán tensor mã hóa và serialization context/keys. Việc gửi context phải loại secret key.
- [OpenFHE](https://openfhe.org/): các scheme/backend khác nhau; có hỗ trợ phép tính không có nghĩa adapter của Agent2 đã có hoặc đã đạt hiệu năng/nghiệm thu.

CR-029 đã cài dependency opt-in và chạy profile CKKS thử nghiệm có thông số cố định; chưa chọn backend/crypto profile cho production, chưa mở endpoint cloud hoặc đổi model/feature/điểm và tiến trình live. D-11/D-12 tiếp tục mở cho giao thức/khóa/quyền mở/sai số/tài nguyên; D-10 đã nhận yêu cầu ciphertext-only nhưng vị trí node và triển khai thật vẫn cần xác định.
