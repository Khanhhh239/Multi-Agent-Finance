# Diễn tập pipeline mới trên 001/003 — 18/10/2026

**Kết quả: đạt các tiêu chí kỹ thuật đã khóa cho lượt mô phỏng.** Đã chạy từ nguồn hiện có qua rules, NetworkX, ngưỡng động, hàng đợi, API kết luận, restart và thông báo giả lập. Cấu hình hiện tại được khóa trước dự đoán; source oracle của 001/003 chỉ được nối sau khi khóa hash kết quả.

[Tổng hợp máy đọc](pipeline_rehearsal_20261018_v2/summary.json), [kế hoạch/cấu hình/hash đầu vào](pipeline_rehearsal_20261018_v2/evaluation_plan.json), [đối chiếu artifact độc lập](pipeline_rehearsal_20261018_v2/artifact_validation.json).

## Kết quả theo bộ

| Hạng mục | 001 | 003 |
| --- | ---: | ---: |
| Giao dịch | 20.559 | 20.523 |
| Chứng từ cân đối Nợ/Có | 29.737 | 29.572 |
| Dòng sổ cái | 66.749 | 65.750 |
| Đặc trưng/giao dịch khớp cache đã khóa | 190 | 190 |
| Hit quy tắc, gồm ngữ cảnh/ngoại lệ | 10.949 | 11.778 |
| Hồ sơ trong queue mới | 556 | 594 |
| Hồ sơ nguồn | 144 | 144 |
| Nút NetworkX | 4.290 | 4.143 |
| Cạnh NetworkX | 3.359 | 3.242 |
| Nhóm quan hệ cần đối chiếu | 24 | 24 |
| Dòng tham số 30/60/90 ngày | 9.135 | 9.135 |
| Dòng ngưỡng đủ điều kiện | 750 | 708 |
| Bằng chứng A5 phát lại theo lịch sử | 20 | 20 |
| Đơn vị kiểm soát nguồn | 608 | 608 |
| Không khớp kỳ vọng nguồn | 0 | 0 |

Tổng 41.082 giao dịch, 8 công ty trong mỗi bộ. 1.216/1.216 điều kiện nguồn của F1/C4/E2/F2/F3/F4 khớp kỳ vọng, gồm unknown/thiếu dữ kiện. Đây là oracle mô phỏng đã khai báo trước; không diễn giải thành precision gian lận hoặc đánh giá kế toán độc lập.

Trong 18.270 dòng tham số ngưỡng (gồm các cửa sổ và ngữ cảnh chu kỳ), 1.458 dòng đủ mẫu; 16.718 dòng thiếu lịch sử và 94 dòng thiếu lịch sử chu kỳ. Các dòng chưa đủ điều kiện giữ ngưỡng null; không xem bảng đã được hiệu chỉnh đầy đủ cho mọi tài khoản. Đã phát lại 40 bằng chứng A5 để kiểm tra lựa chọn ngưỡng từ lịch sử trước thời điểm phát hiện.

## Kiểm chứng xuyên suốt

1. **Nguồn:** kiểm mọi SHA256 trong manifest, schema/feature contract hiện tại, liên kết và cân đối chứng từ; dựng lại 190 đặc trưng từ dữ liệu nguồn và so chính xác ma trận float32 với cache. Không fit/chấm model IF hoặc AE.
2. **Rules và hàng đợi:** chạy nguyên DEFAULT_CONFIG mới, giữ ngưỡng pháp lý/thẩm quyền của engine; tập thành viên queue phải khớp các sự kiện vận hành. Xuất cả score, hit, bằng chứng, sự kiện và config vào output mới.
3. **NetworkX:** snapshot đầy đủ theo công ty tại 31/12/2025; kiểm namespace ID, biên thời gian, FK cạnh, partition thành phần liên thông và đường đi. Lặp sync cùng đầu vào trả changed=false.
4. **Ngưỡng động:** xuất đủ 30/60/90 ngày theo tài khoản chi tiết; bảng batch khớp một instance độc lập. Phát lại 20 hit A5/bộ bằng lịch sử trước thời điểm phát hiện. Dòng thiếu mẫu/chu kỳ giữ ngưỡng null hoặc fallback đúng phạm vi.
5. **HTTP thật:** kiểm tài nguyên UI/API, hàng đợi ưu tiên, chi tiết 16 hồ sơ từ các công ty, JSON đồ thị và 32 chứng từ cân đối trong API. Route nguồn/nhãn không được công khai.
6. **Kết luận:** 6 sự kiện SIM_PIPELINE_BOT, gồm hợp lệ/nghi vấn/thiếu dữ kiện, được lưu qua API. Thiếu lý do trả 400, lưu trên hash cũ trả 409. Tạo lại cả ReviewStore và HTTP server xác nhận kết luận, admission và hash audit còn nguyên.
7. **Thông báo:** outbox tồn tại trước kết luận để kiểm hủy cảnh báo đã đóng; tóm tắt tuần được làm mới. Khởi động lại không sinh trùng job. Diễn tập 18/10, 19/10 và 20/10 bằng đồng hồ giả lập, ngân sách lần lượt 5/5/10, kiểm theo công ty–snapshot–ngày. Không có lịch gửi thật được đặt cho các ngày này.

