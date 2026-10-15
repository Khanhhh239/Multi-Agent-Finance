# DATA.md — Dữ liệu của Agent 2: nguồn, cách chọn, cách sinh, mô tả, tính chất

**Trả lời thẳng:** đúng, toàn bộ dữ liệu dùng để huấn luyện và đánh giá hiện nay là **tổng hợp hoặc mô phỏng**. Chưa có một dòng dữ liệu kế toán thật nào của doanh nghiệp nhỏ Việt Nam. Hai bộ dữ liệu công khai nước ngoài tôi tải cũng là dữ liệu mô phỏng (một bộ sinh bằng chương trình, một bộ sinh từ trò chơi ERPsim do người chơi đóng vai). Hệ quả: mọi con số hiệu quả trong báo cáo chỉ nói về thế giới mô phỏng, không nói về doanh nghiệp thật.

Quy ước độ tin cậy: **[Đ]** đã đọc tài liệu gốc hoặc kiểm tra trực tiếp trên tệp; **[T]** chỉ có từ tóm tắt hoặc kết quả tìm kiếm; **[N]** đề xuất hoặc giả định của tôi.

---

## 1. Vì sao phải dùng dữ liệu tổng hợp

- Không có bộ dữ liệu công khai nào gán nhãn gian lận nội bộ của doanh nghiệp nhỏ. Bài của nhóm Đại học Würzburg nêu rõ dữ liệu hệ thống ERP nói chung không được công bố [Đ, Phần 6]. Gói dữ liệu của bạn bạn cũng là tổng hợp.
- ACFE *Occupational Fraud 2024* (1.921 vụ, 138 nước) cho tổn thất, thời gian kéo dài và cơ cấu loại gian lận theo quy mô tổ chức, **không** cho tỷ lệ gian lận theo giao dịch và không có số riêng cho Việt Nam [Đ]. Do đó tỷ lệ 0,3% giao dịch là giả định của tôi [N], không phải ước lượng thực tế.
- Hệ quả thiết kế: dữ liệu tổng hợp chỉ dùng để (a) so sánh phương pháp với nhau trên cùng một thế giới, (b) kiểm tra hệ thống có chạy đúng từ đầu đến cuối, (c) đo ngân sách cảnh báo. Không dùng để suy ra độ chính xác thực địa.

## 2. Các nguồn tham khảo và quyết định chọn / không chọn

