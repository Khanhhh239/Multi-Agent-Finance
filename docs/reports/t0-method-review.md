# Đánh giá T0 và các chỉnh sửa cần thiết

Đối chiếu ngày **18/10/2026** với [note T0](../../research/notes/t0_data_foundation_reconciliation.md). Đây là đánh giá thiết kế và đề xuất; chưa có benchmark T0 hoặc kiểm định tại doanh nghiệp.

## 1. Kết luận

**Phương pháp phù hợp để tiếp tục phát triển, nhưng chưa có bằng chứng là SOTA hoặc tối ưu.** Giữ Bronze–Silver–Gold, lịch sử phiên bản và đối soát nhiều tầng. Giá trị cần chứng minh là dữ liệu khớp sổ, tái lập đúng thông tin tại ngày dự báo và giảm sai số dự báo phía sau.

## 2. Những điểm cần sửa

| Ưu tiên | Chỉnh sửa | Lý do |
|---|---|---|
| **P0 — Thời gian** | Lưu cả thời gian hiệu lực nghiệp vụ và thời điểm thông tin khả dụng; feature chỉ dùng thông tin đã biết tại cutoff T | SCD2 chỉ theo hiệu lực nghiệp vụ chưa xử lý đủ dữ liệu đến muộn hoặc sửa hồi tố |
| **P0 — Phân bổ tiền** | Tách `payment_allocations` (payment → invoice) và `payment_bank_links` (payment ↔ giao dịch ngân hàng); lưu lịch sử đảo/sửa | Xử lý trả từng phần, thanh toán gộp và tránh đếm tiền nhiều lần |
| **P0 — Đối soát** | Sinh ứng viên trước khi chấm điểm; chọn thuật toán theo trường hợp 1–1, 1–N, N–M; cho phép chưa khớp/chờ duyệt | Khớp đúng tổng tiền chưa chứng minh đúng hóa đơn; ngưỡng tự động phải được đo trên validation |
| **P1 — Nhập dữ liệu** | Giữ raw cùng nguồn, khóa bản ghi, batch, thời điểm nhận và phiên bản; chạy lại không tạo trùng; tách bản lỗi để xử lý | Bảo đảm truy vết và phục hồi khi nguồn hoặc pipeline lỗi |
| **P1 — Lịch sử** | Phân biệt snapshot/SCD2 với event sourcing; ghi event cho các quyết định phân bổ/đảo do hệ thống tạo | Lưu nhiều bản sao ERP không có nghĩa đã thu đủ event nghiệp vụ của ERP |
| **P1 — Gold** | Cho phép tổng hợp và tính feature; quy định rõ đơn vị mỗi dòng, công thức và cutoff | Sửa nhận định “Gold không còn phép tính”; dữ liệu báo cáo hiện tại chưa thay thế được snapshot lịch sử cho ML |

**Ví dụ chống leakage:** giao dịch xảy ra ngày 10/03 nhưng hệ thống chỉ nhận và công bố ngày 12/03 thì backtest ngày 11/03 không được dùng giao dịch đó. Quy tắc này áp dụng cả với quyết định đối soát và allocation. Lịch nghĩa vụ tương lai đã biết tại T vẫn có thể được dùng.

Về tiền, cần phân biệt **ngày thu lần đầu, ngày trả đủ và ngày clear ERP**. Credit note làm giảm công nợ nhưng không tạo cash-in. Với receipt cùng tiền tệ đã chuẩn hóa, kiểm tra:

```text
Tiền nhận = tổng tiền phân bổ + tiền chưa phân bổ
```

Phí/FX và giao dịch đảo phải được xử lý riêng. Dùng `DECIMAL` hoặc đơn vị tiền nhỏ nhất phù hợp; khóa/join phải phân biệt doanh nghiệp (`tenant_id`).

## 3. Pipeline đề xuất

```text
ERP: hóa đơn/công nợ + Ngân hàng: giao dịch/số dư + CSV điều chỉnh
  → Bronze: raw, metadata và lịch sử các lần nhận
  → Silver: chuẩn hóa, phiên bản theo thời gian, kiểm tra chất lượng
  → Đối soát: sinh ứng viên → rule/scorer → giải xung đột → tự động/duyệt/chưa khớp
  → Gold: báo cáo, snapshot công nợ và feature as-of T
  → T1–T8 và đánh giá
```

Khớp **1–1** có thể dùng matching hai phía; **1–N** cần xét nhóm hóa đơn; **N–M có ràng buộc nhóm** có thể cần MILP/CP-SAT. Min-cost flow phù hợp khi chi phí và ràng buộc biểu diễn được theo dòng tiền tuyến tính. Nghiệm tối ưu của mô hình vẫn cần kiểm chứng nghiệp vụ.

## 4. Cách triển khai và kiểm chứng

**MVP offline:** raw file + Parquet + SQL/DuckDB + Python. Khi có nhiều người duyệt và cập nhật đồng thời, cân nhắc PostgreSQL cho trạng thái/phân bổ. Giữ ba lớp dữ liệu dưới dạng logic; chọn thêm hạ tầng sau khi đo nhu cầu. Đây là đề xuất, chưa phải kết quả so sánh hiệu năng.

Bắt đầu bằng rule và scorer đơn giản. Chỉ thử LLM cho phần trích xuất nội dung hoặc gợi ý nhãn khi đo được lợi ích; không để nhãn do hệ thống tự tạo thay thế bộ test được kiểm tra độc lập.

Cần bộ dữ liệu chuẩn liên kết **invoice ↔ allocation ↔ payment ↔ bank transaction**, có cả trường hợp không khớp. Ưu tiên kiểm tra trả từng phần/gộp, giao dịch đảo, credit note, dữ liệu đến muộn/sửa hồi tố và tải lại trùng.

Các chỉ số chính:

- Precision của auto-match, candidate recall và tỷ lệ phải duyệt tay.
- Giá trị tiền gán sai, tiền chưa phân bổ và lỗi bảo toàn tiền.
- Sai lệch ngày thu tiền và lỗi dùng thông tin chưa khả dụng tại cutoff.
- Thời gian chạy và tác động lên sai số dự báo T1/T6.

Các tỷ lệ 80%/15%/5% hoặc ngưỡng 85% trong tài liệu cũ chỉ là giả thuyết cho đến khi được đo. API ERP/ngân hàng cần xác nhận dữ liệu, quyền truy cập và chi phí cụ thể trước khi chốt connector.

## 5. Paper nên đọc trước

| Paper | Dùng cho phần nào? |
|---|---|
| [Temporal Features in SQL:2011 — R3](../../research/references/papers/t0/2012_temporal_features_sql2011.pdf) | Phân biệt thời gian nghiệp vụ và thời gian hệ thống biết thông tin |
| [The Subset Sum Matching Problem — R7](../../research/references/papers/t0/2025_subset_sum_matching_problem.pdf) | Khớp nhóm bản ghi tài chính; tham khảo greedy, DP và MILP |
| [Automating Large-Scale Data Quality Verification — R4](../../research/references/papers/t0/2018_automating_data_quality_verification.pdf) | Thiết kế kiểm tra chất lượng bằng các ràng buộc dữ liệu |

Xem [danh mục đầy đủ 8 paper](../../research/references/bibliography/t0_reading_list.md) để đọc thêm về lakehouse, Delta Lake và entity matching; có [BibTeX](../../research/references/bibliography/t0_references.bib) kèm theo.
