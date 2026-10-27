# Kiểm tra sâu luật cứng và ML — 23/10/2026

**Có vấn đề cần sửa. Đã tái hiện 4 nhóm lỗi logic rõ ràng, thêm 1 nhóm ngữ nghĩa/cập nhật feature cần chốt; RR09 vẫn là khoảng trống chính sách chưa đóng.** Nhận định trước đây rằng pipeline đã nạp/chạy được chỉ đúng trong phạm vi đã kiểm thử, chưa đủ để gọi toàn bộ logic luật/feature là ổn.

Lượt này kiểm tra mã, chạy lại bộ hồi quy hiện có, thử các tình huống dữ liệu biên mới và chấm lại artifact evaluation đã khóa. Trạng thái các phát hiện bên dưới: **đã tái hiện, chưa khắc phục trong engine/model**. Bằng chứng được tạo riêng; nguồn, model, kết quả shadow và kết luận cũ được bảo toàn.

## 1. Lỗi đã tái hiện

| Mã | Mức ưu tiên | Hiện tượng và cách tái hiện | Ảnh hưởng | Cần sửa |
|---|---|---|---|---|
| **R01 — B4 dùng chứng từ biết muộn** | Cao | Giao dịch 12/08; giao nhận chỉ được biết 14/08. Đổi cờ giao nhận của dữ kiện biết ngày 14/08 từ 0 sang 1 làm điểm B4 ngày 12/08 giảm **3 → 0** | Bằng chứng tương lai có thể làm mất đóng góp cảnh báo lịch sử; không phải mọi hồ sơ đều vì thế bị loại khỏi hàng đợi | Chỉ dùng xác nhận giao nhận có nguồn, đúng giao dịch và thời điểm biết/xác minh không muộn hơn cutoff; dữ kiện đến sau giữ làm ngữ cảnh rà tiếp |
| **R02 — B2 giữ nhân viên ở chỉ mục công ty cũ** | Cao | Nhân viên chuyển C001 → C002 trong master; giao dịch C001 sau ngày chuyển vẫn có **3 điểm B2** do điện thoại của nhân viên đó. Kỳ vọng chỉ mục hiện hành C001 không còn người này | Tín hiệu trực tiếp B2 có thể dựa trên sai phạm vi công ty; quan hệ lịch sử nếu cần phải được trình bày riêng | Khi thay master, xóa định danh khỏi khóa dùng `old.company_id`, rồi thêm vào công ty mới; kiểm tra lại công ty hiện hành trước khi lấy direct_matches |
| **M01 — Feature dùng dữ kiện chưa có tại cutoff** | Cao | Chứng từ biết sau ngày chi vẫn làm `support_doc_count` **0 → 2**, `goods_receipt_verified` **0 → 1** trong feature ngày chi. Hóa đơn có ngày phát hành sau ngày chi vẫn làm `invoice_log_gross` **0 → 16,30041729** khi điền 12 triệu | Rò thông tin thời gian vào đầu vào IF nếu nguồn có các tình huống này; chia train/calibration/evaluation theo posted_at không tự khắc phục rò bên trong feature | Xây feature từ phiên bản bằng chứng được biết trước cutoff, có trạng thái thiếu/khả dụng; từ chối hoặc che dữ kiện tương lai thay vì đọc trực tiếp các cờ/tổng tiền cuối cùng |
| **M02 — Rỗng trùng rỗng thành quan hệ** | Trung bình | Để trống điện thoại và địa chỉ của nhân sự/NCC: `employee_phone_overlap=1`, `employee_address_overlap=1`; B2 trong cùng fixture có 0 điểm | Feature ML tạo quan hệ không có bằng chứng. Chưa suy từ hai feature này rằng IF chắc chắn sẽ cảnh báo sai | Bỏ định danh rỗng/không hợp lệ trước khi cập nhật bộ đếm và đối chiếu; thống nhất chuẩn hóa với quy tắc |