| Nguồn | Nội dung | Quyết định | Lý do |
|---|---|---|---|
| ACFE, *Occupational Fraud 2024: Report to the Nations* [Đ] | Cơ cấu loại gian lận (billing 31%, check/payment tampering 23%, expense 20%, payroll 14%, skimming 19%… ở nhóm dưới 100 nhân sự), tổn thất trung vị 145.000 USD, kéo dài 12–18 tháng | **Dùng làm khung kịch bản** (`agent2_data/calibration_fraud.json` của phiên trước) | Nguồn chuẩn duy nhất theo quy mô tổ chức; chỉ dùng cho loại kịch bản, không dùng cho tần suất |
| Gói `zipp.zip` của bạn bạn (`sme_fraud/`) [Đ] | Bộ sinh SME Việt Nam, kế toán TT133/TT200, 190 đặc trưng, 31 luật | **Dùng làm nền**, kế thừa bộ sinh | Đúng phạm vi bài toán (gian lận nội bộ SME, tiền đồng, TT133/TT200); có kế toán cân Nợ = Có và đặc trưng chỉ dùng quá khứ |
| Tritscher và cộng sự 2022, *Open ERP System Data For Occupational Fraud Detection* (arXiv 2206.04460) + dữ liệu Würzburg [Đ] | 5 lần chạy ERPsim trên SAP, 12 kịch bản (8 mua hàng–thanh toán, 4 bán hàng–thu tiền), nhãn từng dòng, tỷ lệ gian lận 0,06–0,23% | **Tải, dùng làm kiểm tra bên ngoài** (190 MB, chỉ giải nén CSV, không chạy mã) | Nhãn gian lận nghề nghiệp thật kiểu quy trình ERP; lược đồ SAP khác lược đồ của ta nên không dùng làm dữ liệu huấn luyện chính |
| Gronewald và cộng sự, DFKI *General Ledger Data* (Data in Brief 2026; Zenodo 10.5281/zenodo.22014653, CC BY 4.0) [Đ cho trang Zenodo và tệp] | 256.232 dòng, 102.429 bút toán, 850 bất thường chèn (0,83%), 6 người dùng, 2023–2024, bảng tài khoản DATEV | **Tải, dùng làm kiểm tra bên ngoài** (31,1 MB, MD5 khớp) | Sổ cái có nhãn bất thường; nhãn chèn nằm trong danh sách phép thử bút toán nên có vòng tròn (đã nêu trong báo cáo) |
| Schreyer và cộng sự 2017 (arXiv 1709.05254) [Đ] | 2 sổ cái SAP thật ẩn danh, 95 và 100 bút toán chèn | Chỉ tham khảo cách chèn bất thường (giá trị hiếm, tổ hợp hiếm); dữ liệu không công khai | Cho thấy bất thường chèn kiểu này là loại dễ nhất |
| Gronewald và cộng sự, *Anomaly Detection in General Ledger Data: Results from a Hybrid Approach* (arXiv 2609.18228) [Đ] | 51.076 bút toán tổng hợp, 573 bất thường chèn **chỉ trong danh sách phép thử** | Chỉ tham khảo, rút bài học thiết kế | Bài học: không được chèn bất thường theo đúng luật đang đánh giá (vòng tròn) |
| BPI Challenge 2019 / 2020 (4TU) [T] | Mua hàng–thanh toán và chi phí công tác của tổ chức Hà Lan, không nhãn | **Không tải** | Không nhãn; lược đồ khác; chỉ hữu ích để đếm cảnh báo trên 1.000 giao dịch, để dành |
| PaySim, BankSim, IBM AMLSim, SAML-D, Bank Account Fraud, Elliptic [Đ, Phần 6] | Gian lận chuyển tiền di động, mở tài khoản, rửa tiền, giao dịch Bitcoin | **Không dùng** | Gian lận bên ngoài hoặc rửa tiền, không có nhà cung cấp, bút toán, phê duyệt, lương; ngoài phạm vi Agent 2 |
| ICIJ Offshore Leaks, chi trả nhà cung cấp của chính quyền thành phố (Chicago, NYC) [T] | Đồ thị pháp nhân thật; chi trả công | **Không tải** | Chưa truy cập được tự động (403, 405); không nhãn gian lận |
| Nghị định 123/2020/NĐ-CP (hóa đơn điện tử định dạng XML) [T, nguồn thứ cấp] | Hóa đơn có dòng hàng, đơn giá, số lượng | Cơ sở để **mô phỏng đơn giá** trong v3 và để khuyến nghị dữ liệu thật cần thu | Hóa đơn điện tử là nguồn dữ liệu có cấu trúc thật của SME Việt Nam |
| Thông tư 200/2014/TT-BTC, 133/2016/TT-BTC (tài khoản kế toán) [T, qua báo cáo kế toán của bạn bạn] | Hệ thống tài khoản | Dùng trong sổ cái mô phỏng | Phân biệt chế độ kế toán doanh nghiệp theo công ty |

**Cách chọn nói gọn:** chọn theo ba tiêu chí: (1) đúng phạm vi gian lận nội bộ doanh nghiệp nhỏ; (2) có nhãn hoặc tạo được nhãn trung thực; (3) tránh vòng tròn giữa cách chèn và cách phát hiện. Dữ liệu ngoài chỉ dùng để kiểm tra chéo, vì không bộ nào có lược đồ Việt Nam.

## 3. Thế giới dữ liệu v3 (dữ liệu chính của đợt này)

Mã: `agent2/world_v3.py` (kế thừa `sme_fraud/generate.py`), kiểm tra: `agent2/validate_v3.py`. Vị trí: `work/data/w3_s201..205` (5 seed). Tất cả tạo bằng bộ sinh ngẫu nhiên có seed, tái lập được.

