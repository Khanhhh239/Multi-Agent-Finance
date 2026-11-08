# Chốt và triển khai M03 — quan hệ hiện hành tại cutoff — 24/10/2026

**Quyết định triển khai: dùng quan hệ hiện hành tại `posted_at` cho nhóm feature đang đối chiếu với B2.** Feature quan hệ phản ánh master và liên kết còn hiệu lực trong các phiên bản đã biết tại cutoff. Quan hệ từng có trong quá khứ không tự động tiếp tục đóng góp sau khi bị thay/gỡ. Đây là lựa chọn ngữ nghĩa; không kết luận rằng mọi thiết kế dùng quan hệ lịch sử đều sai hoặc bản thân hai probe M03 chứng minh rò dữ liệu tương lai.

Đổi tên rõ ràng bốn cột, giữ tổng số feature là **194**:

| Cột cũ | Cột v4 |
|---|---|
| `employee_phone_overlap` | `employee_phone_overlap_current` |
| `employee_address_overlap` | `employee_address_overlap_current` |
| `graph_employee_count` | `graph_employee_count_current` |
| `linked_vendor_count` | `linked_vendor_count_current` |

Không xuất alias tên cũ và không thêm cột “đã từng liên hệ” trong nhóm này. Hợp đồng ghi `state=current_as_of_posted_at`, `historical_features=[]`, `historical_window_days=null`: cửa sổ lịch sử không áp dụng cho snapshot hiện hành, không phải một cửa sổ tích lũy vô hạn. Tín hiệu quan hệ lịch sử nếu được bổ sung sau này cần tên, cửa sổ và contract riêng. Các feature lịch sử giao dịch khác như cửa sổ 3/7/30 ngày không bị đổi thành snapshot quan hệ.

[features.py](../sme_fraud/features.py) giảm khóa ngân hàng, điện thoại và địa chỉ cũ tại **công ty cũ**, xóa khóa bộ đếm về 0, rồi thêm khóa của snapshot nhân sự mới. Chuyển công ty, thay thông tin, giá trị rỗng và trường contact bị xóa khỏi snapshot đều không giữ counter cũ. Một nhân viên khác còn trùng thông tin vẫn được đếm đúng.

[identity_graph.py](../sme_fraud/identity_graph.py) là cơ chế dùng chung cho feature và [rules.py](../sme_fraud/rules.py): thay/gỡ slot bank/phone/representative theo phiên bản đã biết; giữ dấu kết thúc để mirror cũ hoặc cùng thời điểm không khôi phục cạnh đã gỡ; xử lý `active/revoked/deleted/inactive`; gỡ đúng công ty khi master chuyển phạm vi. Graph dựng lại UnionFind từ các cạnh hiện hành khi trạng thái thay đổi nên thành phần có thể tách ra. Metadata đếm nhân sự/NCC chỉ lấy các master hiện hành thuộc công ty tương ứng. `KnownGraph` vẫn truy cập được qua API cũ của rules; lớp dùng chung giữ cách tạo scope hồ sơ và đường bằng chứng của rules.

Snapshot master dùng `recorded_at`, liên kết dùng `observed_at`, đều phải **không sau cutoff**, bao gồm đúng thời điểm đó. Master ưu tiên hơn mirror cùng timestamp. Bản ghi master trùng hệt được gộp; hai snapshot khác nội dung cùng ID/timestamp bị từ chối để tránh kết quả phụ thuộc thứ tự dòng. Phần representative được thay/gỡ khi snapshot cung cấp trường tương ứng. [Đặc tả chi tiết](m03_current_relationship_fix_20261024/relationship_semantics.md).

| Ca tái hiện | Trước thay master | Giao dịch sau thay master |
|---|---|---|
| Nhân viên đổi phone/address | Overlap hiện hành 1/1; graph employee count 1 | **Overlap 0/0; graph count 0; B2 0 điểm** |
| NCC đổi phone để tách khỏi nhân viên | Phone overlap 1; graph employee count 1 | **Phone overlap 0; graph count 0; B2 0 điểm** |

