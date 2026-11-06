# Chọn cấu hình thống nhất và kiểm tra gate

**Ngày 04/11/2026. Trạng thái: đề xuất cấu hình tích hợp, hậu kiểm bằng chứng
đã lưu. Chưa kích hoạt model và chưa nghiệm thu pipeline mới.**

Đề xuất dùng **LightGBM competing risks v6 làm lõi chung cho T1/T2**, nối
với T4, T5 và bộ tổng hợp số dư T6 theo một hợp đồng xác suất. Đây là lựa
chọn để tích hợp tiếp; **chưa có bằng chứng cấu hình này qua các gate sản
phẩm**. Bản kiểm tra này không yêu cầu ứng viên phải giảm CRPS 5% so với v6;
đó là điều kiện thay thế trong nghiên cứu unified trước, không phải G1–G18.

Không có một model duy nhất thay được các nhiệm vụ đối soát, dự báo doanh
thu, tính nghĩa vụ chi và mô phỏng số dư. Thống nhất ở đây nghĩa là các phần
dùng cùng định nghĩa tiền, ngày cắt, trạng thái và xác suất; T1/T2 cùng lấy
kết quả từ một classifier. Lựa chọn này được đưa ra sau khi đã xem kết quả
v6/v1/v2, không phải một lựa chọn đăng ký trước trên test mới.

**1. Cấu hình đề xuất và phạm vi đáp ứng.**

| Phần | Cấu hình và hợp đồng |
|---|---|
| T0/T9 | Kiểm chất lượng và đối soát đầu vào; giữ giao dịch có ngày quan sát, số tiền áp dụng, phí và phần chưa phân bổ. Chưa có phép đo E2E với nhãn T9 ước lượng cho cấu hình v6 này. |
| T1/T2 | Một model v6 dự báo hazard chung open/paid/write-off; lấy CIF paid và write-off từ cùng phép tích lũy. Giữ calibration identity đã được chọn trên nguồn. Credit-only hiện có xác suất 0 vì train không có nhãn. |
| T2 xuất ra | Xác suất write-off trước một chân trời xác định. Không gọi xác suất này là “không bao giờ trả”, xác suất SBA default, hoặc xác suất không thu trong 13 tuần. |
| T6 thu hóa đơn mở | `PMF_paid[k] = F_paid(7k) − F_paid(7(k−1))`. Giữ nguyên khối xác suất ngoài chân trời; không chuẩn hóa tổng PMF về 1, không nhân thêm `1 − p_bad`, không lấy mẫu T2 riêng. |
| Số tiền thu | Dồn số dư mở tại origin vào tuần tất toán đã lấy mẫu, tối đa một lần/hóa đơn. Không cộng cash head. Đây vẫn là xấp xỉ tiền thu; không mô phỏng trả từng phần hoặc credit tương lai. |
| T4 | Giữ mô hình doanh thu quantile riêng; chuyển doanh thu mới sang tiền thu bằng kernel lịch sử as-of, tránh cộng lại hóa đơn đã nằm trong danh mục mở. |
| T5 và sổ tiền | Giữ lịch chi biết tại origin, kịch bản chi chưa biết và dòng phi AR. Dùng adapter theo ngày của v2/r3: tách tiền áp dụng/tiền ngân hàng/phí, rút vốn đúng ngày, RNG riêng từng thành phần. |
| T6 phụ thuộc | Cấu hình đã có số đo dùng copula-t, `nu=4`, `rho_firm=0.15`, `rho_customer=0.15`; 1.000 đường/lần, ba MC replicate. Các tham số này là cấu hình kiểm tra hiện có, chưa khẳng định tối ưu. |
| ACI/cảnh báo | Cần kiểm lại riêng trên các origin tuần với kết quả đã chín. Điểm bank đang dùng trong audit là khoảng gốc, **chưa có ACI**. Không chuyển bộ hiệu chỉnh/chính sách cũ sang rồi mặc định đã đạt. |