### 3.1. Vì sao không dùng nguyên bộ v2 của bạn bạn
Kiểm tra trực tiếp [Đ]: (1) cả 400 nhà cung cấp nền cùng ngày onboard 01/01/2023, nên tuổi nhà cung cấp tự phân biệt gian lận; (2) 2.043 tên nhà cung cấp cùng tiền tố, nên luật E3 báo 100% dòng; (3) nhà cung cấp được chọn đều ngẫu nhiên, số tiền không phụ thuộc nhà cung cấp, không mùa vụ; (4) 31 luật viết đúng theo 6 kịch bản chèn, một seed, năm công ty gần giống, một mức khó. Kết quả: luật đạt AP 0,60 trên v2 nhưng chỉ 0,24 trên v3.

### 3.2. Cấu trúc
- **Cửa sổ thời gian:** huấn luyện 01/2024–12/2024; kiểm định 01/2025–06/2025; kiểm thử 07/2025–12/2025. 50.000 / 25.000 / 25.000 dòng; 150 / 75 / 75 dòng gian lận.
- **Đơn vị quan sát:** một giao dịch đã ghi sổ (hoặc một lần rà soát tạm ứng phi tài chính). 100.000 dòng, 300 dòng gian lận (0,3%) mỗi seed.
- **Công ty:** 8 công ty, 5 ngành (thương mại, sản xuất, dịch vụ, bán lẻ, vận tải), 16–44 nhân sự, 45–140 nhà cung cấp, 30–80 khách hàng, thang số tiền 0,5–2,0; chế độ kế toán TT200 hoặc TT133 theo công ty. Ví dụ seed 201: 635 nhân sự, 2.381 nhà cung cấp, 440 khách hàng, 63.012 hóa đơn, 335.454 dòng bút toán.
- **Bảng:** transactions (52 cột), labels, splits, vendors, employees, customers, invoices, journal_documents, journal_lines, document_links, account_flow_edges, entity_links, attendance, vendor_status_history, bank_account_changes, advances, advance_events, calendar, features. Nhãn nằm **chỉ** ở `labels.csv`, không có trong giao dịch hay đặc trưng (kiểm tra bằng test).
- **Loại giao dịch (seed 201):** 21 loại, lớn nhất: thanh toán nhà cung cấp 29.973, hóa đơn bán 11.951, thu tiền 11.183, mua hàng 10.120, chi tiền mặt 8.611, giá vốn 5.524, lương 3.411, điều chỉnh 3.254.

### 3.3. Cách sinh phần "bình thường" (sửa các lỗi của v2) [N: là giả định thiết kế]
| Thành phần | Cách sinh |
|---|---|
| Ngày onboard nhà cung cấp | 55% "cũ" rải đều 2018–2022; 45% rải 01/2023–10/2025; giao dịch chỉ phát sinh sau ngày onboard |
| Độ phổ biến nhà cung cấp | trọng số 1/(1+j)^0,9 × U(0,6; 1,4) (kiểu Zipf) |
| Số tiền theo nhà cung cấp | lognormal, μ = ln(8 triệu × thang công ty) + N(0; 0,9), σ ∈ U(0,18; 0,35); 12% nhà cung cấp có bước tăng giá hợp lệ 15–30% từ một ngày trong 09/2024–08/2025 |
| Đơn giá và số lượng | mỗi nhà cung cấp có đơn giá lognormal(ln 250.000; 1,0), nhiễu ±1,5%; số lượng = số tiền / đơn giá (mô phỏng dòng hàng của hóa đơn điện tử XML) |
| Thuê nhà | một nhà cung cấp cố định, số tiền cố định theo công ty |
| Tên | "Công ty {loại hình} {ngành} {tên riêng}" từ danh sách đa dạng; một số cặp chi nhánh hợp lệ có tên gần giống |
| Mùa vụ | trọng số ngày: ngày lễ ×0,12; 14 ngày trước Tết ×1,6; từ ngày 26 hàng tháng ×1,3; tháng 11–12 ×1,12; cuối tuần giảm |
| Hạn mức, tự duyệt, giờ làm việc, chứng từ đi kèm | giữ cơ chế của bộ sinh gốc (giám đốc 100 triệu, kế toán trưởng 50 triệu, kế toán 20 triệu; tự duyệt ≤ 2 triệu với người không phải giám đốc) |

### 3.4. Gian lận: 9 họ × 3 mức khó
Số dòng gian lận được chia đều giữa các họ trong từng giai đoạn; mức khó chọn ngẫu nhiên 40% dễ / 35% vừa / 25% khó (với họ tạm ứng, mức ghi "mixed").

