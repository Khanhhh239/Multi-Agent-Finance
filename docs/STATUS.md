# Trạng thái dự án

Cập nhật **07/11/2026 — một phiên local 8765**: hợp nhất nhập CSV/Excel, chọn ML và phiếu rà vào phiên hồ sơ hiện có. Giữ nguyên 1.146 hồ sơ, 5 doanh nghiệp, toàn bộ snapshot/model/nhãn/lịch sử ML đang dùng và 12 phiếu rà từ 8853; các database QA giữ riêng trên đĩa. Đã dừng các cổng demo phụ, lưu cấu hình để `python -B start_review.py` mở đúng phiên. **211 test Python, 146 kiểm tra JavaScript, 30/30 kiểm tra Playwright đạt**; đối chiếu 27 bảng hồ sơ cũ, 11 bảng ML và 16 tệp nguồn/báo cáo không đổi. Danh tính quản lý cố định chỉ dùng trong QA local. [Đường dẫn, bằng chứng và khôi phục](reports/app/unified_local_20261107.md).

Cập nhật **06/11/2026 — khóa tập bằng chứng phiếu rà**: CLI và web chỉ nhận chính xác JSON trong manifest, đối chiếu tập phiếu/model/dòng chọn/ngân sách; chặn cả tệp thừa trong thư mục con, trùng giao dịch và thay đổi trong lúc đọc. **201 test Python đạt**, gồm 19 test gói mới. Thử thêm tệp thứ 13 trên bản sao `run_02` bị từ chối ở cả CLI/web; giữ 12 phiếu hiện có, không tạo kết quả dở dang và không sửa gói nguồn. [Chi tiết và bằng chứng](reports/ml/ml_review_packet_lock_20261106.md).

Cập nhật **06/11/2026 — sửa mất nhãn khi bổ sung CSV**: giữ nhãn không liên quan, tải lại giống hệt không đổi revision; có xem trước và chọn giữ/sửa xung đột, sửa cần lý do/xác nhận, lưu lịch sử trước/sau có checksum. Giữ giao dịch/feature/model; chặn tệp lỗi và phiên cũ. **182 test Python, 137 kiểm tra JavaScript, 36/36 kiểm tra Playwright đạt** trên database mô phỏng riêng. [Quy tắc, kiểm thử và giới hạn khôi phục](reports/ml/company_ml_labels_20261106.md).

Cập nhật **05/11/2026 — phiếu rà ML trên web**: thêm `/ml-reviews`, dữ kiện/căn cứ/hành động hữu ích, đồng hồ có tạm dừng và xác nhận thời gian ở máy chủ, lưu nháp/kết quả theo người rà, phân quyền công ty và CSV/tổng hợp sau khi hoàn tất. Demo 8853 có 12 phiếu ban đầu chưa điền; dữ liệu/model giữ nguyên. **165 test Python, 131 kiểm tra JavaScript, 27/27 kiểm tra Playwright đạt**; test ghi kết quả mô phỏng dùng DB riêng. Sửa kèm kiểm tra bằng chứng ngoài manifest trong luồng nhập/CLI. [Hướng dẫn và giới hạn](reports/ml/ml_review_web_20261105.md).

Cập nhật **05/11/2026 — đồng bộ điều kiện ML trên web**: CatBoost dùng kiểm tra nhãn đúng kỳ train từ backend, đủ hai lớp và biết trước ranh giới; khóa chấm/giữ khi artifact không tương thích. Có thống kê nhãn/lý do khóa, kiểm tra lại khi đổi kỳ/công ty/dữ liệu, bỏ phản hồi trễ và khóa khi lỗi mạng. **150 test Python, 127 kiểm tra JavaScript và 29/29 kiểm tra Playwright đạt**. Demo 8853 đã có API mới, revision và model C001/C002 giữ nguyên. [Chi tiết và demo kiểm thử riêng 8855/8856](reports/ml/company_ml_readiness_20261105.md).

Cập nhật **05/11/2026 — chốt phạm vi thử model**: người dùng chọn demo C001/C002, tối đa **5 giao dịch/model/doanh nghiệp**. Đã xác nhận gói so sánh `run_02` khớp lựa chọn: 24/24 tệp nguyên vẹn, 8 cặp doanh nghiệp/model có 40 vị trí rà, gộp thành 12 giao dịch duy nhất. Dữ liệu/model nguồn không đổi nên dùng lại kết quả đã khóa; chưa có phiếu hữu ích/phút kiểm tra thực tế. CatBoost tiếp tục bị loại vì thiếu nhãn train phù hợp. [Kết quả và phiếu rà](reports/ml/company_ml_comparison_20261104.md).

