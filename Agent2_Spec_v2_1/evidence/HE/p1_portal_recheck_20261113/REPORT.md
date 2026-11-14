# Đối chiếu P1 trên Portal — 13/11/2026

**READY_FOR_REVIEW cho kiểm thử kỹ thuật — C001 và C002 đều đã đạt 8/8 đối chiếu nguồn/engine, kiểm tra giao diện và reload giữ nguyên lần chạy trên Portal; chưa nghiệm thu nghiệp vụ.**

Phạm vi người dùng giao: chạy lại trên Portal và đối chiếu P1 với engine luật,
phép cộng thủ công và các bản ghi nguồn. C001/C002 là dữ liệu mô phỏng; không
ghi kết luận nghiệp vụ, nhãn xác minh hoặc đánh giá hiệu quả ML.

## Lỗi đã tìm thấy và sửa

1. Phiếu rà chỉ lấy căn cứ tạo feature, bỏ sót căn cứ riêng của P1. Ca đồng
   thời thiếu giao dịch/phân bổ của thành viên còn lại và khai báo phạm vi
   lịch sử. `review_api.py` hiện hợp nhất các tham chiếu do kết quả server ghim,
   kiểm tra cùng snapshot/doanh nghiệp và thời điểm; không nhận tham chiếu từ
   trình duyệt. Giao diện thêm liên kết hóa đơn, phân bổ, khoản điều chỉnh và
   phạm vi lịch sử. Đã khởi động lại riêng Agent2 qua Portal để nạp thay đổi;
   Portal và kho model/khóa/snapshot giữ nguyên.
2. Portal có thể xóa phiên vừa đăng nhập khi phản hồi `/api/state` từ trước
   đăng nhập đến muộn. Trình kiểm thử live quan sát UI đã mở khóa nhưng Agent2
   trả 401. Kịch bản Chrome cô lập tái hiện việc phản hồi cũ làm mất phiên;
   sau sửa kiểm tra phiên bản phiên, phản hồi cũ không xóa đăng nhập mới và
   không mở lại màn hình sau đăng xuất. TTL/quyền/mật khẩu giữ nguyên.
3. Trình kiểm thử live trước đây đóng cửa sổ khi đọc quyền bị lỗi, làm mất
   cửa sổ đăng nhập của người dùng. Đã đổi để giữ cửa sổ và in lỗi có trạng
   thái HTTP; không xuất mật khẩu hoặc token.
4. Trình kiểm thử đọc `innerText` của mã yêu cầu nằm trong mục chi tiết đang
   thu gọn, nhận chuỗi rỗng dù server đã tạo yêu cầu. Đã đổi sang lấy mã từ
   phản hồi POST server; khi mở lịch sử thì mở mục thu gọn trước. Bộ kiểm thử
   mới giữ browser/page qua retry và có kết nối điều khiển riêng trên loopback
   để sửa công cụ mà không bỏ cửa sổ đăng nhập.

## Bằng chứng hiện có

| Tệp | Kết quả và giới hạn |
|---|---|
| review_focused.json | 21 kiểm thử qua, gồm API/kho phiếu/nguồn P1 và kiểm tra căn cứ mới |
| comparison_focused.json | 9 kiểm thử qua: 4 ca đối chiếu và 5 ca căn cứ; có giao với bộ 21 |
| login_race_before.json | Tái hiện lỗi: phản hồi trước đăng nhập làm API trở về 401 |
| login_race_after.json | Hai kiểm tra qua: giữ phiên mới; không hiện dữ liệu cũ sau đăng xuất |
| portal_sso_regression.json | 16 kiểm tra trình duyệt qua trong Portal/Agent2 cô lập |
| runner_ui_regression.json | Bắt mã yêu cầu từ server, mở lại 5 kết quả CKKS và không tạo yêu cầu trùng; fixture cô lập, không phải HE4 live |
| live_receipt_partial.json | Trạng thái dở trước khi job C002 cũ hết hạn (`HE4_EXPIRED`); giữ làm lịch sử |
| live_receipt.json, live_report.json | Biên nhận và báo cáo hoàn tất Portal live (`passed`, C001 8/8 + C002 8/8, `login_count: 2`, `portal_timeout_unchanged: true`, `browser_errors: []`) |
| native_worker_counts.json | Kiểm tra read-only worker HE4 cho C001 và C002: mỗi DN đủ 12/12 phép tính `done`, `generation=1` (`rules: 6`, `graph: 1`, `statistics: 5`) |
| C001-reconciliation.json | HE live khớp engine và phép cộng nguồn ở đủ 8 giao dịch; không ghi phản hồi nghiệp vụ |
| C001-result.json, C001-review-packet.json | Kết quả và 8 phiếu từ API Portal; 0 phiếu ghi kết luận, không đủ điều kiện train |
| C002-reconciliation.json | HE live khớp engine và phép cộng nguồn ở đủ 8 giao dịch (`all_rows_match: true`); không ghi phản hồi nghiệp vụ |
| C002-result.json, C002-review-packet.json | Kết quả và 8 phiếu C002 từ API Portal (`status: completed`); 0 phiếu ghi kết luận, không đủ điều kiện train |
| cross-company-http.json | 4 GET dùng sai đường dẫn DN cho snapshot/job đều 404, không trả bản ghi riêng tư; cùng principal được cấp cả C001/C002 |

## Đối chiếu live C001 đã hoàn tất

- Run `herun_a41f1c89c0b04bb9bd85021731bdaf7f`, snapshot
  `snp_25b7fd36815346619377fd430b9002fc`. Nguồn lấy từ Portal khớp checksum
  `ff1ed8a9699beece6a1949e5c9f4cd9d2deb438a76518e9b6ee1fa38fd43864b`.
