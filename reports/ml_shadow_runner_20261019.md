# ML: runner chỉ xuất điểm — 19/10/2026

Đã bổ sung runner kỹ thuật cho feature cache tương thích. Phần này có thể hoàn thiện khi chưa có dữ liệu thật. **Chưa chứng minh lợi ích ML trên SME và chưa kết nối luồng shadow nguồn thật.** [Audit trước đó](ml_pilot_readiness_20261019.md) được giữ nguyên làm lịch sử.

## Đã triển khai

- [Module và CLI](../sme_fraud/shadow_scoring.py) chỉ gọi `score_samples` trên model đã có; không huấn luyện, hiệu chỉnh ngưỡng hoặc gọi benchmark có nhãn.
- Scope chỉ định công ty, thời gian bắt đầu/kết thúc có múi giờ và tham chiếu nguồn; đầu cuối loại trừ. Kiểm tra ID, coverage, feature hữu hạn và đúng allowlist có thứ tự.
- Kiểm tra checksum model/cache/nguồn, hợp đồng ngữ nghĩa và phiên bản sklearn/định dạng. Bất tương thích giữ nguyên lỗi; không ép model benchmark nhận định dạng nguồn mới.
- Xuất điểm cùng manifest/provenance/hash vào thư mục mới; không đọc labels/splits, đổi hàng đợi/kết luận/thông báo hoặc phân loại gian lận. Khi lỗi, không công bố run dở dang.

## Kiểm chứng kỹ thuật

[Kết quả máy đọc cuối](ml_shadow_runner_20261019/final_verification/verification.json), [kiểm thử](ml_shadow_runner_20261019/final_verification/tests.json), [log](ml_shadow_runner_20261019/final_verification/tests.log). Chi tiết số dòng và kiểm tra lặp được ghi riêng cho 001/003 trong JSON.

**28 kiểm thử liên quan đạt**, gồm 17 kiểm thử runner mới và 11 kiểm thử hợp đồng/model hiện có. Mỗi cache 001/003 có **25.000 dòng** trong scope mô phỏng đã chọn; tổng 50.000 dòng của hai cache, chạy hai lượt thành 100.000 lượt tính điểm. Hai lượt cho cùng hash CSV ở từng cache. Hai trường hợp định dạng nguồn mới bị từ chối trước tính điểm. Hash **1.209 tệp đã khóa** và 10 tệp model/manifest/feature của audit trước không đổi. Không chạy lại toàn bộ suite của các thành phần web/rules trong đợt thêm module độc lập này.

Đã sửa lỗi ACL Windows ở cách công bố thư mục kết quả: output kế thừa quyền của thư mục đích, vẫn được công bố sau khi ghi hoàn chỉnh. Bốn thư mục của lượt thử đầu đã được khôi phục quyền kế thừa; lượt kiểm chứng cuối dùng cách ghi đã sửa. Kết quả cũ của lần thử đầu giữ trong thư mục cha để truy vết.

Hai model/cache benchmark tương thích được chạy hai lần với kích thước batch khác nhau, chỉ trên cửa sổ validation mô phỏng 01/01–30/06/2025. So sánh hash CSV để kiểm tra điểm tái lập. Đây là dữ liệu đã dùng cho hiệu chỉnh model; không dùng lượt chạy này để báo precision/recall, lợi ích thực địa hoặc thành tích trên giai đoạn giữ kín.

Hai cặp model benchmark/nguồn mô phỏng mới tiếp tục bị chặn trước khi gọi tính điểm với `dataset_format_version_mismatch`. Không thay các model, feature cache hoặc metadata để vượt kiểm tra. Không gọi fit trong replay; 005 chỉ băm opaque để bảo toàn, không parse/nạp/chấm hay dùng oracle. Nguồn, kết quả detector và hàng đợi đã khóa giữ nguyên.

## Phần còn chờ

| Cổng | Trạng thái |
|---|---|
| Runner score-only từ cache | Đã triển khai, có kiểm chứng kỹ thuật trên mô phỏng |
| Dựng feature từ bản xuất SME thật và nối pipeline | Chưa có nguồn thật đã nghiệm thu; runner hiện không làm bước importer/feature producer |
| Model phù hợp định dạng nguồn mới | Chưa có artifact thay thế đã nghiệm thu; model cũ vẫn bị chặn |
| Cửa sổ train/calibration/đánh giá, phạm vi công ty | Runner chưa chứng nhận không chồng lấn; cần provenance và kiểm tra trước pilot |
| Protocol so sánh và tiêu chí lợi ích | Bản nháp, chưa phê duyệt |
| Review kế toán độc lập / lợi ích vận hành | Chưa có / chưa đo |

Tiếp theo: chọn SME/quy trình và người rà; xác nhận mapping/nguồn và thiết kế so sánh; dựng cache/model phù hợp rồi kiểm tra thời điểm trước khi nối suy luận nguồn thật. Giữ baseline rules + graph + A5 trong lúc thu bằng chứng; chưa cần thêm model phức tạp hơn.

[Hướng dẫn chạy và phạm vi giới hạn](../examples/ml_shadow_runner/README.md). Trạng thái tổng vẫn `awaiting_real_data`; hoàn tất runner kỹ thuật không đóng cổng nghiệm thu hiệu quả ML.
