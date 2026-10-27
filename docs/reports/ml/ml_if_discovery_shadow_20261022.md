# IF tìm đầu mối ngoài baseline — shadow 22/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

**Đã thử mở admission từ IF: chọn thêm 38 chứng từ/đầu mối ngoài phạm vi baseline, giữ suất bắt buộc và trần ngân sách.** Đây là đầu mối mô hình đề xuất, chưa phải 38 bất thường nghiệp vụ được xác nhận. Ở kịch bản chính, 23 lượt baseline bị chậm tối đa 4 ngày và mức sử dụng thời gian tăng 760 phút ước tính. Đã chuẩn bị riêng 128 phiếu rà mù, outcome/phút thực tế vẫn trống.

## Protocol đã khóa

Phép thử cũ chỉ xếp lại hồ sơ đã admission nên không đo khả năng này. Nhánh mới giữ thứ tự baseline cho phần công việc thông thường và bổ sung admission IF; không đồng thời thay phép gộp hoặc rerank baseline bằng IF.

- Chính: tối đa **1 suất IF trong 5 hồ sơ/120 phút mỗi công ty/ngày**. Nhạy cảm: 2/5; ở mức 10 hồ sơ/240 phút tương ứng 2/10 và 4/10. Suất IF lấy sau các suất bắt buộc, không dùng được thì trả về baseline.
- Pin công việc baseline đã chọn có ưu tiên `cao_nhat` và công việc không phải loại transaction nếu còn pending; công việc hard đang pending khác cũng đi trước IF. Đối chứng 0% phải tái hiện đúng lịch, work key và chi phí baseline đã khóa.
- Chỉ lấy giao dịch evaluation vượt hoặc bằng **ngưỡng calibration đã lưu**: 001 là 0,5671807203; 003 là 0,5514013755. Không hạ ngưỡng hoặc lấy điểm dưới ngưỡng để lấp quota.
- Giao dịch/chứng từ chưa thuộc phạm vi baseline đã quan sát đến cutoff: kiểm tra thành viên, ngữ cảnh/bằng chứng pattern và đối tượng nguồn invoice; tích lũy phạm vi qua các ngày và các finding nguồn lịch sử. Không loại ứng viên sớm bằng thông tin baseline sẽ phát hiện trong tương lai.
- Một đầu mối giao dịch mỗi chứng từ; định danh theo công ty + invoice, nếu thiếu thì journal document, sau cùng transaction. Chọn điểm IF cao nhất đang có trong cùng chứng từ, chỉ rà chứng từ một lần mỗi nhánh. Đây là lượt triage singleton, không giả định tương đương khối lượng của hồ sơ baseline nhiều thành viên.
- Chi phí IF giả định 20 phút, kiểm tra thêm 30 phút; mọi lượt đều trừ vào trần phút và số suất hiện hành. Nếu baseline tạo hồ sơ liên quan sau lượt IF, vẫn tính công việc baseline riêng, không tự coi đã hoàn tất.
- Dữ liệu, điểm và eligibility phải có trước nửa đêm Việt Nam kế tiếp, loại trừ đúng cutoff. Chỉ dùng 11.811 điểm evaluation đã khóa, không fit/load/chấm model hoặc chấm train/calibration.

[Protocol](../../../examples/ml_if_discovery_shadow/protocol.json) được ghi trước khi xem số ứng viên; từng cohort có plan/hash đầu vào trước mô phỏng. Chạy 10 cấu hình/cohort, gồm 2 đối chứng 0%; không thay hàng đợi sản xuất hoặc gói review cũ.

## Phạm vi mở thêm

| Cohort | Điểm evaluation | Vượt ngưỡng IF | Chứng từ ngoài baseline được rà ở kịch bản chính |
|---|---:|---:|---:|
| 001 | 5.934 | 13 | 13 |
| 003 | 5.877 | 25 | 25 |
| **Tổng** | **11.811** | **38** | **38** |

38 giao dịch thuộc 38 chứng từ, đều có **0 điểm giao dịch từ luật**, không có operational alert/hard trigger dẫn tới admission. Tuy vậy **33/38 có hit/ngữ cảnh luật không cộng điểm**. “IF-only” ở đây là IF mở admission mới, không có nghĩa trước đó hoàn toàn không có dữ kiện hoặc ngữ cảnh luật.

Không chứng từ nào trong 38 chứng từ này được baseline đưa vào hồ sơ đến hết evaluation. Đây là kết luận trong replay/cửa sổ quan sát, không phải chứng minh baseline vĩnh viễn bỏ sót. Đầu mối được rà sau khi đủ điều kiện trung bình 0,08 ngày, chậm nhất 2 ngày ở cấu hình chính.

| Loại nghiệp vụ của đầu mối | Số chứng từ |
|---|---:|
| vendor_payment | 10 |
| stock_purchase | 8 |
| tools_purchase | 7 |
| material_purchase | 4 |
| selling_expense | 3 |
| material_issue | 3 |
| equipment_purchase | 2 |
| sales_invoice | 1 |

Không dùng nhãn/oracle để gọi các đầu mối này là gian lận hoặc xác định đầu mối nào hữu ích.

## Ngân sách và chi phí cơ hội

Ở mức chính 5/120, cả 809 lượt bắt buộc đã chọn của baseline được giữ; 0 vượt số suất/phút, 0 đẩy công việc bắt buộc. Toàn bộ **2.436 work scope baseline** vẫn được rà trong kỳ; không mất work scope lịch sử và tồn baseline cuối kỳ vẫn là 180. Có 23 work scope được rà muộn hơn (tối đa 4 ngày) và 6 work scope sớm hơn do lịch/packing chi phí thay đổi.

