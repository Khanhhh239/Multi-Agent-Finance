# 10. Realism v2 và C2ST tách đặc trưng (Sprint 4, 21/10/2026)

## 10.1 Vấn đề
C2ST gốc (`structural-company-split-v1`) cho AUC 0,996–0,997: bộ phân loại tách được dữ liệu tổng hợp khỏi bộ AR giống ERP
(Customer Invoices) gần như hoàn hảo. Đặc trưng phân biệt chính là `term_days` (gain 618k), tiếp theo `late_days`, `log_amount_rel`.

Kết luận sai nếu đọc nguyên văn: "máy phát kém". Thực chất AUC gộp hai loại khác biệt khác bản chất:

| Loại | Ví dụ | Xử lý |
|---|---|---|
| **Khác biệt có chủ đích** | `term_days`: bộ Mỹ 74% kỳ hạn 15 ngày (mã SAP) vs VN theo Atradius (45 ngày TB); mức trễ: bộ Mỹ 2,2% trễ >30 ngày vs VN "khoảng một tháng" | **Không sửa** cho giống bộ Mỹ. Báo cáo riêng, không đặt mục tiêu |
| **Khác biệt hình dạng/hành vi** | độ phân tán số tiền (log-sd thật 1,78 vs 0,91), hoá đơn lập cuối tuần (thật 19% vs 3%), nhịp thứ trong tuần, hình dạng phân phối trễ, độ bền hành vi theo khách | **Sửa** nếu mô tả dạng ERP thật |

## 10.2 Tách đặc trưng (`agent1/synth/c2st.py::FEATURE_SETS`)

| Bộ | Đặc trưng | Mục tiêu đăng ký trước |
|---|---|---|
| `legacy_full` | 7 đặc trưng gốc | không (giữ để so với v1) |
| `designed` | `term_days` | không — AUC ≈1 là hệ quả của thiết kế VN |
| `behavioral` | `log_amount_rel`, `issue_dow`, `due_dow`, `paid_dow`, `issue_dom`, `due_dom`, `paid_dom`, `issue_weekend`, **`late_rank`** (hạng phân vị trễ trong công ty — bỏ chênh lệch mức trễ, giữ hình dạng), **`cust_late_loo`** (trung bình `late_rank` của khách trên các HĐ khác — độ bền hành vi), `cust_n` | **AUC < 0,75** |

Đặc trưng cấp khách được tính trên toàn bộ miền rồi mới lấy mẫu 100k dòng (bản đầu tính sau lấy mẫu làm lệch số HĐ/khách giữa hai miền — đã sửa).
Chia train/test theo **công ty**; CI bootstrap theo cụm.

## 10.3 Realism v2 (`WorldConfig(realism="v2")`, mặc định `v1`, các thế giới cũ không đổi)

| Thay đổi | v1 | v2 | Căn cứ (hình dạng ERP, không phải hiệu chỉnh VN) |
|---|---|---|---|
| Ngày trong tuần của HĐ | T2–T6 mỗi ngày 19%, T7 5% | T2 15%, T3 16,5%, T4 17,5%, T5 16,5%, T6 16,5%, T7 11,5%, CN 6,5%; 85% HĐ cuối tuần được giữ (dời nếu ngày lễ) | bộ AR thật: 19% HĐ lập cuối tuần |
| Phân tán số tiền trong cùng khách | lognormal σ=0,75 | σ=1,15 (chuẩn hoá giữ nguyên kỳ vọng doanh thu) | log-sd tương đối thật 1,78 |
| HĐ nhỏ/điều chỉnh | không | 6% HĐ nhân thêm lognormal(−2,5; 0,8) | đuôi trái dày (min log −11) |

Thanh toán vẫn chỉ vào ngày làm việc (không đổi): bộ thật có 0,34% trả cuối tuần.

## 10.4 Kết quả (`outputs/data/c2st_split.csv`, `c2st-split-v1`; thật = Customer Invoices, 6 "công ty")

| Thế giới | legacy_full | designed (kỳ hạn) | **behavioral** | CI 95% behavioral |
|---|---|---|---|---|
| `src` (v1, 40 công ty) | 0,968 | 0,923 | **0,672** | [0,63; 0,84] |
| `sens_uk` (v1) | 0,969 | 0,891 | 0,787 | [0,74; 0,90] |
| `sens_coface` (v1) | 0,977 | 0,961 | 0,755 | [0,63; 0,89] |
| `c2st_ctrl_v1` (v1, 12 công ty, đối chứng cặp) | 0,967 | 0,920 | 0,734 | [0,65; 0,86] |
| **`c2st_v2`** (v2, cùng seed/12 công ty) | 0,955 | 0,923 | **0,691** | [0,59; 0,87] |
| `c2st_v2_customers_exp` (v2 + khách mua lẻ/dị biệt) | 0,961 | 0,930 | 0,806 | [0,77; 0,83] |

