# Mã nguồn Agent 1

## T0, T5 và T9 đang nằm ở đâu?

| Phạm vi | File/thư mục | Vai trò và nơi sử dụng |
| --- | --- | --- |
| T0 | `data/schema.py` | Cổng chất lượng hóa đơn; được `agent1_service/ingest/invoices.py` gọi lại. |
| T0 | `agent1_service/ingest/` ở thư mục dự án | Đọc XML/ERP/sao kê, chuẩn hóa ngày và tiền, kiểm tra phiên bản và vòng đời hóa đơn. `erp_ledger.py` vẫn được API dùng. |
| T5 | `rules/obligations.py` | Sinh lịch nghĩa vụ từ hồ sơ/hợp đồng, ngày biết và quy ước ngày làm việc. |
| T5 | `adaptive/obligations.py`, `adaptive/obligation_imports.py` | Phân bổ thanh toán, tính phần còn phải trả và chống nạp trùng theo định danh nghiệp vụ. Hai lớp này dùng lại lịch trong `rules/`, không phải hai bản sao. |
| T9 dịch vụ | `reconciliation/`, `agent1_service/workspace/reconciliation.py` | Đề xuất/duyệt phân bổ, sổ quyết định, đảo quyết định và snapshot theo ngày biết. |
| T9 nghiên cứu | `models/t9_recon.py`, `models/reconciliation_pipeline.py` | Bộ đối chiếu ML/quy tắc và tạo nhãn ngân hàng cho các script benchmark cũ. Vẫn có caller và test. |
| T9 nghiên cứu nhanh | `models/t9_fast.py`, `models/t9_source_policy.py` | Tính ứng viên bằng mảng và các chính sách phân bổ; vẫn dùng trong script hard-case/sprint. |
| T9 nghiên cứu nhãn | `models/t9_research.py` | Hàng chờ tiền chưa phân bổ, mô phỏng người duyệt hoàn hảo và nhãn mềm FIFO. Mô phỏng dùng nhãn thật để chấm cận trên, không phải thao tác duyệt của dịch vụ. |
| Đánh giá | `eval/` | Metric/gate cho dịch vụ và nghiên cứu. Các file nhỏ vẫn có script hoặc test sử dụng. |
| Huấn luyện | `jobs/retrain.py` | Chuẩn bị dữ liệu/huấn luyện T1 từ nguồn đã đối soát; giữ nguyên trong lượt dọn này. |

## Phần đã gộp ngày 13/11/2026

- `models/t9_soft_labels.py` và `models/t9_review_queue.py` chuyển vào
  `models/t9_research.py`. Script và test trong repo đã đổi import; caller bên
  ngoài repo cần đổi sang đường dẫn mới.
- Nhãn mềm và mô phỏng duyệt dùng chung `queued_transactions`: chỉ nhận tiền
  vào dương, trừ số đã phân bổ và bỏ phần dư không vượt dung sai T9.
- Dung sai lấy từ `t9_recon.TOL` thay cho hai hằng số chép lại.
- Bỏ override DataFrame `_amount_feats` trong `FastAmountReconciler`: luồng
  `candidates` đã dùng `_array_amount_features`. Lời gọi DataFrame vẫn được
  hỗ trợ qua phương thức kế thừa từ `Reconciler`; test đối chiếu kiểm trực tiếp
  hàm mảng thực sự đang chạy.
- Bỏ import `memo_numbers` lặp bên trong `reconcile_arrays`.

## Phần giữ lại sau rà soát

Không thấy mô-đun Python nào trong `models/`, `eval/`, `jobs/`, T0 ingest và
T5 đủ bằng chứng là không còn sử dụng. File chỉ được gọi bởi script nghiên
cứu vẫn cần cho script đó; tên phiên bản cũ chưa đủ để kết luận là rác.

`reconciliation/_thang/` là mã nguồn có provenance/hash upstream và có các
phụ thuộc gián tiếp giữa allocation, ledger, matching, data, balances và fx.
Giữ nguyên cả bộ để kiểm chứng nguồn và hành vi dịch vụ.

Không chỉnh mã, tài liệu, dữ liệu, kết quả hoặc snapshot nghiên cứu T1/T6
ngày 12–13/11. Các output và báo cáo lịch sử giữ nguyên; tên file cũ trong
prereg/nhật ký vẫn mô tả cấu trúc tại thời điểm đo, với ghi chú nơi mã đã chuyển.

Các lần chạy T9 mới ghi hash mã hiện tại theo cơ chế sẵn có. Không sửa hash
hoặc output frozen để coi kết quả cũ là kết quả đã chạy lại sau khi gộp.

## Kiểm tra sau khi gộp

Ngày 13/11/2026: 171 test T0/T5/T9 và đối soát đạt; lượt kiểm tra cuối nhóm
T9 đạt 14 test, gồm 3 ca biên tiền dư mới (174 ca khác nhau qua hai lượt).
40 bộ dữ liệu ngẫu nhiên cho hàng chờ, nhãn mềm và hai chính sách duyệt cho
kết quả giống mã trước khi gộp. Ba script đã đổi import nạp thành công;
466 file Python qua kiểm tra cú pháp và không còn import sống tới hai mô-đun
đã bỏ. Hai cache `.pyc` của mô-đun đã bỏ cũng đã xóa.

Hash mã nguồn, experiment và tài liệu T1/T6 được bảo toàn. Trong 4.642 file
được theo dõi để bảo vệ, 4.637 file giữ nguyên; 5 file trong output
`neural_data_ablation_20261113` thay đổi trong lúc rà soát, ngoài danh sách
file của lượt dọn này. Không khôi phục hoặc ghi đè các thay đổi đang diễn ra đó.