Cập nhật **04/11/2026 — so sánh model từng doanh nghiệp**: đã chạy Isolation Forest/Autoencoder/ECOD/LOF cho demo C001/C002, cùng kỳ 18 train/6 calibration/6 evaluation và ngân sách thử 5 giao dịch/model/công ty. CatBoost bị loại vì chỉ 0/18 và 1/18 train có nhãn phù hợp. Có runner chỉ đọc SQLite, artifact/điểm/tập chọn đã khóa và phiếu hữu ích/phút kiểm tra cho 12 giao dịch duy nhất; **0 phiếu thực tế**, chưa kết luận model tốt nhất hoặc đổi model đang dùng. **136 test Python liên quan đạt**, gồm 11 test so sánh mới. [Kết quả, giới hạn và cách điền phiếu](reports/ml/company_ml_comparison_20261104.md).

Cập nhật **04/11/2026 — nhập CSV/Excel**: thêm `/data-import`, kiểm tra lỗi theo dòng/cột/cách sửa, chuẩn hóa và tạo 194 feature trước khi xác nhận lưu. Lưu riêng doanh nghiệp, giữ model và chuyển đúng công ty sang chọn ML. Có kiểm tra xung đột, phân quyền và cập nhật nhãn riêng cho dữ liệu nhập; **125 test Python, 118 kiểm tra JavaScript và 39/39 kiểm tra Playwright đạt**. Bản đầu hỗ trợ thay thế toàn bộ tập giao dịch ML, dùng danh mục kết nối; chưa nối thêm từng lô hoặc tự ánh xạ ERP. [Chi tiết và demo 8853/8854](reports/ml/data_import_20261104.md).

Cập nhật **04/11/2026 — cấu hình ML theo doanh nghiệp**: thêm web `/company-ml`, đọc/kiểm tra nguồn đã kết nối, đánh giá ứng viên, xác nhận/giữ/quay lại phiên bản và chấm bằng model cố định riêng cho từng công ty. Có adapter Isolation Forest, Autoencoder, ECOD tham chiếu cố định, LOF novelty và CatBoost tùy chọn với nhãn đã xác minh. **88 test Python liên quan và 116 kiểm tra JavaScript đạt**, gồm thực thi cả năm thuật toán, phân quyền/công ty, lịch sử, xung đột hai phiên và backup/restore artifact. Đã chạy thêm **50 kiểm tra trên Chrome headless bằng Playwright**: C001 dùng IF v3, C002 dùng ECOD v1; thêm một dòng nguồn mô phỏng mỗi công ty rồi cập nhật/chấm/reload, artifact/ngưỡng/model và điểm cũ giữ nguyên. [Biên bản demo và giới hạn](reports/ml/company_ml_demo_20261104.md), [hướng dẫn chạy](../examples/company_ml/README.md). Chức năng mới vẫn ở shadow; đăng nhập thật và ánh xạ ERP vẫn chưa triển khai. Nhập CSV/Excel theo mẫu đã được bổ sung ở cập nhật phía trên.

Cập nhật **29/10/2026**: [nghiệm thu app tích hợp](reports/app/release_acceptance_20261029.md) đạt **39 mẫu / 73 giao dịch P2 / 17 luồng lịch sử**, Chrome desktop/360×800/390×844, mất kết nối và restart. Sửa ba lỗi mạng/phiên/hộp thông báo; **81 kiểm tra browser, 173 test Python, 104 kiểm tra JavaScript, 68 kiểm tra API/dữ liệu/bằng chứng** đạt. Workspace ghi thử riêng; mọi danh tính, kết luận và phút nhập đều mô phỏng, không gửi thật.

Bản tích hợp **28/10/2026** đã chạy trên **41.082 giao dịch**, nạp và đọc đủ **1.211 hồ sơ**, đạt **42 kiểm tra HTTP**, **208 test Python** và **92 kiểm tra JavaScript** ở lượt đó. Chấm luật/queue mới; IF chỉ chấm 11.811 dòng evaluation bằng model/ngưỡng v4 ngày 24/10, không huấn luyện lại. Hai mươi cấu hình discovery có guard đều giữ baseline và ngân sách. Lượt 29/10 đã bổ sung nghiệm thu browser trên nguồn tích hợp này; điểm chậm ở nguồn hỗ trợ hồ sơ vẫn là việc tối ưu riêng.