| Ngân sách/ngày | Trần suất IF | Phút giả định/lượt IF | Chứng từ IF mới | Work baseline bị chậm | Chậm nhất | Tổng phút ước tính |
|---|---:|---:|---:|---:|---:|---:|
| 5 / 120 | 0% | — | 0 | 0 | 0 | 54.001 |
| 5 / 120 | 20% | 20 | 38 | 23 | 4 ngày | 54.761 |
| 5 / 120 | 20% | 30 | 38 | 37 | 4 ngày | 55.141 |
| 5 / 120 | 40% | 20 | 38 | 25 | 4 ngày | 54.761 |
| 5 / 120 | 40% | 30 | 38 | 38 | 4 ngày | 55.141 |
| 10 / 240 | 0% | — | 0 | 0 | 0 | 56.481 |
| 10 / 240 | 20% | 20 | 38 | 9 | 1 ngày | 57.241 |
| 10 / 240 | 20% | 30 | 38 | 15 | 2 ngày | 57.621 |
| 10 / 240 | 40% | 20 | 38 | 9 | 1 ngày | 57.241 |
| 10 / 240 | 40% | 30 | 38 | 15 | 2 ngày | 57.621 |

Ngân sách giữ nguyên là **trần theo công ty/ngày**, không phải giả định tổng thời gian sử dụng thực tế bằng nhau. Với giả định 20 phút, IF dùng thêm 760 phút trong trần còn trống và có dịch lịch baseline; với 30 phút là 1.140 phút. Các số này chưa được đo bởi người rà. Chi phí rà tham chiếu/phân xử cũng phải ghi riêng khi thực hiện, không coi là miễn phí.

Nâng quota 20% lên 40% không mở thêm chứng từ trong mẫu này. Các cấu hình dùng cùng 38 chứng từ; không cộng số đầu mối giữa cấu hình. Việc mất/đổi suất cùng ngày trong `daily.csv` có thể do công việc đã làm sớm hơn; số “bị chậm” ở bảng được tính bằng ngày rà của **cùng work key** trong hai nhánh.

## Rà độc lập cần hoàn tất

Đã tạo [gói reviewer mù mới](../../../reports/ml_if_discovery_review_20261022/reviewer_packet.zip), giữ nguyên gói 69 phiếu trước đó:

| Nhóm mẫu, chỉ lưu nhãn nhóm ở private | Số phiếu |
|---|---:|
| Toàn bộ đầu mối IF mới được chọn | 38 |
| Snapshot baseline có lựa chọn/thời điểm khác giữa hai nhánh | 58 |
| Tham chiếu ngẫu nhiên cùng được chọn, 1/cohort/công ty | 16 |
| Tham chiếu ngẫu nhiên chứng từ evaluation chưa rà ở cả hai nhánh đến cuối kỳ, 1/cohort/công ty | 16 |
| **Tổng** | **128** |

58 snapshot baseline tương ứng công việc được rà ở cutoff khác nhau; không phải 58 vụ độc lập. Bằng chứng mỗi phiếu chỉ lấy dữ kiện có sẵn trước cutoff, ẩn nhánh/điểm/thứ hạng và dùng mã công ty. Phiếu ghi riêng hành động hữu ích, thiếu chứng từ, căn cứ, phút bấm giờ/đo khoảng và phân xử bởi người khác; chưa có người được phân công, tất cả kết luận/thời gian vẫn trống.

Mẫu tham chiếu là chẩn đoán phân tầng: nhóm chưa rà dùng cutoff cuối kỳ, không cùng thời điểm với mọi đầu mối IF. Không tự suy rộng precision, số vụ bỏ sót hoặc lợi ích quần thể từ bộ này. [Trạng thái validator ban đầu](../../../reports/ml_if_discovery_review_20261022/private/initial_validation/review_status.json): 128 pending, 0 kết luận độc lập hợp lệ, phút thực tế và gain là null.

## Bằng chứng và kết luận kỹ thuật

- [Tổng hợp](../../../reports/ml_if_discovery_shadow_20261022/summary.json), [bảng kịch bản](../../../reports/ml_if_discovery_shadow_20261022/scenario_summary.csv), [kiểm chứng](../../../reports/ml_if_discovery_shadow_20261022/verification.json).
- Mỗi cohort có `above_threshold_candidates.private.csv`, `analysis_plan.json`, `predictions_frozen.json`; từng cấu hình có `daily.csv`, `selections.private.csv`, `summary.json`. Tệp private giữ nội bộ, không gửi cho reviewer mù.
- [Cách chạy](../../../examples/ml_if_discovery_shadow/README.md), [mã mô phỏng](../../../sme_fraud/compare_if_discovery.py), [mã chuẩn bị review](../../../sme_fraud/if_discovery_review.py).

**71 kiểm thử liên quan đạt, gồm 22 kiểm thử mới; 1.482 tệp bảo toàn không đổi.** Đối chứng 0% khớp baseline tại từng ngày, cùng work key và phút. Model/ngưỡng/nguồn/luật/graph/A5 và kết quả trước giữ nguyên; 005 chỉ hash byte cho bảo toàn, không phân tích/chấm. Không gửi thông báo hoặc cập nhật hệ thống thật.

Phép thử đã đo được khả năng **mở phạm vi ngoài admission baseline** ở ngưỡng hiện tại. Cần hoàn tất rà độc lập và phút thực tế để xác định bao nhiêu đầu mối đáng xử lý, chi phí tài liệu/phân xử, và lợi ích có bù được 760–1.140 phút cùng độ trễ baseline hay không. Chưa có cơ sở bật admission IF trên hệ thống thật.