Đối chiếu sau chạy kiểm 522 phân phối all_days bằng công thức nội suy phân vị/trung bình/độ lệch chuẩn mẫu, 8.433 ID nút và 35 nhóm phân bổ ngày. 229 file đầu vào được đối chiếu hash giữ nguyên; các file WAL/SHM/lock đang sống không nằm trong fingerprint này.

## Thay đổi so với báo cáo cũ

| Bộ | Hồ sơ cũ → mới | Hit A5 cũ → mới | Hit P2 cũ → mới |
| --- | ---: | ---: | ---: |
| 001 | 256 → 556 | 20 → 219 | 0 → 1217 |
| 003 | 307 → 594 | 21 → 265 | 0 → 1192 |

Cấu hình cũ dùng log/MAD và chưa bật P2; lượt mới dùng rolling-account P99/90 ngày và chính sách chi tiền mặt hiện có. Đếm hit gồm ngữ cảnh hoặc trường hợp bị suppress; không đồng nhất với số hồ sơ. ID hồ sơ có thể đổi khi phạm vi thành viên đổi. Chi tiết before/after và danh sách ID thêm/bớt nằm trong `comparison_previous.json` của từng bộ.

Hàng đợi tăng đáng kể cần được rà nghiệp vụ, đặc biệt P2 và A5, trước khi chốt cấu hình cho đợt đánh giá tiếp theo. Nghiệp vụ nền chưa có kết luận độc lập nên chưa biết phần tăng là cảnh báo sai hay dấu hiệu cần đối chiếu. Giữ cấu hình đã khóa của lượt này để kết quả có thể tái lập.

## Thông báo và phản hồi giả lập

Tạo 284 job: 276 simulated, 8 cancelled. **0 lần gọi transport ngoài, 0 tin gửi ra ngoài.** Số job gồm nhiều kênh/người nhận và tóm tắt tuần; giới hạn ngân sách đếm hồ sơ duy nhất, không đếm job.

[Outbox giả lập](pipeline_rehearsal_20261018_v2/notification_outbox.mock.json), [phân bổ ngày](pipeline_rehearsal_20261018_v2/notification_allocations.mock.csv), [sự kiện kết luận bot](pipeline_rehearsal_20261018_v2/feedback_events.mock.json), [kiểm tra restart/API](pipeline_rehearsal_20261018_v2/review_notification_checks.json).

Các kết luận bot chỉ là thao tác thử luồng, không được tính là reviewer độc lập, nhãn gian lận hoặc kết quả pilot. SQLite và audit nằm riêng trong output mới. Không ghi kết luận vào báo cáo hoặc database vận hành cũ.

## Chạy lại và mở kết quả

```powershell
python -B -m sme_fraud.run_pipeline_rehearsal --output reports/pipeline_rehearsal_repeat --review-at 2026-10-18T09:00:00+07:00
```

Runner từ chối output đã có nội dung và không có tùy chọn chấm 005. Chọn tên mới khi chạy lại. Mã tại [run_pipeline_rehearsal.py](../sme_fraud/run_pipeline_rehearsal.py).

Đọc nhanh từng bộ: [summary 001](pipeline_rehearsal_20261018_v2/sme_fraud_001/scoring_summary.json), [summary 003](pipeline_rehearsal_20261018_v2/sme_fraud_003/scoring_summary.json); file queue/hit/config/graph/threshold đi cùng trong thư mục đó. Có thể mở UI cục bộ với nguồn cũ và report/database mới:

```powershell
python -B -m sme_fraud.review_server --data-root data/synthetic_sources_20261017_v2 --reports-root reports/pipeline_rehearsal_20261018_v2 --database reports/pipeline_rehearsal_20261018_v2/review.sqlite3 --port 8765 --qa
```

Database này chứa kết luận bot và lịch phân bổ của các ngày giả lập. Mặc định thông báo vẫn dry-run. Dừng server cũ trước khi dùng cùng cổng; nếu đổi cổng, cập nhật `case_url` khi cấu hình thông báo mới.

## Phạm vi nghiệm thu

Bộ hồi quy chạy song song đạt 544/544; 5/5 đối chứng chốt runner đạt, gồm bảo vệ holdout và hợp đồng JSON đồ thị. [Kết quả hồi quy](../.runtime/pipeline_rehearsal_20261018/current.json), [chốt runner](../.runtime/pipeline_rehearsal_20261018/focused.json). Các nhóm kiểm thử có phần giao nhau; không cộng hai số thành tổng mới.

**Holdout 005 chưa chấm, chưa nạp UI/model, chưa giải mã JSON oracle.** Chỉ hash opaque các file để kiểm giữ nguyên. Gate nguồn thật vẫn `awaiting_real_data`, reviewer độc lập = 0. Không có tuyên bố đạt Gate 1 thực địa, calibration cho SME thật hoặc precision gian lận.

Luồng Web được kiểm qua HTTP và SQLite thật; lượt này không có nghiệm thu trực quan browser, không gửi SMTP/OA thật. Các module giữ nguyên phạm vi đã công bố trong Sprint 1.2–1.4.

Lượt đầu dừng ở phép kiểm runner đọc sai field JSON đồ thị; đã sửa verifier và giữ [bản lỗi](pipeline_rehearsal_20261018/SUPERSEDED.md) để truy vết. Kết quả đầy đủ chính thức của lượt này là thư mục `_v2`.