V6 đã có một phân phối chung cho nguyên nhân đóng, nên giải quyết được việc
T1 và T2 phát ra xác suất mâu thuẫn hoặc T6 trừ rủi ro hai lần. T6 hiện chỉ
lấy mẫu biên paid; nó chưa xuất trạng thái write-off từng đường. Nếu giao
diện cần các trạng thái đó, phải lấy mẫu một kết quả chung từ các nguyên
nhân/tuần của cùng model, thay vì thêm một lần lấy mẫu T2 độc lập.

Đây là **phương án tích hợp đơn giản hơn hướng thu tiền từng phần** trong
đề xuất ngày 03/11. Nếu trả từng phần theo tuần là yêu cầu bắt buộc thì v6
chưa đáp ứng; prototype v2 mới thực hiện hợp đồng đó, nhưng cũng chưa có
bằng chứng qua gate. Vì vậy không đổi tên v6 thành mô hình quá trình thu
tiền mới, không diễn giải lựa chọn này là v6 đã hoàn thành kế hoạch unified.

V2 được giữ làm kết quả nghiên cứu. Bản sửa của adapter bank có thể dùng
cùng lõi v6; không cần đưa classifier chuyển trạng thái v2 vào mới sử dụng
được các sửa lỗi phí, thời điểm hoặc phạm vi dòng tiền. Tổ hợp v6 + adapter
này đã có số đo trong nhánh comparator của v2/r3. Dịch vụ hiện vẫn dùng
`HazardGBM` qua registry/nightly, chưa tự nhận được model đa lớp v6.

**2. Kiểm trực tiếp các ngưỡng liên quan.**

Audit chỉ đọc artifact đã lưu, kiểm hash model/source/CSV và tính lại các
chỉ số có thể đối chiếu. Không train, chọn lại calibration, chỉnh ngưỡng
hay dự báo lại test. Hai chẩn đoán sau ánh xạ ngưỡng hiện hành sang dữ liệu
đã có; chúng **không thay một lần chạy đầy đủ giao thức cổng**.

**G4 — xác suất paid trong 4 tuần.** Cổng sản phẩm dùng ECE với 10 khoảng
xác suất bằng nhau; báo cáo v6 dùng nhóm quantile. Vì vậy audit tính lại
bằng hàm ECE của sản phẩm trên dự báo từng hóa đơn, không chép cột ECE cũ.

| World | Hóa đơn | ECE 4 tuần, khoảng bằng nhau | So ngưỡng ≤0,05 |
|---|---:|---:|---|
| validation_000 | 12.169 | 0,048304 | Đạt ngưỡng số |
| validation_001 | 12.993 | 0,023665 | Đạt ngưỡng số |
| test_000 | 5.772 | **0,071924** | **Chưa đạt** |
| test_001 | 14.564 | 0,027616 | Đạt ngưỡng số |
| v6 fresh_000 | 5.280 | 0,049097 | Đạt ngưỡng số |
| v6 fresh_001 | 14.443 | 0,025736 | Đạt ngưỡng số |

Đây là 65.221 anchor đầu tiên đủ điều kiện, không phải hai origin nguồn
của G4. Không đổi sáu dòng này thành kết quả G4 chính thức. Chúng cho thấy
lệch xác suất vẫn tồn tại; hai World fresh qua ngưỡng không xóa kết quả xấu
của World cũ.

**G12 — phân phối số dư.** Tính lại coverage từ P10/P90 và số dư thật từng
tuần trên bốn World v2 mới đã lưu, 32 công ty, hai origin/công ty. Chia đúng
hai chân trời tuần 1–4 và 5–13 thay vì chỉ lấy trung bình cả 13 tuần:

| Model thu tiền, cùng adapter bank | Tuần 1–4 | Tuần 5–13 | Ngưỡng G12 |
|---|---:|---:|---|
| **V6 được đề xuất** | **85,55%** | **73,61%** | 75–85% ở cả hai |
| Unified v2 | 83,98% | 69,97% | 75–85% ở cả hai |

