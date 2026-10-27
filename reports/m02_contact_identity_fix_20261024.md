# Sửa M02 — rỗng trùng rỗng thành quan hệ — 24/10/2026

**Đã sửa trong mã nguồn:** dữ liệu điện thoại/địa chỉ thiếu hoặc không dùng được không còn trở thành khóa trong bộ đếm và phép đối chiếu feature. Các ca rỗng đã tái hiện nay cho `employee_phone_overlap=0`, `employee_address_overlap=0`, phù hợp với B2. Quan hệ hợp lệ vẫn được nhận diện sau chuẩn hóa.

| Tình huống | Phone overlap | Address overlap | Graph employee count | Điểm B2 trực tiếp |
|---|---:|---:|---:|---:|
| Cả hai phía rỗng | 0 | 0 | 0 | 0 |
| Cả hai phía chỉ có khoảng trắng | 0 | 0 | 0 | 0 |
| Phone `N/A`, địa chỉ `không có` | 0 | 0 | 0 | 0 |
| `0912.345.678` khớp `+84 912 345 678`, địa chỉ khác | 1 | 0 | 1 | 3 |
| `Số 12, Đường Ánh Dương` khớp `SO12DUONGANHDUONG`, phone khác | 0 | 1 | 0 | 3 |

[Bằng chứng sau sửa](m02_contact_identity_fix_20261024/reproduction_after.json) lưu cả feature và hit B2. Các ca so sánh B2 trong bảng tắt nhánh graph để đo riêng khớp trực tiếp; feature graph vẫn được tính độc lập. [Bằng chứng gốc](deep_rules_ml_audit_20261023/edge_probes.json) được giữ nguyên. Sửa feature không đồng nghĩa đã chứng minh IF từng báo sai hoặc hiệu quả rà hồ sơ đã tăng.

[identity.py](../sme_fraud/identity.py) là nơi chuẩn hóa dùng chung cho [rules.py](../sme_fraud/rules.py) và [features.py](../sme_fraud/features.py). Quy ước giữ cách xử lý cũ cho giá trị hợp lệ: chữ hoa, bỏ dấu tiếng Việt/dấu phân cách, giữ số 0 đầu, quy đổi dạng phone `+84`/`0084` như B2. Chỉ phone/address loại thêm:

- Giá trị không phải chuỗi, kể cả số, boolean, list/dict; không tự biến chúng thành định danh bằng `str()`.
- Khóa rỗng sau chuẩn hóa: chuỗi rỗng, khoảng trắng, chỉ dấu câu.
- Placeholder sau chuẩn hóa: `NA`, `NAN`, `NONE`, `NULL`, `UNKNOWN`, `NOTAVAILABLE`, `KHONGCO`, `CHUACO`.
- Phone chỉ có các chữ số 0.

Không áp danh sách placeholder này cho các loại khóa khác như số hóa đơn hay tài khoản ngân hàng. Namespace mô phỏng như `PHONE_SYN_001` vẫn được hỗ trợ. Đây là quy tắc đối chiếu định danh của ứng dụng, không xác nhận số điện thoại đang hoạt động hoặc địa chỉ có thật.

Feature chỉ thêm khóa phone/address không rỗng vào bộ đếm, dùng cùng khóa chuẩn hóa ở phía NCC và chỉ trả overlap khi bộ đếm dương. Thiếu hẳn cột contact cũng được coi là không có khóa. Phần graph bỏ phone thiếu/không hợp lệ, chuẩn hóa phone như B2, phân biệt namespace phone/bank với entity ID để tránh nối nhầm loại định danh. Address vẫn là tín hiệu yếu; không được nối thành cạnh graph mạnh, đúng mô tả feature hiện có.

**232 kiểm thử thuộc 15 module đạt, 0 thất bại, 0 lỗi chạy, 0 bỏ qua.** Gồm [15 kiểm thử M02 mới](../tests/test_feature_contact_identity.py), định dạng phone, địa chỉ có dấu, dữ liệu sai kiểu, cột thiếu, graph, namespace, giữ dữ liệu nguồn, trường hợp hợp lệ và từ chối model cùng số cột nhưng ngữ nghĩa cũ. Các kiểm thử B4 (9), B2 (12), M01 (23), causal, rules, bank/payment, noise/spec, nguồn thuế, train và shadow đều đạt. [Kết quả cuối cùng](m02_contact_identity_fix_20261024/post_fix.json), [log](m02_contact_identity_fix_20261024/post_fix.log).

Feature contract tăng từ v2 lên **`causal-evidence-20261024-v3`**, **vẫn 194 cột**, và fingerprint có bao gồm `identity.py`. Đã kiểm tra bằng chính model chạy thử M01 v2 có cùng 194 cột: sau khi loại riêng khác biệt tên định dạng dataset trong phép thử, model bị từ chối **chỉ vì semantic provenance không khớp**, không dựa vào lệch độ rộng ma trận. Cache v2 cũng bị từ chối. Không ép tương thích bằng cách sửa nhãn phiên bản trên artifact cũ.

Một IF v3 mới đã chạy thử trong thư mục riêng: **12 dòng train, 6 calibration, 6 evaluation; 0 dòng evaluation dùng để fit/hiệu chỉnh**. Cả 6 điểm evaluation hữu hạn. [Kết quả chạy thử và kiểm tra model v2](m02_contact_identity_fix_20261024/model_smoke.json), [huấn luyện](m02_contact_identity_fix_20261024/smoke_model/training_run.json), [shadow](m02_contact_identity_fix_20261024/smoke_scores/run.json). Đây là kiểm tra kỹ thuật trên fixture tổng hợp, không thay thế model cohort vận hành hay kết luận rà độc lập, không đo lợi ích IF so baseline.

[Bảo toàn đầu vào](m02_contact_identity_fix_20261024/verification.json): **2.343 tệp đã khóa không đổi checksum**, gồm nguồn, model và bằng chứng M01/B2/B4. Chỉ đổi ba tệp mã hiện có `features.py`, `rules.py`, `feature_contract.py`, thêm module chuẩn hóa và tệp test mới. `rules.py` chuyển hàm chuẩn hóa sang module dùng chung; logic sửa B4/R02 vẫn được kiểm tra hồi quy. Không ghi đè cache/model/shadow/hàng đợi/phiếu rà đã chốt.

**M03 vẫn mở:** lượt này không quyết định quan hệ feature là hiện hành hay lịch sử, không gỡ counter contact hợp lệ cũ khi sửa master và không thay UnionFind lịch sử bằng graph có thể gỡ cạnh. Không suy từ việc chặn khóa rỗng rằng vấn đề cập nhật quan hệ đã được đóng.

Chưa dựng lại cache/model hai cohort vận hành hoặc phát hành lại app. Trước khi chạy IF với ngữ nghĩa mới cần cache và model v3 được dựng/huấn luyện tương ứng, vẫn giữ các cửa sổ train/calibration/evaluation riêng.