| Họ | Loại ACFE tương ứng | Mô tả ngắn | Ghi chú |
|---|---|---|---|
| ghost_vendor | billing | NCC trùng tài khoản/điện thoại/địa chỉ với nhân viên; NCC vỏ mới lập; nhân viên ma | mức khó: NCC cũ "ngủ đông", liên kết qua người đại diện |
| split_payments | billing / expense | chia nhỏ thanh toán để né hạn mức | mức khó: 2–3 khoản 55–80% hạn mức, hai nhà cung cấp |
| duplicate_payment | check/payment tampering | trả trùng hóa đơn | khó: khác số hóa đơn, lệch ±3%, cách 3–20 ngày |
| period_end_adjustment | financial statement | bút toán tay cuối kỳ | khó: người duyệt thứ hai thông đồng, số tiền lớn |
| risky_invoice | billing | hóa đơn của nhà cung cấp đã ngừng hoạt động | một phần chỉ lộ ra sau (registry reported later) |
| long_outstanding_advance | expense / noncash | tạm ứng quá hạn hoặc xóa nợ thiếu hồ sơ | giữ nguyên bộ sinh gốc |
| kickback_overpricing | corruption | cặp lập–duyệt cố định mua giá cao 10–70% hơn mức thường của nhà cung cấp | **không luật nào viết sẵn** |
| expense_padding | expense reimbursements | chi tiền mặt tự duyệt lặp lại sát hạn mức 2 triệu, thiếu chứng từ | **không luật nào viết sẵn** |
| payroll_padding | payroll | nâng lương một nhân viên 8–100% trong 2–4 tháng liền | **không luật nào viết sẵn** |

### 3.5. Ca hợp lệ giống gian lận (hard negatives)
17 loại, khoảng 6% số dòng: 13 loại của bộ gốc (đổi tài khoản đã xác minh, tự duyệt hợp lệ, làm cuối tuần, tiền thuê tròn, trả góp hợp lệ, NCC mới hợp lệ, bên liên quan đã công bố, duyệt chậm, nhân sự làm từ xa, gia hạn/xóa nợ tạm ứng có hồ sơ, chốt kỳ hợp lệ, hóa đơn lịch sử hợp lệ) và 4 loại mới: **thưởng Tết** (74), **thưởng cuối năm** (93), **tăng giá hợp lệ** (656), **mua dồn hợp lệ** (321) (số của seed 201). Dùng để đo "báo nhầm trên ca giống gian lận" mà dữ liệu thật mới có.

### 3.6. Đặc trưng
- 190 đặc trưng của bạn bạn: thời gian, hạn mức, tự duyệt, quan hệ nhà cung cấp–nhân viên, lịch sử hóa đơn, đồ thị, tài khoản Nợ/Có, cặp tài khoản. Chỉ dùng dữ liệu trước thời điểm chấm điểm.
- **30 đặc trưng thực thể** của tôi (`agent2/feats.py`), tính một lượt theo thời gian: lệch đơn giá so với trung vị 20 lần mua gần nhất của chính nhà cung cấp (z, tỷ lệ, dịch chuyển 3 lần gần nhất), lệch lương so với trung vị 12 tháng không thưởng của chính nhân viên, tập trung cặp người lập–người duyệt 90 ngày, khoản gần trùng (±3%) 30 ngày, chi tiền mặt tự duyệt thiếu chứng từ lặp lại, v.v. Có test chứng minh đặc trưng **nhân quả** (cắt dữ liệu tương lai thì đặc trưng quá khứ không đổi).

### 3.7. Kiểm tra chất lượng (`validate_v3.py`, mọi bộ đều qua)
Khóa ngoại và công ty; trình tự thời gian lập ≤ duyệt ≤ ghi sổ trong cửa sổ; tổng Nợ = tổng Có mọi chứng từ; không có nhãn trong giao dịch/đặc trưng; mỗi vụ chỉ nằm trong một giai đoạn; đủ 9 họ; số dòng gian lận đúng ngân sách; không còn cùng ngày onboard (tối đa < 2%) và tên đa dạng (tên riêng trùng < 10%); tuổi nhà cung cấp còn phân biệt gian lận (AUC 0,24–0,30) vì NCC vỏ mới lập là dấu hiệu thật. Đã bắt và sửa hai lỗi của tôi: tiền thuê trả cho nhà cung cấp chưa tồn tại; thanh toán vượt cửa sổ thời gian.

