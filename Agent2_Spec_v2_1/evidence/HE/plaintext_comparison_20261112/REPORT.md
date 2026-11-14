# CR-038 — Bảng đối chiếu rõ/HE, READY_FOR_REVIEW

Đã xây và chạy bộ đo trên **đúng model/snapshot C001/C002 đang chuẩn bị cho Portal**, mỗi DN 5 giao dịch, 5 lượt đo mới sau một lượt làm nóng. Không fit lại model, không sửa phép tính, feature contract, replay hoặc ngưỡng. Trạng thái phép đo hoàn tất; chất lượng toàn luồng **PARTIAL** vì hard crash vẫn không khôi phục được.

Mở [bảng HTML](run/comparison.html), [bảng Markdown](run/REPORT.md), [JSON từng lượt/ca](run/comparison.json), [ảnh bảng](run/preview.png). [Hướng dẫn chạy lại](../../../../agent2/docs/HE_PLAINTEXT_COMPARISON.md).

| DN | Sai số tuyệt đối lớn nhất, cả 5 lượt | Thứ tự rõ/HE, mọi lượt | Chấm rõ p50 | HE p50 | HE p95 |
|---|---:|---|---:|---:|---:|
| C001 | 1,446058 × 10⁻⁶ | Khớp; 0 cặp đảo đáng kể | 117,79 ms | 1.977,61 ms | 2.072,64 ms |
| C002 | 1,445533 × 10⁻⁶ | Khớp; 0 cặp đảo đáng kể | 116,29 ms | 2.016,48 ms | 2.601,16 ms |

Thứ tự cùng là **T0 → T2 → T4 → T1 → T3**. Tất cả điểm đạt ngưỡng đã có sẵn `0.001 + 0.00001 * abs(rõ)`. Không điều chỉnh ngưỡng dựa kết quả. So đúng record/revision trong DN, model version, snapshot checksum, feature contract, preprocessing và as_of đã khóa. Mỗi lượt HE mới tạo một yêu cầu mới, không đo cache như lượt chấm mới.

## Khôi phục đo mới, cùng model/dữ liệu

| Loại sự cố | Thành công / ca xác nhận | Tỷ lệ quan sát | p50 khôi phục thành công |
|---|---:|---:|---:|
| Ngắt worker sau submit, trước claim | 2/2 | 100% | 1.904,56 ms |
| Khởi động lại có chờ phép tính hoàn tất | 2/2 | 100% | 660,99 ms |
| Hard crash khi đang tính, trước commit | **0/2** | **0%** | Không có |

Mỗi kiểu một ca/DN, cả 6 lần ngắt đều được xác nhận; không gộp thành một tỷ lệ chung hoặc suy rộng thành SLA. Ca khởi động lại có kiểm soát dùng `Jobs.close` drain rồi mở lại node/worker, không giả là đã bấm nút UI trong bộ đo này. [Nghiệm thu Portal trước](../portal_acceptance_20261112/REPORT.md) đã kiểm nút thực tế và nêu rõ giới hạn từng loại sự cố.

Hai ca hard crash giữ nguyên job và báo `WORKER_INTERRUPTED`, được tính **khôi phục thất bại**. Không gán thành công chỉ vì báo lỗi rõ hoặc giữ được ID. Bốn ca còn lại cùng job, một record worker mới và đủ 5 điểm khớp rõ. Worker có đúng **9 record/DN = 1 warmup + 5 lượt đo + 3 ca sự cố**, tổng 18, không có record tính trùng.

## Kiểm chứng

- [9 unit tests](focused_tests.log) đạt, [execution](focused_execution.json): join theo ID khi đảo dòng; phát hiện đảo hạng dù top-k trùng tất cả; điểm hòa/gần nhau; chia 0; unavailable/mã trùng/thiếu/nonfinite; timing lỗi; ca ngắt chưa xác nhận không được tính thành công hoặc đưa vào mẫu số.
- Một lượt tích hợp native HE thực tế: 10 lượt đo, 2 warmup, 6 ca sự cố trên model lưu sẵn. Bộ đo bật hard guards cấm fit/begin_fit/publish và đối chiếu model DB, snapshot DB, hai file khóa DPAPI trước/sau giữ nguyên. Tạo private state/auth tạm riêng; không mở khóa state live, đổi quyền hay dừng Portal/worker live.
- HTML được mở và kiểm 4 bảng, 2 DN, 3 loại sự cố, không lỗi JS; ảnh đã kiểm trực quan. Sửa riêng renderer để hai dòng tổng quan Markdown cùng nằm trước phần chi tiết; không chấm lại hoặc đổi số đo.
- Không chạy lại toàn bộ 159 HE/742 regression của CR-037 vì không đổi đường chạy sản phẩm. 9 test mới không được cộng vào kết quả bộ cũ để tuyên bố full suite đã chạy.

## Cách hiểu và bước tiếp

HE giữ đúng điểm và thứ tự trong mẫu này, đổi lại mất khoảng 17 lần thời gian pipeline rõ ở local. Hai timing đều có đọc model và feature; HE thêm signed readiness, context/mã hóa, checkpoint, HTTP worker, giải mã và polling. Không gồm fit/startup/Portal/browser trong timing bình thường; thời gian khôi phục có startup. Không so thời gian riêng kernel rõ với pipeline HE toàn phần.

5 giao dịch mô phỏng/DN không đủ kết luận precision/recall hoặc mức tin cậy nghiệp vụ. Top-5 trên 5 mẫu bao phủ tất cả, không chứng minh khả năng chọn thêm giao dịch hữu ích. Mẫu thời gian nhỏ; p95 mô tả đúng mẫu local, không phải cloud public. Chưa mở rộng bốn nhánh HE, 33 biến trong circuit, tỷ trọng ML hoặc queue.

**HE-AC-01 vẫn OPEN:** ưu tiên khôi phục cùng request đã khóa khi worker chết giữa compute, giữ chống replay/độc quyền thực thi và commit an toàn. Lượt này chỉ đo và báo cáo, chưa sửa cơ chế đó. R0–R6/D-11/D-12 và phê duyệt production giữ nguyên; không tự ký DONE.