Đã bổ sung **audit tồn đọng/SLA**: tái hiện đúng bốn baseline, chạy **22 cấu hình offline và 63 test đạt**. Đồng hồ tái rà cũ gộp thời gian trước khi đủ điều kiện; đuôi chờ đủ điều kiện là 20/26 ngày ở mức thấp. Giả định tồn đầu kỳ và trần phút là các yếu tố chính trong mô phỏng; chưa đổi chính sách.

## Đã có

| Phần | Trạng thái |
| --- | --- |
| Nghiệm thu app 29/10 | Đủ 39 mẫu/17 luồng; thông báo lỗi tiếng Việt, giữ bản nháp khi lỗi mạng, nạp lại phiên sau restart mà không tự lặp POST; lỗi thông báo hiện trong hộp thoại và nút thử lại không bị khóa. 174 job giả lập, 522 mốc lịch sử, không trùng và giữ ngân sách; 32 tệp detector copy vào QA giữ hash. |
| Bản tích hợp 28/10 | Workspace mới `reports/integrated_rehearsal_20261028_v2/`: luật → graph/A5 → queue → IF shadow có guard → app hai cấp → thông báo giả lập. Kiểm tra đủ 1.211 detail bằng bốn tiến trình SQLite chỉ đọc, có hash từng phản hồi; luồng nghiệp vụ chạy HTTP trên cùng database test mới. Snapshot cũ giữ nguyên. |
| Phân tích tồn/SLA 28/10 | Workspace `reports/baseline_sla_20261028/`: tách tồn tại cutoff đầu kỳ, ngày đủ điều kiện từng lượt, giới hạn suất/phút, nợ SLA cũ và việc chờ chứng từ. FIFO/EDF có giữ suất bắt buộc chưa giảm đuôi chờ; không đề xuất đổi mặc định từ kết quả này. |
| Luật và hàng đợi | Có rules + graph + A5, kiểm soát ngân sách và SLA. RR09 đã phân tầng ưu tiên theo mức vượt; giữ riêng điểm phát hiện và mức ưu tiên xử lý. |
| Ma trận kiểm thử luật | Đã đối chiếu 35 mã theo bảy nhóm tình huống: 228 ô có test đạt, 17 ô không áp dụng có lý do; kiểm tra cả ưu tiên, hàng đợi và SLA. Thêm 169 test mới, bộ hồi quy tổng 607 test đạt. |
| Đối chứng C4/E2/F2/F3/F4 | Năm luật đã có đủ bảy nhóm trước đó. Nay có 98 biến thể/2 seed, 196 ca khớp gồm 10 nguồn sai bị từ chối đúng; xuất CSV/cache riêng, kiểm tra điểm/hard trigger/queue/SLA và nạp app. Hồi quy mới 708 test đạt, gồm 101 test bổ sung. |
| Các lỗi gần nhất | Đã sửa B4 dùng bằng chứng tương lai để giảm cảnh báo, B2 giữ nhân viên ở công ty cũ, feature đọc dữ kiện sau cutoff, định danh rỗng và quan hệ master cũ. |
| Bản sửa ngày 27/10 | A6 loại hoá đơn có ngày phát hành/quan sát rõ ràng sau cutoff. T1/T2 chỉ dùng hồ sơ xoá nợ có căn cứ thời gian/phạm vi để miễn cảnh báo; header không có mốc thời gian cần bản writeoff nguồn đúng phạm vi đã biết. |
| ML | Feature contract v4, 194 feature; model mới tương thích và đã replay shadow. Train 2024, calibration nửa đầu 2025, evaluation nửa cuối 2025. |
| Giới hạn trì hoãn IF | Đã replay 20 cấu hình, giữ 0 ngày trễ thêm so với lịch baseline. Cấu hình chính giữ 2.425 lượt baseline và 40 chứng từ IF, 0 vượt ngân sách/mất suất bắt buộc. Quota IF giảm khi cần; thời gian chờ IF có thể tăng. |
| Rà hai cấp | Kế toán viên gửi kết quả; kế toán trưởng hoặc giám đốc khác người chốt/trả lại. Có kiểm soát công ty, phiên bản hồ sơ và nhật ký. |
| Giao diện nghiệp vụ | Đã kiểm tra bằng chứng → gửi → chốt/trả → bổ sung/gửi lại trên Chrome desktop, 360×800 và 390×844. Hiện lý do trả lại, căn cứ chốt, lịch sử và lỗi ngay tại biểu mẫu; nhánh thiếu bằng chứng vẫn cho rà bổ sung. |
| Thông báo theo vai trò | Đã hoàn thiện 10 loại sự kiện, người nhận theo công ty/vai trò, chống trùng, nhắc quá hạn và lịch sử gửi. 140 test Python, 92 kiểm tra JavaScript và 11 kiểm tra Chrome đạt; toàn bộ gửi thử là mô phỏng/mock. |
| Vận hành | Có backup/restore, quy trình phát hành, outbox và adapter thông báo. Gửi thông báo vẫn giả lập. |