Trong cả hai ca, **toàn bộ feature và hit của giao dịch trước thời điểm thay đổi giữ nguyên** khi thêm phiên bản master và giao dịch về sau. Các liên kết thực sự còn hiệu lực, người khác còn trùng thông tin và quan hệ được tái lập sau đó vẫn được nhận diện. [Bằng chứng sau triển khai](m03_current_relationship_fix_20261024/reproduction_after.json). Hai probe cũ vẫn được giữ tại [rà soát gốc](deep_rules_ml_audit_20261023/edge_probes.json).

**317 kiểm thử thuộc 20 module đạt; 0 thất bại, 0 lỗi chạy, 0 bỏ qua.** Gồm [19 kiểm thử M03 mới](../tests/test_current_relationship_features.py): thay/xóa master, chuyển công ty và chuyển về, người còn trùng thông tin, ngân hàng khác institution, thay người đại diện, thu hồi/replacement, mirror cũ, ranh giới cutoff và batch đồng thời, tách nhóm NCC, master không có mirror, bất biến lịch sử, thứ tự nguồn và xung đột snapshot. Các bộ B4/B2/M01/M02, graph, case identity, kế toán, train và shadow đều đạt. Hai tệp test cũ chỉ đổi tên cột trong assertions để theo schema hiện hành, giữ nguyên kỳ vọng hành vi. [Kết quả cuối cùng](m03_current_relationship_fix_20261024/post_fix.json), [log](m03_current_relationship_fix_20261024/post_fix.log).

Đã kiểm tra đường xuất/kiểm định dữ liệu bằng **fixture mới 10.000 giao dịch**, có timestamp khả dụng tường minh, gồm 50 ca mô phỏng và 500 hard negative; kiểm tra schema, khóa ngoại, chronology, tình huống và cân bằng kế toán đều đạt. Nhãn/split của fixture tạm này chỉ dùng cho kiểm định cấu trúc, không đưa vào detector/model. Đây không phải khẳng định các nguồn legacy thiếu ngày biết đã đủ dữ kiện M01 hoặc đã vượt kiểm định tình huống; không tự thêm timestamp vào nguồn đã khóa. [Kết quả kiểm định fixture](m03_current_relationship_fix_20261024/fresh_dataset_validation.json).

Feature contract mới là **`causal-evidence-20261024-v4`**, pin module graph dùng chung và đặc tả ngữ nghĩa quan hệ. Cache/model v3 bị từ chối dù cùng 194 cột, do tên cột và semantic fingerprint khác. IF v4 mới chạy được trong thư mục riêng với **12 dòng train, 6 calibration, 6 evaluation; 0 dòng evaluation tham gia fit/hiệu chỉnh**. Fixture có thay master trong evaluation: 19 dòng trước thay có quan hệ, các dòng sau thay không giữ quan hệ cũ. Đây là kiểm tra kỹ thuật, chưa đo hiệu quả tìm hồ sơ so baseline. [Kiểm tra tương thích và chạy thử model](m03_current_relationship_fix_20261024/model_smoke.json), [huấn luyện](m03_current_relationship_fix_20261024/smoke_model/training_run.json), [shadow](m03_current_relationship_fix_20261024/smoke_scores/run.json).

[Bảo toàn](m03_current_relationship_fix_20261024/verification.json): **2.378 tệp đã khóa không đổi checksum**, gồm nguồn/model và các bằng chứng đã bàn giao. Không ghi đè cache/model, hàng đợi, shadow hoặc phiếu rà đã chốt. M03 đã có đặc tả và triển khai theo hướng hiện hành; chưa tái huấn luyện model hai cohort vận hành hoặc phát hành lại app. Các kết luận hiệu quả ML vẫn cần shadow cùng ngân sách và rà độc lập trên phiên bản mới.