R01 nằm ở nhánh B4 dự phòng dùng trạng thái NCC khi không có kết quả từ nguồn thuế riêng; không suy rằng mọi nhánh B4 đều bị hạ điểm theo cách này.

Điểm mã: [B4](../sme_fraud/rules.py) dòng 761–763; [chỉ mục và B2](../sme_fraud/rules.py) dòng 449–454, 729–731; [feature](../sme_fraud/features.py) dòng 159, 194, 231, 237–245. [Kết quả từng ca](deep_rules_ml_audit_20261023/edge_probes.json), [danh sách phát hiện có cấu trúc](deep_rules_ml_audit_20261023/findings.json).

## 2. M03 — quan hệ hiện hành và quan hệ lịch sử trong feature chưa tách rõ

Đã tái hiện hai khác biệt so với master hiện hành:

- Sau khi nhân viên đổi điện thoại/địa chỉ, feature overlap vẫn là **1**; B2 ở giao dịch sau sửa master đã về **0**.
- Sau khi NCC đổi điện thoại để tách khỏi nhân viên, `graph_employee_count` của feature vẫn là **1**; đường quan hệ hiện hành trong B2 không còn.

Nguyên nhân kỹ thuật: khi thay master, code feature chỉ giảm bộ đếm ngân hàng cũ, không giảm điện thoại/địa chỉ cũ; đồ thị UnionFind của feature chỉ hợp nhất, không gỡ cạnh đã bị thay. Những feature này khác đồ thị có cập nhật hiện hành trong rules.

Hai probe này đặt kỳ vọng theo **trạng thái master hiện hành**. Việc cố ý dùng quan hệ đã từng quan sát trong quá khứ có thể là một thiết kế feature hợp lệ. Vì vậy đây được ghi là **khoảng trống ngữ nghĩa/nhất quán cần chốt**, không tự đồng nhất với rò dữ liệu tương lai hoặc kết luận mô hình sai. Cần tách rõ feature “hiện hành” với “đã từng liên hệ”, đặt tên/mô tả/version và cửa sổ lịch sử tương ứng; nếu chọn hiện hành thì phải hỗ trợ thay/gỡ liên kết và giảm đúng bộ đếm.

## 3. RR09 và các phần còn thiếu khác

RR09 được kiểm tra lại qua engine và hàng đợi: hạn mức đã xác minh **2.000.000 đồng**, khoản chi **2.000.001 đồng** vẫn nhận **14 điểm P2/ưu tiên cao**. Đây là hành vi hiện tại, chưa phải thực thi đề xuất phân tầng. [Đề xuất tham số](rr09_proposal_20261022.md) vẫn cần chốt chính sách rồi triển khai; kiểm tra ghi nhận hành vi này không có nghĩa chấp nhận nó là chính sách cuối.

Các phần dưới đây vẫn là giới hạn đánh giá, không được gọi thành lỗi số học mới:

- 515 lượt baseline thiếu điểm IF đầy đủ đã được giải thích bằng thành viên ngoài evaluation; không chấm lại train/calibration để làm đẹp độ phủ.
- Hiệu ứng số thành viên với phép max đã được đo, nhưng chưa có kết quả độc lập để chọn phép gộp khác.
- 128 phiếu mới có rà trợ lý; **0 kết luận độc lập hợp lệ**, phút con người null. Chưa chứng minh lợi ích IF hoặc chất lượng trên SME thật.

## 4. Kết quả kiểm chứng và phạm vi ảnh hưởng