V6 lệch ở cả hai khoảng, dù tuần 1–4 chỉ cao hơn cận trên khoảng 0,55 điểm
phần trăm. Tuần 5–13 của World 000 và 002 cùng chỉ đạt 62,50%; không thể
dùng trung bình gộp để che phần thiếu phủ đó. Cần kiểm hiệu chỉnh trên nguồn
và chấm lại cả coverage lẫn độ rộng/interval score.

G12 đầy đủ còn yêu cầu nhãn T9 ước lượng, ACI, IS80 thắng bốn đối chứng và
Brier thiếu tiền thắng naive. Benchmark v2/r3 không có đủ các thành phần
này; Brier tốt hơn unified v2 hoặc CRPS thấp hơn không thay được chúng.
Kết luận phù hợp là **chẩn đoán khoảng gốc chưa đạt và chưa đủ giao thức
để nghiệm thu G12 cho ứng viên**. G12 hiện hành của pipeline cũ vẫn giữ
`passed` theo CSV riêng của pipeline đó.

Nguồn audit:
[ECE tính lại](../../outputs/analysis/unified_candidate_gates_20261104/g4_equal_width_diagnostic.csv),
[coverage theo World/chân trời](../../outputs/analysis/unified_candidate_gates_20261104/g12_coverage_diagnostic.csv),
[coverage theo công ty](../../outputs/analysis/unified_candidate_gates_20261104/g12_firm_coverage_diagnostic.csv).

**3. Những gate chưa được lựa chọn model này giải quyết.**

| Gate/nhóm | Bằng chứng hiện hành | Trạng thái đối với ứng viên |
|---|---|---|
| G1/G2 | Pipeline cũ đạt WAPE/IBS so B1 | Chưa đo v6 so B1 trên cùng hai origin/risk set; Brier bốn trạng thái ngày 91 không phải IBS 13 tuần. |
| G3/G4 | Pipeline cũ chưa đạt | V6 chưa có đối chiếu CQR theo G3; G4 còn lỗi trong chẩn đoán trên. |
| G5/G6 | BLEND trên dữ liệu thật đã đạt | Không chuyển kết quả BLEND sang v6; chưa kiểm v6 trên các miền thật đó. |
| G8 | Chưa đạt trên SBA | Nhãn khoản vay khác nhãn write-off hóa đơn; không đánh dấu đạt hoặc bỏ cổng chỉ vì gộp T1/T2. Cần chủ dự án chốt lại phạm vi nếu muốn thay định nghĩa nhiệm vụ T2. |
| G9/G10 | Các mô hình T4 cũ có bằng chứng đạt | Cùng họ LightGBM không đủ kế thừa gate cho weights T4 refit của v2/r3. |
| G11 | Ngoài phạm vi synthetic, vẫn cần ở pilot thật | Chưa có chuyên gia xác minh cho pilot thật. |
| **G12** | Pipeline cũ đạt | Cấu hình v6 mới chưa được nghiệm thu; khoảng gốc thiếu phủ ở kỳ xa. |
| **G13** | **Trượt** | Pipeline cũ phát hiện sớm 93,75%, lead trung vị 11,64 tuần, nhưng **2,08 báo giả/công ty-năm**, cổng ≤1. Ứng viên chưa có backtest cảnh báo theo đợt; hai origin không đủ đo. |
| **G15** | **Trượt** | T9 đang chọn: **F1 0,7964 <0,80**, **precision 0,9246 <0,95**; coverage 0,7507 và MAE ngày 1,85 qua ngưỡng. Đổi model thu tiền không tự sửa nhãn còn thiếu/sai. |
| G16 | T0 hiện có bằng chứng đạt | Giữ bằng chứng thành phần; cần kiểm biên dữ liệu khi tích hợp hợp đồng mới. |
| G7/G14/G17/G18 | Kết quả pipeline cũ hoặc các ablation riêng | Chưa có phép thử tương ứng cho tổ hợp v6 này; không tự kế thừa trạng thái cũ. |