Biên bản chính: [tồn đọng/SLA](reports/operations/baseline_sla_20261028.md), [tích hợp 28/10](reports/app/integrated_rehearsal_20261028.md), [đối chứng năm luật](reports/rules/rule_branch_controls_20261027.md), [thông báo](reports/app/notification_roles_20261027.md), [giao diện hai cấp](reports/app/browser_workflow_20261027.md), [guard IF](reports/ml/if_delay_guard_20261027.md), [ma trận luật](reports/rules/rule_test_matrix_20261027.md), [RR09 và ML v4](../reports/rr09_ml_completion_20261024.md), [phân quyền](../reports/review_roles_20261024.md). Thí nghiệm guard 27/10 dùng baseline 24/10; bản tích hợp 28/10 đã chấm lại luật và queue, giữ riêng cả hai đợt.

## Còn mở

| Việc | Giới hạn hiện tại |
| --- | --- |
| Nguồn doanh nghiệp thật | F1/C4/E2/F2/F3/F4 đã có đối chứng mô phỏng; chưa được nghiệm thu trên nguồn SME thật. |
| Thời điểm biết chứng từ | Bốn cờ khả dụng bằng chứng vẫn chưa đủ căn cứ trên 41.082 dòng nguồn; feature tương ứng được che, không suy là không có chứng từ. |
| Năng lực và thời gian chờ | 21/27 ngày là đồng hồ tái rà cũ; audit đo max chờ đủ điều kiện 20/26 ngày, thuộc mức thấp. 32 lượt cao nhất được chọn ngay ngày đủ điều kiện. Trong 995 lượt chọn vào ngày sau SLA, 969 đã mang nợ trước đầu ngày đủ điều kiện; đây chưa phải SLA hoàn thành thật. Tồn đầu kỳ/lịch/phút xử lý thực tế cần được xác nhận trước khi chốt công suất. |
| Lợi ích ML | Chưa có phút thực tế hoặc kết luận độc lập. Gói 74 phiếu v4 có **0 lượt rà**, thuộc nhánh trước guard; không tự chuyển kết luận sang nghiên cứu mới. Gói 128 phiếu thuộc đợt cũ hơn. |
| Hiệu năng nguồn hỗ trợ | Probe detail chỉ đọc có profiler mất 3,441 giây, chủ yếu ở `review_support.case_support` quét/giải mã lặp nguồn. Chưa phải P95 hoặc SLA; cần tối ưu có đối chiếu đầy đủ phản hồi và công ty/cutoff. |
| Phạm vi browser mở rộng | Lượt 29/10 đã đạt 39 mẫu/17 luồng trên Chrome desktop và viewport 360/390. Chưa nghiệm thu trình duyệt khác hoặc điện thoại vật lý. |
| Email/Zalo | Chưa xác nhận gửi–nhận thật. |
| Tài khoản | Chưa tạo tài khoản/đăng nhập theo yêu cầu người dùng; quyền và điểm tích hợp đã chuẩn bị. |

Phân quyền không tự tạo kết quả rà độc lập. IF vẫn ở **shadow**, lợi ích vận hành chưa được chứng minh. Xem [readiness sau guard](../reports/if_delay_guard_20261027/readiness.json), [trạng thái gói rà cũ](../reports/review_roles_20261024/ml_role_validation/review_status.json) và [nghiệm thu nguồn thật](../reports/rule_source_acceptance.md).

## Ưu tiên tiếp theo

Bản tích hợp, nghiệm thu Chrome và audit tồn/SLA đã đạt phạm vi mô phỏng. Trước khi đổi ngân sách cần version hóa metric chờ và nhập đúng trạng thái đầu kỳ; chưa có bằng chứng nên đổi bộ chọn mặc định. Tiếp tục tối ưu nguồn hỗ trợ hồ sơ và hoàn thiện bằng chứng theo thời gian. Gửi–nhận thật chờ tài khoản/kênh; đăng nhập/tài khoản vẫn để sau theo lựa chọn của người dùng. Chi tiết trong [backlog](BACKLOG.md).