## 4. Tập niêm phong (kiểm thử cuối)

`agent2/world_sealed.py`, `work/data/sealed_s901..903`. 3 thế giới, tỷ lệ 0,36% (360 gian lận mỗi bộ), 12 họ = 9 họ trên + 3 họ **chưa từng dùng khi phát triển**: `price_creep` (một cặp thông đồng tăng đơn giá 2–4% mỗi lần trả, không có bước nhảy), `off_cycle_payroll` (khoản lương thêm ngoài ngày trả lương), `vendor_burst` (4–6 khoản cho các nhà cung cấp khác nhau trong một buổi tối). Thêm một loại mồi (`legit_offcycle_payroll`). Viết trước khi xem kết quả phát hiện, chạy đúng một lần với cấu hình đóng băng.

## 5. Hai bộ dữ liệu công khai bên ngoài

| | DFKI General Ledger | ERP Fraud Data (Würzburg) |
|---|---|---|
| Bản chất | tổng hợp bằng chương trình, doanh nghiệp thương mại Đức, 6 kế toán, DATEV SKR03 | mô phỏng trò chơi ERPsim trên SAP, người chơi đóng vai, một người được kiểm toán viên hướng dẫn gian lận |
| Quy mô | 102.429 bút toán, 25 tài khoản, 2023–2024 | 5 lần chạy: 54.677 và 32.337 giao dịch bình thường; 39.430 (24 gian lận), 36.778 (50), 37.407 (86) |
| Tỷ lệ dương | 0,83% | 0,06% đến 0,23% |
| Nhãn | 1 bút toán; còn có 5 cờ phép thử bút toán | từng dòng, kèm tên kịch bản; có tệp giải thích đặc trưng |
| Giấy phép | CC BY 4.0, MD5 đã khớp | trang gốc không nêu |
| Hạn chế | bất thường chèn trong danh sách phép thử; chỉ 6 người dùng | 5 người chơi mỗi nhóm; chỉ bảng mua hàng; không có nhà cung cấp ma hay nhân sự ma |
| Dùng để | kiểm tra phương pháp không giám sát và giá trị của danh sách phép thử | kiểm tra không giám sát, giám sát theo lần chạy và bỏ một kịch bản |

## 6. Tính chất cần nhớ khi dùng dữ liệu

1. **Mất cân bằng cực đoan:** 0,3% dương. AP ngẫu nhiên = 0,003. ROC-AUC luôn 0,85–0,99 dù AP thấp, nên không dùng làm tiêu chí.
2. **Nhãn là ý đồ gian lận do bộ sinh gán**, không phải kết luận của người có chuyên môn; một vụ gồm nhiều dòng, nên chia theo vụ và đo theo vụ.
3. **Mỗi thế giới có cơ chế chung:** mô hình học trước có thể "học" dấu vết của bộ sinh (ví dụ lương luôn trả ngày 28). Vì vậy dùng giao thức bỏ một họ, chéo thế giới và tập niêm phong.
4. **Không có dữ liệu thật** để hiệu chỉnh số tiền, tần suất, mùa vụ và mức đa dạng tên; đây là việc cần làm với doanh nghiệp đối tác.
5. **Dữ liệu cần thu thập tiếp (ưu tiên):** hóa đơn điện tử XML theo dòng hàng; danh mục nhà cung cấp và nhân viên đã chuẩn hóa; lịch lương và hợp đồng; nhật ký lập/duyệt; sao kê ngân hàng; kết luận của người rà soát cho một mẫu cảnh báo.

## 7. Cách tái tạo
```powershell
$env:PYTHONPATH = (Get-Location)
python -m agent2.world_v3 --output work/data/w3_s201 --rows 100000 --fraud-rate 0.003 --seed 201 --companies 8
python -m agent2.validate_v3 --data work/data/w3_s201
python work/gen_sealed.py        # tập niêm phong, seed 901-903
```