Các gate bắt buộc của giai đoạn synthetic hiện là G1/G2/G5/G9/G12/G13/G15/G16;
bảng sản phẩm đang thiếu G13 và G15. Với ứng viên mới, còn phải đo lại các
gate bị ảnh hưởng bởi model/weights/nhãn/adapter thay đổi, dù bảng cũ ghi
đạt. G3/G4 là điều kiện chất lượng riêng, không tự thêm chúng vào danh sách
cổng bắt buộc trong script hiện hành. Pilot thật vẫn **NO-GO**.

Nguồn: [GATES_CURRENT](GATES_CURRENT.md),
[mã xét cổng](../../scripts/evaluate_gates.py),
[G13 CSV](../../outputs/e2e/protocol/alert_policy_v2.csv),
[G15 CSV](../../outputs/t9/sprint3/target_metrics.csv),
[bảng ánh xạ đủ G1–G18](../../outputs/analysis/unified_candidate_gates_20261104/gate_mapping.csv).

**4. Thứ tự thực hiện để hướng tới qua gate.**

1. Khóa cấu hình v6 và hợp đồng đầu vào/đầu ra trong một adapter riêng;
   bổ sung registry/API cho model đa lớp và trạng thái, không ép vào loader
   `HazardGBM` nhị phân. Kiểm danh mục rỗng, dư xác suất ngoài 13 tuần, số
   tiền, phí, credit đã biết và không nhân rủi ro hai lần. Chưa bật làm mặc định.
2. Ưu tiên độ phủ/độ chính xác nhãn T9 và kiểm G15, rồi dựng feature/lịch
   sử từ phần thực sự quan sát được. Cần đo mức suy giảm từ nhãn đối soát
   sang dự báo; cohort dùng payments synthetic sạch chưa trả lời được.
3. Chạy cùng pipeline trên nguồn theo origin tuần, so B1 cho G1/G2, kiểm
   calibration/CQR cho G3/G4; hiệu chỉnh ACI và chọn chính sách cảnh báo
   trên nguồn với kết quả đã chín. Không chỉnh theo các World đã xem.
4. Khóa weights, calibration, ACI, chính sách và ngân sách; xác nhận E2E
   trên tập mới theo G12 đủ bốn đối chứng và G13 theo đợt cảnh báo. Đo lại
   latency toàn pipeline; số 14,89 giây của rollout v2 không phải latency
   v6 hay dịch vụ. Chỉ xét kích hoạt sau khi có bằng chứng gate tương ứng.

Lựa chọn thực dụng hiện tại là **v6 để tích hợp tiếp, chưa phải v6 để phát
hành**. Không cần tiếp tục thêm classifier/head chỉ để tìm model thắng v6;
việc còn thiếu chủ yếu là đo và nối đúng pipeline, nhãn T9, hiệu chỉnh số
dư và cảnh báo. Cũng chưa có cơ sở cam kết sửa các phần đó chắc chắn qua gate.

**Tái lập audit.**

```powershell
.\.venv\Scripts\python.exe -B -m analysis.audit_unified_candidate_gates
```

Mã: [analysis/audit_unified_candidate_gates.py](../../analysis/audit_unified_candidate_gates.py).
[candidate.json](../../outputs/analysis/unified_candidate_gates_20261104/candidate.json)
ghi cấu hình đề xuất, không phải bản đăng ký/kích hoạt model.
[verification.json](../../outputs/analysis/unified_candidate_gates_20261104/verification.json)
ghi hash đầu vào và kết luận. Mọi file cổng, model, weights và source thí
nghiệm được audit giữ nguyên; đầu ra chỉ ghi vào thư mục analysis riêng.
