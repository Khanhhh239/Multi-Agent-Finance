# Pha D. Dữ liệu mở rộng và độc lập

Mục tiêu: dữ liệu đủ lớn và đủ đa dạng; một tập niêm phong **mà kịch bản do người khác viết**; nối với dữ liệu thật không nhãn để chẩn đoán khoảng cách.

| # | Việc | Công | Ghi chú |
|---|---|---:|---|
| D1 | Mở rộng bộ sinh: dòng hàng hóa đơn, sao kê ngân hàng, tồn kho | 5 ngày | Không đổi dãy số ngẫu nhiên của thế giới cũ |
| D2 | Sinh 17 đến 20 thế giới phát triển và lưới độ nhạy | 2 ngày công, 1 đến 2 ngày chạy | |
| D3 | Sinh quy mô lớn song song | 3 ngày | |
| D4 | Tập niêm phong v5 với kịch bản độc lập | 5 ngày | Cần người khác |
| D5 | Nền thật không nhãn: BPI, chi trả thành phố, khoảng cách miền | 3 ngày | Hỏi chủ dự án trước khi tải |

---

## D1. Mở rộng bộ sinh

**Mục đích:** giải hạn chế L4, L5, L6 (dữ liệu tệp 12): giá theo mặt hàng, đối chiếu tiền, tồn kho.
**Nguyên tắc quan trọng:** các bảng mới phải dùng **một dòng số ngẫu nhiên riêng** (`random.Random(seed + hằng số)`) để không làm thay đổi bất kỳ giá trị nào của các bảng cũ khi cùng seed. Kiểm tra: băm các tệp CSV cũ (`transactions.csv`, `labels.csv`, ...) của seed 411 trước và sau khi thêm mã; phải giống hệt.
**Các bước:**
1. `invoice_lines.csv`: mỗi hóa đơn mua và bán có 1 đến 8 dòng hàng (`item_id`, `description`, `quantity`, `unit_price_vnd`, `vat_rate`); tổng khớp `invoice_net_vnd`. Giá theo mặt hàng của từng nhà cung cấp có phân phối riêng (nay chỉ có một đơn giá).
2. `bank_statement.csv`: mỗi giao dịch `bank` sinh một dòng sao kê (`value_date`, `amount`, `counterparty_account`, `memo`) với độ trễ và vài khoản nhiễu (phí, lãi); tạo khả năng đối chiếu độc lập và thật hơn cho `receivable_lapping`, `altered_payee`, `fake_tax_payment`.
3. `inventory_ledger.csv`: nhập, xuất, tồn theo mã hàng cho ngành thương mại và sản xuất; hủy hàng và hao hụt chuẩn.
4. Cập nhật 5 kịch bản dùng được thông tin mới (`inventory_theft`, `unrecorded_sales_skimming`, `kickback_overpricing` theo mặt hàng, `fake_lease_vendor`...), **thêm** biến thể kịch bản mới, không sửa kịch bản cũ.
5. Cập nhật `validate_v4.py` (bảng mới có khóa, tổng khớp, tồn không âm), `10_tu_dien_du_lieu.md`, các kiểm thử.
**Xong khi:** thế giới sinh lại bằng seed 411 có các bảng cũ đồng nhất băm; bảng mới qua kiểm định.

## D2. Thế giới phát triển mới và lưới độ nhạy

1. `scripts/gen_dev_library.py`: sinh seed 1001 đến 1020 (n = 200.000, 48 công ty) → `work/data/lib_s1001..`.
2. Lưới độ nhạy (tệp dữ liệu 07 mục 4): với 4 thế giới cơ sở sinh các biến thể: `rate` ∈ {0,0005; 0,001; 0,004; 0,01}; `difficulty_weights` ∈ {(.05,.35,.60), (.30,.50,.20)}; `fraud_company_share` ∈ {.25, .85}; `scale_mult` ∈ {×10, ×50} (D1 hoặc B1). Cần thêm tham số tương ứng vào `WorldV4` hoặc dùng các tham số đã có.
3. Chạy E1 trên lưới; vẽ thay đổi thứ hạng phương pháp. Mục tiêu: biết kết luận bền với giả định nào.
**Xong khi:** bảng độ nhạy trong `results/v4/sensitivity.json` và nhận xét.

## D3. Sinh quy mô lớn