- **669 kiểm thử hiện có, 51 module: 0 failure, 0 error, 0 skip.** [Kết quả](deep_rules_ml_audit_20261023/regression_result.json), [log](deep_rules_ml_audit_20261023/regression.log). Test cũ chưa bao phủ đầy đủ các ca mới trên nên PASS này không phủ định phát hiện.
- **9 probe bổ sung:** 7 kỳ vọng không đạt, không có lỗi chạy probe; trong đó hai kỳ vọng M03 có giả định “hiện hành” đã ghi rõ. Hai probe còn lại xác nhận nguồn timestamp khác dạng chuẩn bị từ chối và tái hiện hành vi RR09 hiện tại. Không cộng 9 probe này thành 9 tình huống nghiệp vụ đã nghiệm thu.
- **Chấm lại 11.811 giao dịch evaluation** bằng hai artifact IF đã ghim SHA256, không fit lại model nguồn: điểm khớp bản đã lưu, sai lệch tuyệt đối lớn nhất **0**; provenance cửa sổ được xác minh. [Đối chiếu artifact](deep_rules_ml_audit_20261023/actual_artifacts.json).
- Đối chiếu riêng feature điện thoại/địa chỉ với master hiện hành trên **41.082 dòng cache reporting**: **0 sai khác**. Hai bộ có 8 revision nhân sự/bộ nhưng không đổi các trường công ty, điện thoại, địa chỉ, ngân hàng hoặc vai trò đã kiểm; không có revision NCC và không có điện thoại/địa chỉ rỗng. Vì vậy các probe contact mới không được kích hoạt trên hai cache này. [Bản quét](deep_rules_ml_audit_20261023/actual_contact_scan.json).
- Hai nguồn reporting không có cột `support_docs_observed_at` và không có ngày hóa đơn sau ngày chi. **Thiếu cột thời điểm biết không chứng minh toàn bộ cờ chứng từ được biết đúng lúc**; không thể dùng điểm replay giống nhau để chứng nhận nguồn SME mới không rò thời gian.
- Dữ liệu/model/kết quả đã khóa và mã hiện có được kiểm tra hash trước/sau. Nhãn/oracle/holdout nguồn đã khóa không được phân tích hoặc chấm; các fixture tạm trong test có thể có tên 005 hoặc nhãn giả để kiểm tra cổng. Băm opaque để bảo toàn được thực hiện riêng.

## 5. Thứ tự sửa đề xuất

1. **Sửa cutoff bằng chứng ở R01/M01 trước**; thêm test bảo đảm dữ kiện biết sau không đổi điểm/feature trước đó.
2. **Sửa chỉ mục công ty R02**, sau đó lỗi rỗng M02; thêm test chuyển công ty, xóa định danh và cập nhật đồng thời.
3. **Chốt ngữ nghĩa M03** rồi đồng bộ bộ đếm/đồ thị; kiểm tra cả việc giữ một quan hệ hợp lệ khác khi gỡ một cạnh cũ.
4. **Chốt và triển khai RR09** ở cấu hình có phiên bản; không để 14 điểm P2 tự nâng lại mọi khoản vượt nhỏ lên ưu tiên cao; giữ các căn cứ bắt buộc độc lập.
5. Sau sửa feature, **đổi hợp đồng/fingerprint, dựng cache và artifact model mới** trên các cửa sổ được phép. Giữ nguyên artifact cũ; không sửa metadata để ép model cũ tương thích. Nếu dùng kết quả evaluation này để chọn phương án, khóa giai đoạn đánh giá mới trước lần thử tiếp theo.
6. Chạy lại hồi quy cùng các ca tái hiện mới, kiểm tra bảo toàn đầu vào rồi tiếp tục rà độc lập. Sửa mã và test đạt chưa tự chứng minh hiệu quả vận hành của IF.

Cách tái hiện: chạy `python -B .runtime/deep_rules_ml_audit_20261023/probe_edges.py` trong workspace với môi trường dependency khớp [environment.json](deep_rules_ml_audit_20261023/environment.json). Script chỉ tạo fixture trong bộ nhớ và ghi bằng chứng audit riêng. Hai lệnh replay artifact cần thư mục output mới; không chạy đè các replay đã lưu.