**Đọc kết quả:**
1. **"AUC 0,996" không phải do hành vi.** Bộ `behavioral` đã là 0,67–0,79 ở các thế giới cũ; `designed` (chỉ kỳ hạn) một mình đã 0,89–0,96. Cổng "<0,75" trước đây đặt cho bộ gộp là đặt sai chỗ; áp cho `behavioral`: `src` (0,67) và v2 (0,69) đạt; `sens_uk` (0,79) và `sens_coface` (0,76) chưa.
2. **v2 giảm AUC hành vi 0,734 → 0,691 (−0,043) so với đối chứng cặp, nhưng CI chồng lên nhau** ([0,59; 0,87] vs [0,65; 0,86]) ⇒ cải thiện nhỏ, **chưa chứng minh có ý nghĩa thống kê** (chỉ có 6 công ty thật).
   Tác động đúng chỗ: gain của `log_amount_rel` 27,9k → 4,4k, `issue_dow` 10,7k → 5,9k.
3. **Phần khách hàng chưa giải được.** Còn phân biệt chủ yếu bằng `late_rank`, `cust_n`, `cust_late_loo`. Bộ thật: trung vị 3 HĐ/khách, 10% khách chỉ 1 HĐ, p99 463 HĐ; máy phát v1: trung vị 25–40, p10 4–6.
   Thử thêm khách mua lẻ + dị biệt (`customer_realism`): phân bố nửa dưới giống hơn (p10 = 1, trung vị 6) nhưng độ tập trung tụt (top-10 pooled 0,11 vs 0,43) và **AUC tăng lên 0,806** ⇒ **thất bại, không bật**; giữ làm cờ thử nghiệm.
4. Bộ `designed` ≈ 0,92: **không sửa**, đây là khác biệt thiết kế (kỳ hạn VN theo Atradius, 45 ngày TB, vs 15 ngày kiểu SAP Mỹ).

## 10.5 Vòng 3: cửa sổ quan sát (`--window-months 15`, `outputs/data/c2st_split_window15m.csv`)

**Phát hiện:** bộ thật dài ~14 tháng/công ty, thế giới tổng hợp 84 tháng. `cust_n` (số HĐ/khách) và tỷ lệ khách 1 HĐ do **độ dài cửa sổ**
quyết định, không phải hành vi. So theo công ty (bộ thật): trung vị 2 HĐ/khách, 35% khách chỉ 1 HĐ trong 14 tháng; v1 trên 84 tháng: 26 HĐ/khách, 1%.
Hàm `agent1/synth/c2st.py::match_window` cắt mỗi công ty tổng hợp về một cửa sổ liên tục cùng độ dài.

| Thế giới | behavioral toàn cửa sổ | **behavioral 15 tháng** | CI 95% |
|---|---|---|---|
| `c2st_ctrl_v1` | 0,734 | 0,745 | [0,54; 0,88] |
| `c2st_v2` | 0,691 | 0,697 | [0,48; 0,76] |
| `c2st_v2_customers_exp` | 0,806 | 0,699 | [0,24; 0,83] |
| `src` | 0,672 | 0,785 | [0,63; 0,86] |
| `sens_uk` | 0,787 | 0,841 | [0,79; 0,91] |
| `sens_coface` | 0,755 | 0,764 | [0,62; 0,82] |

**Kết luận (quan trọng hơn mọi con số ở trên):**
- Chỉ đổi cửa sổ đo, thứ hạng các bản đã đảo: bản "thất bại" ở vòng 2 nay ngang v2; `src` từ tốt nhất thành kém thứ hai.
  CI rộng 0,3–0,6 điểm AUC, lớn hơn mọi khác biệt giữa các phiên bản máy phát.
- ⇒ **Bộ tham chiếu 6 "công ty" không đủ để chọn giữa các phiên bản máy phát.** Chỉnh tiếp theo con số này là khớp nhiễu.
  **Dừng chỉnh máy phát theo C2ST** cho tới khi có bộ thật nhiều công ty hơn.
- Điều chắc chắn rút ra: (1) AUC 0,996 cũ chủ yếu do kỳ hạn (chủ đích) và do so khác cửa sổ; (2) bộ hành vi quanh 0,70–0,79, không phải ≈1.
- `realism='v2'` giữ làm tuỳ chọn (tác động đúng chỗ ở `log_amount_rel` và `issue_dow`), **không** bật mặc định, **không** sinh lại `src/tgt/big_*`.

## 10.6 Việc tiếp theo (đề xuất, chưa làm)
- Lấy bộ thật tham chiếu nhiều công ty hơn (ứng viên đã có trong kho: BPI 2019 có nhiều `company`/vendor; cần ánh xạ sang hoá đơn AR và kiểm tra tính hợp lệ).
- Sau đó mới khớp độ tập trung khách theo công ty và hình dạng trễ.

## 10.7 Giới hạn
- Bộ thật tham chiếu chỉ có 6 "công ty" (mã `business_code`) và nguồn gốc không rõ ⇒ AUC có CI rộng; không dùng làm cổng sản phẩm.
- Sửa hình dạng cho giống ERP Mỹ **không** chứng minh giống SME VN; v2 chỉ giảm khoảng cách về hình dạng tổng quát.
- Chưa sinh lại `src/tgt/big_*` bằng v2 (RAM, và sẽ đổi toàn bộ kết quả); quyết định áp dụng v2 cho dữ liệu huấn luyện chính thuộc người giao việc sau khi xem 10.4.