**Hiện trạng:** một tiến trình Python, 200.000 dòng mất 100 đến 230 giây. Bộ sinh đóng gói theo toàn thế giới (dòng đệm, tập `pools`), nên khó phân mảnh theo công ty.
**Cách làm đề xuất:** thay vì tái cấu trúc, **sinh nhiều thế giới nhỏ độc lập song song** (mỗi thế giới 200.000 dòng, 40 đến 60 công ty, seed khác) bằng `joblib.Parallel` hoặc nhiều tiến trình; gộp bằng cách thêm tiền tố tên thế giới vào mọi khóa (đã có mẫu trong `eval_v4.prepare`). Đạt 2 đến 10 triệu dòng với 10 đến 50 thế giới.
Nếu cần một thế giới đơn rất lớn: tái cấu trúc `make_background` để sinh theo công ty và lưu đệm theo công ty; chỉ làm khi có lý do.
**Đồng thời:** định dạng parquet cho các bảng lớn; cập nhật `data.load` đọc parquet.
**Xong khi:** sinh 20 thế giới trong dưới 1 giờ trên máy 20 luồng; đo bộ nhớ.

## D4. Tập niêm phong v5 với kịch bản độc lập

**Vì sao:** niêm phong v4 do cùng người viết, nên chưa độc lập tuyệt đối.
**Quy trình:**
1. **Người viết kịch bản độc lập** (kiểm toán viên, kế toán trưởng có kinh nghiệm điều tra; không thuộc nhóm phát triển phương pháp) viết 8 đến 12 kịch bản gian lận bằng văn xuôi theo mẫu: mô tả thủ đoạn; ai thực hiện; dữ liệu nào bị ảnh hưởng (giao dịch nào sinh ra, trường nào thay đổi); mức che giấu dễ, vừa, khó; ca hợp lệ giống; quy mô tiền và thời gian; nguồn thực tế (vụ án, kinh nghiệm). **Không xem mã đặc trưng, không xem kết quả.**
2. Coding agent chuyển từng kịch bản thành mã sinh `agent2/world_v5_scenarios.py` **đúng ý** người viết, không điều chỉnh để dễ hay khó phát hiện; hỏi lại người viết khi mơ hồ; người viết duyệt đầu ra mẫu (10 dòng ví dụ mỗi kịch bản).
3. Sinh 3 thế giới niêm phong v5 (seed mới), kiểm định (V1 đến V12), băm và **khóa** (không chạy bộ phát hiện).
4. Chạy bộ phát hiện đúng một lần với cấu hình đã đóng băng (kết quả pha B). Báo cáo như A5.
**Cảnh báo:** nếu người viết là chính coding agent hoặc người đã biết phương pháp thì tập này không độc lập; ghi rõ trong báo cáo.

## D5. Nền thật không nhãn và khoảng cách miền

**Điều kiện:** hỏi chủ dự án trước khi tải (nêu tên tệp, nguồn, dung lượng, giấy phép; BPI 2020 là CC BY-NC).
1. Tải BPI Challenge 2019 (728,6 MB, CC BY 4.0) và BPI 2020 (các tệp nhỏ), chi trả thành phố nếu truy cập được.
2. Viết bộ chuyển đổi sang lược đồ giao dịch chuẩn (C3): ánh xạ hoạt động sự kiện sang `txn_type`, `creator_id`, `approver_id`; những gì thiếu thì để trống và ghi.
3. Chạy hệ thống ở chế độ cold và Rules; đếm cảnh báo trên 1.000 giao dịch cho từng luật; xem thủ công 50 cảnh báo ngẫu nhiên và ghi tỷ lệ "đáng kiểm tra" (lưu ý: không phải độ chính xác).
4. Chẩn đoán khoảng cách miền `agent2/domain_gap.py`: lấy các trường không nhãn chung (giờ trong ngày, thứ, log số tiền, tỷ lệ loại nghiệp vụ, độ trễ giữa tạo và duyệt) của dữ liệu thật và dữ liệu sinh; huấn luyện LightGBM phân biệt "thật hay sinh"; AUC cao nghĩa là khác nhau rõ; liệt kê đặc trưng phân biệt mạnh nhất (SHAP hoặc độ quan trọng) để sửa bộ sinh.
**Xong khi:** báo cáo `docs/02_du_lieu/13_khoang_cach_thuc_te.md` với các điều chỉnh bộ sinh đề xuất.