- T02: 6 + 3 = 9 triệu / hóa đơn 10 triệu, chưa trúng P1.
- T03: 9 + 3 = 12 triệu / 10 triệu, trúng P1, vượt 2 triệu.
- T04: điều chỉnh −4 triệu giữ liên kết khoản gốc, P1 `not_applicable`.
  T05 dùng đủ 6 + 3 + 3 − 4 = 8 triệu lịch sử, trả thêm 1 thành 9 / 10 triệu.
- T06/T07: từng khoản 4 / 6 triệu không trúng riêng; nhóm đồng thời
  4 + 4 = 8 / 6 triệu trúng nhóm, vượt 2 triệu. Phiếu có giao dịch/phân bổ
  của thành viên còn lại và khai báo `P1_COV_6`. Không cộng điểm nhóm hai lần.
- T08: có hóa đơn/phân bổ nhưng thiếu phạm vi lịch sử, giữ `unavailable`,
  `matched`/`score` null và lý do `p1_history_scope_missing`.
- Cả 12 phép tính HE4 đã hoàn tất: 6 P1, 1 đồ thị, 5 thống kê, dùng lại trong
  các dòng có đầu vào số giống nhau. ML CKKS là nhánh riêng. P1 khả dụng ở 6
  dòng, thống kê/đồ thị 8 dòng, ML 7 dòng; T01 có ML `input_out_of_domain`,
  không tự ép miền hoặc dùng điểm rõ thay thế.
- Mở 8 kết quả/8 phiếu, mở căn cứ và tải lại trang giữ cùng run. Đã xem ảnh
  giao diện T03 và phân bổ thành viên T07; nhãn vẫn là dữ liệu mô phỏng.
- Phiên cũ đã hết hạn; đăng nhập mới tiếp tục đúng run C001, không đổi snapshot,
  model hoặc khóa. Bộ kiểm thử đọc mã từ mục thu gọn sai đã được sửa; lỗi công
  cụ này không được tính là lỗi kết quả P1.

Các phép đối chiếu trong unit test dùng kết quả circuit rõ để thử bộ kiểm tra;
không phải bằng chứng tính HE thật hoặc chạy Portal live. Bằng chứng native HE
của bộ nguồn nằm riêng tại [p1_sources_20261113](../p1_sources_20261113/REPORT.md).
Không cộng các tập kiểm thử có giao nhau thành số lượng full suite.

## Đối chiếu live C002 đã hoàn tất

- Run `herun_83f30523ede5495a97a9957a07a000dc`, snapshot
  `snp_2b8bce04da224fc2aa71f94a496ccfed` (job cũ
  `herun_1df14750934b4adba8469f6fbba1290d` đã `HE4_EXPIRED` trước đó không được mở
  lại). Nguồn lấy từ Portal khớp checksum
  `199157151eb852be5c7f8a5a9e2040617ce149ae6250594bd7ec27fcc255050a`.
- T01: 18 triệu / hóa đơn `P1_I_BASE` 30 triệu (`evaluated_no_hit`, 0 điểm).
- T02: 18 + 9 = 27 triệu / 30 triệu (`evaluated_no_hit`, 0 điểm).
- T03: 27 + 9 = 36 triệu / 30 triệu, trúng P1 (`evaluated_hit`, 20 điểm), vượt
  6 triệu.
- T04: điều chỉnh −12 triệu giữ liên kết khoản gốc `P1_T01`, P1
  `not_applicable`. T05 dùng đủ 18 + 9 + 9 − 12 = 24 triệu lịch sử, trả thêm 3
  thành 27 / 30 triệu (`evaluated_no_hit`, 0 điểm).
- T06/T07: từng khoản 12 / 18 triệu trên `P1_I_GROUP` không trúng riêng
  (`evaluated_no_hit`, 0 điểm); nhóm đồng thời 12 + 12 = 24 / 18 triệu trúng
  nhóm (`reference_group_points: 20`, vượt 6 triệu, `row_points_exclude_group: true`).
  Phiếu rà T07 chứa đủ giao dịch/phân bổ `P1_A_P1_T06`/`P1_A_P1_T07` và khai báo
  `P1_COV_1`..`P1_COV_6`.
- T08: khoản trả 6 triệu theo hóa đơn `P1_I_GAP` 30 triệu nhưng thiếu phạm vi
  lịch sử, giữ `unavailable`, `matched`/`score` null và lý do
  `p1_history_scope_missing`.
- Cả 12 phép tính HE4 đã hoàn tất (`done`, `generation=1`): 6 P1, 1 đồ thị, 5
  thống kê. P1 khả dụng ở 6/8 dòng, thống kê và đồ thị 8/8 dòng, ML 7/8 dòng
  (T01 có ML `input_out_of_domain`), không tự ép miền hoặc dùng điểm rõ thay thế.
- Mở 8 kết quả/8 phiếu, mở căn cứ và tải lại trang giữ cùng run; kiểm ảnh
  `C002-P1-T03.png` và `C002-peer-allocation.png`. Giữ nguyên TTL Portal 20 phút
  (có re-login lần 2 trong quá trình chạy để giải mã/hoàn tất); không xuất mật
  khẩu, không ghi phản hồi nghiệp vụ (`human_review_feedback_written: false`).

## Giới hạn còn mở

- Cả C001 và C002 đều là dữ liệu mô phỏng (`simulated_documents: true`,
  `training_eligible: false`, `original_documents_verified: false`); chưa chứng
  minh chứng từ thật hoặc hiệu quả ML, chưa gộp trọng số bốn nhánh hay tự duyệt
  R0–R6 / D-11 / D-12 / production.
