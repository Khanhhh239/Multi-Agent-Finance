# Hiểu toàn bộ dự án Agent 1 — bản dễ nhớ (cập nhật 24/10/2026, chiều)

> **Ảnh chụp ngày 24/10/2026.** Dùng tài liệu này để hiểu kiến trúc và lịch sử kết quả; các mục “hiện tại”, số World và cổng trong thân bài không thay [hướng dẫn nguồn hiện hành](AI_READING_GUIDE.md).

> Mục tiêu của tài liệu này: đọc một lần (khoảng 40 phút) là nắm được **dự án làm gì, làm bằng cách nào, đã tới đâu, tin được tới mức nào, và việc tiếp theo là gì**.
> Mọi con số lấy từ kết quả đã đo trong `outputs/` và `docs/03_Evaluation/GATES_CURRENT.md`. Chỗ nào chưa chắc, tài liệu nói rõ là chưa chắc.

---

## Mục lục

1. [Dự án trong 60 giây](#1-dự-án-trong-60-giây)
2. [Bài toán: vì sao SME thiếu tiền dù có lãi](#2-bài-toán)
3. [Sản phẩm: hệ thống trả lời gì mỗi tuần](#3-sản-phẩm)
4. [Hệ thống chạy thế nào: dây chuyền 6 trạm](#4-dây-chuyền-6-trạm)
5. [Dữ liệu: thật, sinh, và vì sao cần cả hai](#5-dữ-liệu)
6. [Cách đo trung thực: "đề thi niêm phong"](#6-cách-đo-trung-thực)
7. [Kết quả chính, từng trạm một](#7-kết-quả-từng-trạm)
8. [Bảng 18 cổng nghiệm thu](#8-bảng-18-cổng)
9. [Những lần làm sai và bài học](#9-làm-sai-và-bài-học)
10. [Tin được tới đâu: đã chứng minh / chưa chứng minh](#10-tin-được-tới-đâu)
11. [Cách triển khai an toàn: 4 bậc và 5 luật](#11-triển-khai-an-toàn)
12. [Tình hình hiện tại và việc tiếp theo](#12-tình-hình-hiện-tại)
13. [Từ điển thuật ngữ](#13-từ-điển)
14. [Bản đồ file](#14-bản-đồ-file)

---

## 1. Dự án trong 60 giây

**Agent 1 = "Trợ lý Dòng tiền" cho doanh nghiệp nhỏ và vừa (SME) Việt Nam.**

Mỗi tuần nó trả lời bốn câu hỏi:

| # | Câu hỏi của chủ doanh nghiệp | Hệ thống trả lời bằng |
|---|---|---|
| 1 | 13 tuần tới, **tuần nào** tôi có thể hết tiền? | Dải số dư P10/P50/P90 từng tuần |
| 2 | **Xác suất** bao nhiêu? | % thiếu hụt trong 4 tuần và 13 tuần |
| 3 | Nên **đòi khoản nào trước**? | Danh sách hoá đơn xếp theo mức giảm rủi ro |
| 4 | **Nếu** khách lớn trả chậm 2 tuần thì sao? | Mô phỏng kịch bản "nếu như" |

**Tình trạng một dòng:** hệ thống chạy được từ đầu đến cuối, qua **9/18 cổng gốc** (cộng thêm 2 cổng thay thế mới đạt sát ngưỡng: G14, G17), nhưng **chưa từng thấy dữ liệu doanh nghiệp Việt Nam thật**. Nên kết luận hiện tại là: *được chạy thử "bóng" (ghi dự báo, không ai hành động theo), chưa được dùng để ra quyết định thật.*

**Ba điều cần nhớ nhất:**

1. Mọi kết quả tốt đều trên dữ liệu **sinh** hoặc dữ liệu thật **nước ngoài**. Đúng với dữ liệu sinh ≠ đúng với doanh nghiệp thật.
2. Mô hình thông minh **có lúc thua** cách đoán đơn giản (BPI: thua 62,5%). Vì vậy hệ thống luôn **trộn** với cách đơn giản và có **cầu dao tự ngắt**.
3. Cảnh báo thiếu tiền phụ thuộc vào **độ phủ nhãn của trạm ghép sao kê (T9)**: ghép được càng nhiều hoá đơn đã trả thì cảnh báo càng đúng. Đã kiểm chứng bằng thí nghiệm (mục 7.5).

---

## 2. Bài toán

### 2.1 Vì sao doanh nghiệp có lãi vẫn thiếu tiền

Con số nền (Atradius Việt Nam 2025):

| Chỉ số | Giá trị |
|---|---|
| Doanh số B2B bán chịu | **65%** |
| Kỳ hạn thanh toán điển hình | **45 ngày** |
| Giá trị hoá đơn quá hạn | **39%** |
| Khách trả chậm thêm | khoảng **1 tháng** |
| Nợ xấu | khoảng **3%** |
| Nguyên nhân trễ do chính khách thiếu thanh khoản | **47%** |

**Hình ảnh dễ nhớ:** lợi nhuận trên sổ giống *số trên bảng lương*; tiền mặt giống *tiền trong ví hôm nay*. Bạn có thể "kiếm" 100 triệu trên sổ mà ví trống vì khách chưa trả. Lương, thuế, tiền thuê **không đợi**.

### 2.2 Vì sao bảng tính Excel không đủ

Bảng tính giả định *"khách trả đúng hạn"*. Thực tế khách trả **lệch**, và các khách trả chậm thường **cùng lúc** (khi thị trường thiếu tiền, ai cũng chậm). Hai điều Excel không làm được:

- Dự báo **thời điểm** tiền về là một *phân phối* (có thể sớm, có thể muộn), không phải một con số.
- Các khoản chậm **tương quan** với nhau. Khi tính xác suất thiếu hụt, coi chúng độc lập sẽ **đánh giá thấp rủi ro**.

---

## 3. Sản phẩm

Ba lớp đầu ra, từ đơn giản đến phức tạp:

```
Lớp 1  Ngày khách trả       → "Hoá đơn A có 70% khả năng được trả trong tuần 3–5"
Lớp 2  Dải số dư theo tuần   → "Tuần 6: P10 = -40tr, P50 = +120tr, P90 = +300tr"
Lớp 3  Hành động             → "Đòi hoá đơn B và C trước giảm rủi ro thiếu hụt 18 điểm %"
```

**P10/P50/P90 là gì?** Chạy hàng nghìn kịch bản. P50 = kịch bản "giữa". P10 = kịch bản *tệ* (chỉ 10% kịch bản tệ hơn). P90 = kịch bản *tốt*. Khoảng P10–P90 = "80% khả năng số dư nằm trong đây".

---

## 4. Dây chuyền 6 trạm

Hãy tưởng tượng một **nhà máy 6 trạm**. Mỗi trạm làm một việc, đầu ra trạm trước là nguyên liệu trạm sau.

```
Hoá đơn + Sao kê NH
        │
   [T0] Kiểm tra dữ liệu      → loại dữ liệu lỗi, đối chiếu luật thuế (hạn nộp, dịch hạn Tết)
        │
   [T9] Ghép sao kê ↔ hoá đơn → "khoản tiền này của khách nào, trả hoá đơn nào, ngày nào"
        │                        ⇒ tạo NHÃN ngày trả thật
   [T1] Dự báo ngày trả       → mỗi hoá đơn: xác suất trả ở từng tuần
        │
   [T4] Dự báo doanh thu      → hoá đơn MỚI sẽ phát sinh bao nhiêu
        │
   [T6] Mô phỏng số dư        → ghép tiền vào + tiền ra → dải P10/P50/P90 + xác suất thiếu hụt
        │
   [T10] Hành động            → xếp hạng hoá đơn nên đòi, kịch bản "nếu như"
```

Các trạm khác (cắm vào dây chuyền):

| Trạm | Việc | Ghi chú |
|---|---|---|
| T2 | Xác suất vỡ nợ | Thử trên dữ liệu vay SBA (Mỹ) |
| T7 | Phát hiện khách **đổi thói quen** trả | Cảnh báo sớm |
| T8 | **Lời hứa** của khách ("tuần sau tôi trả") | Tăng độ chính xác nếu lời hứa đáng tin |
| T5 | Hạn nộp thuế theo luật VN | 15 kiểm thử đạt |

*(Chi tiết T3, T11–T13: xem `04_AI_Methods/README.md`.)*

### 4.1 Trạm T1 — "đoán khi nào khách trả" (trái tim của hệ thống)

**Ý tưởng "hazard" bằng hình ảnh:** mỗi tuần, hỏi một câu: *"Nếu hoá đơn này chưa được trả tới giờ, thì tuần này khách trả chứ?"* Ghép 13 câu trả lời lại thành phân phối ngày trả.

Có hai mốc đơn giản để so (gọi là **baseline**):

| Mốc | Cách đoán | Ví dụ đời thường |
|---|---|---|
| **B1** | Lấy trung vị trễ của khách đó | "Anh Nam hay trả trễ 10 ngày" |
| **B1d** | Lấy **cả phân phối** trễ của khách đó | "Anh Nam trả trễ 3–25 ngày, thường 10" |

> Mô hình học máy chỉ đáng dùng **nếu thắng B1d**. Đây là thước đo chính xuyên suốt dự án.

**BLEND (trộn):** dự báo cuối = `w × mô hình + (1 − w) × B1d`. Trọng số `w` được chọn trên cửa sổ hiệu chỉnh của *chính doanh nghiệp*. Nếu mô hình kém, `w` tự về gần 0 và hệ thống dựa B1d.

### 4.2 Trạm T6 — "mô phỏng số dư"

Dùng **Monte Carlo + copula-t**: tạo 1.000 kịch bản; trong mỗi kịch bản các khách "cùng chậm hoặc cùng nhanh" theo mức tương quan, nhờ đó đuôi rủi ro không bị đánh giá thấp. Sau đó:

- **ACI** (Adaptive Conformal Inference) tự điều chỉnh độ rộng dải theo kết quả đã lộ diện: nếu dải hẹp quá và số dư thật cứ chui ra ngoài, nó nới ra.

### 4.3 Trạm T9 — "ghép sao kê" (và vì sao nó quyết định nhiều thứ)

Ngân hàng chỉ báo "có 150 triệu từ Công ty X, nội dung: ...". T9 phải đoán khoản này trả **hoá đơn nào**. Có ba cách:

| Cách | Ví dụ | Độ tin cậy |
|---|---|---|
| **Số hoá đơn trong nội dung** | "TT HD 0345" | **Gần 100% đúng** |
| **Số tiền duy nhất** | Chỉ một hoá đơn đúng 150tr đang mở | ~96% |
| **Đoán tổ hợp** | 150tr = hoá đơn 40 + 50 + 60? | Đúng 98% nếu ≤2 hoá đơn, **chỉ 47–74% nếu ≥3** |

---

## 5. Dữ liệu

### 5.1 Vì sao cần cả dữ liệu thật và dữ liệu sinh

| | Dữ liệu thật (nước ngoài) | Dữ liệu sinh (mô phỏng Việt Nam) |
|---|---|---|
| Ưu | Là hành vi con người thật | Biết **sự thật** (ngày trả thật, sự kiện thiếu tiền) nên chấm điểm được; sinh được tình huống hiếm |
| Nhược | Không phải Việt Nam; thiếu nhiều nhãn | Do **chính chúng ta** viết giả định; có thể sai |

**Quy tắc vàng:** dữ liệu thật dùng để *kiểm phương pháp có thật sự thắng không*; dữ liệu sinh dùng để *kiểm cả dây chuyền chạy đúng*.

### 5.2 Dữ liệu thật đã dùng (8 nguồn, ~1,5 GB)

| Nguồn | Dùng để | Quy mô |
|---|---|---|
| Customer Invoices (ERP Mỹ) | T1 chính | ~50 nghìn hoá đơn |
| BPI 2019 (mua hàng châu Âu) | T1, **bài kiểm khắc nghiệt** | ~211 nghìn |
| SBA 7(a) (vay Mỹ) | T2 | ~638 nghìn khoản |
| Online Retail II | T4 doanh thu | 73 chuỗi tuần |
| Berka (ngân hàng Séc) | Giao dịch ngân hàng | 1.478 tài khoản |
| UK PPR | Tham chiếu hành vi trả chậm | 115 nghìn báo cáo |
| OxCGRT, WDI Việt Nam | Sốc vĩ mô (COVID...) | — |

**Bỏ có chủ đích:** Home Credit, SEC (cần đăng nhập/chấp nhận điều khoản).

### 5.3 Dữ liệu sinh: 67 thế giới, khoảng 7 triệu hoá đơn

Mỗi "thế giới" là một nhóm doanh nghiệp giả với hoá đơn, sao kê, chi phí, lời hứa, sốc vĩ mô — hiệu chỉnh theo Atradius, luật VN, Tết, COVID.

| Thế giới | Số công ty | Vai trò |
|---|---|---|
| `src` | 40 | **Nguồn**: nơi học và chọn mọi tham số |
| `tgt` | 14 | Đích đầu tiên. **Đã bị nhìn nhiều lần** |
| `tgt2` | 40 | Đích **niêm phong**, dùng một lần cho luồng cảnh báo (G13) |
| `tgt3` | 30 | Đích niêm phong, dùng một lần cho T9 v2 |
| `sens_uk`, `sens_coface` | — | Kiểm tra khi giả định "đuôi trả chậm" thay đổi |
| 12 `hc_*` | 12 mỗi cái | **Hard-case**: khách lớn chi phối, nhóm trả hộ, chiết khấu, ngoại tệ, sốc chuỗi cung ứng... |
| 20 `dr_*` | — | **Ngẫu nhiên hoá** tham số để mô hình không "thuộc lòng" một thế giới |
| 4 `big_*` | 150 mỗi cái | Quy mô lớn, tổng 3,5 triệu hoá đơn |

### 5.4 Chất lượng dữ liệu sinh: giống thật tới đâu?

Phép thử: huấn luyện một bộ phân loại "đây là thật hay sinh?" (C2ST). AUC = 1,0 là phân biệt hoàn hảo, 0,5 là không phân biệt được.

| Nhóm đặc trưng | AUC | Ý nghĩa |
|---|---|---|
| Gộp tất cả (số báo trước đây) | 0,96–0,997 | Trông rất tệ... |
| **Chỉ kỳ hạn thanh toán** | 0,89–0,96 | ...nhưng phần lớn do **khác biệt có chủ đích**: ta mô phỏng Việt Nam (45 ngày), bộ thật là Mỹ (15 ngày). Không nên sửa. |
| **Chỉ hành vi** | **0,67–0,79** | Phần có thể sửa. Gần ngưỡng mục tiêu 0,75 |

**Hạn chế lớn:** bộ thật dùng để so chỉ có **6 công ty**, nên khoảng tin cậy rất rộng (0,3–0,6 điểm AUC). Không đủ để biết phiên bản máy phát nào tốt hơn. Vì vậy **đã dừng chỉnh máy phát**.

---

## 6. Cách đo trung thực

Phần này giải thích vì sao dự án "chậm": ta cố tình **không cho phép tự lừa mình**.

### 6.1 Hình ảnh "đề thi niêm phong"

| Khái niệm | Hình ảnh đời thường |
|---|---|
| **Chọn tham số trên nguồn** | Học sinh luyện đề ở nhà (`src`) |
| **Bộ đích niêm phong** | Đề thi thật, giữ kín tới ngày thi (`tgt2`, `tgt3`) |
| **Đo một lần** | Chỉ được thi **một lần**. Điểm xấu cũng phải nhận |
| **Đăng ký trước** | **Ghi đáp án vào phong bì và nộp trước** khi mở đề (commit lên git trước khi sinh bộ đích) |
| **Khoảng tin cậy theo công ty** | Điểm kèm biên sai số, tính theo *công ty* (không theo từng hoá đơn, vì hoá đơn của cùng công ty không độc lập) |

### 6.2 Hệ quả

- Mỗi lần sửa mô hình xong, phải **sinh bộ đích mới** để đo lại. Đã dùng hết `tgt`, `tgt2`, `tgt3`; bộ kế tiếp là `tgt4`.
- Kết quả xấu **được ghi lại**, không giấu (ví dụ G13 trượt, lớp chặn T9 vô tác dụng).

### 6.3 Hai chỉ số hay gặp

- **Pinball loss**: sai số của dự báo *phân vị* (càng thấp càng tốt). Phạt nặng hơn khi dải lệch về phía nguy hiểm.
- **Cải thiện so với B1d (%)**: `(pinball B1d − pinball mô hình) / pinball B1d`. Dương = mô hình tốt hơn mốc đơn giản.
- **cov80**: tỉ lệ số dư thật nằm trong dải P10–P90. Lý tưởng gần **80%**. Cổng chấp nhận 75–85%.

---

## 7. Kết quả từng trạm

### 7.1 T1 trên dữ liệu thật (so với B1d)

| Bộ dữ liệu | Phương pháp | Cải thiện [CI 95%] | Đọc |
|---|---|---|---|
| Customer Invoices | DH-GBM thuần | +13,1% [8,3; 17,9] | Thắng |
| Customer Invoices | **BLEND** | **+14,4% [11,7; 17,4]** | Thắng, ổn định hơn |
| BPI 2019 | **DH-GBM thuần** | **−62,5% [−90,4; −37,4]** | **Thua nặng** |
| BPI 2019 | **BLEND** | +6,5% [2,1; 11,0] | Cứu được nhờ neo B1d |

> **Bài học BPI:** cùng một mô hình, trên bộ dữ liệu khác có thể thua hẳn. *Không bao giờ* dùng mô hình thuần mà không có BLEND và cầu dao.

### 7.2 Cầu dao tự ngắt (cổng thoái lui)

Quy tắc: nếu mô hình thua B1d hơn 5% trong **4 tuần liên tiếp** (xét 8 tuần gần nhất, chỉ dùng kết quả đã lộ diện), doanh nghiệp đó chuyển về B1d; quay lại sau 4 tuần ổn.

| Trường hợp | Không cầu dao | Có cầu dao |
|---|---|---|
| BPI, mô hình thuần | −62,5% | −22,3% (cắt 2/3 thiệt hại) |
| BPI, BLEND | +6,5% | +4,7% [2,4; 6,7] |
| Customer Invoices | +14,4% | +14,4% (không kích hoạt) |
| Dữ liệu sinh | gần như không kích hoạt | tốn < 1 điểm |

**Nhớ:** BLEND là **lớp bảo vệ chính**, cầu dao là **lưới an toàn thứ hai**. Cầu dao phải chờ kết quả lộ diện nên không cứu hết.

### 7.3 T1 trên bộ đích niêm phong `tgt2`

Luồng triển khai thật (tinh chỉnh 12 tháng dữ liệu của doanh nghiệp, `w` chọn trên cửa sổ hiệu chỉnh riêng): **+47,5% [30,9; 60,7]** so với B1d. Hard-case `retention` +85,7%, `supply_shock` +46,2%.

*Lưu ý:* dữ liệu sinh "dễ" hơn dữ liệu thật vì hành vi sinh có quy luật rõ. Đừng kỳ vọng +47% ngoài đời.

### 7.4 T6 — dải số dư

| Phiên bản | cov80 tuần 1–4 / 5–13 trên `tgt2` | Đánh giá |
|---|---|---|
| Copula-t gốc | 0,62 / 0,72 | **Hẹp quá** (tự tin quá mức) |
| **Copula-t + ACI** | **0,77 / 0,77** (`tgt`: 0,75 / 0,77) | **Đúng khoảng 75–85%** |

⇒ Dải công bố trong dịch vụ giờ là **copula-t + ACI**, với trạng thái ACI lưu theo từng doanh nghiệp. ACI cần khoảng **8 tuần** số dư lộ diện mới đáng tin; trước đó dashboard hiện cảnh báo.

### 7.5 G13 — cảnh báo thiếu tiền

Cảnh báo = khi xác suất thiếu hụt vượt ngưỡng, báo trước ≥ 4 tuần. Chính sách: hiệu chỉnh isotonic, ngưỡng τ = 0,30, chọn **chỉ trên nguồn** rồi đóng băng. Cổng cần báo giả ≤ 1 lần/công ty-năm.

| Bộ đánh giá | Nhãn thanh toán | Phát hiện ≥4 tuần | Báo giả/công ty-năm | Kết quả |
|---|---|---|---|---|
| `tgt` (cổng chính thức) | T9 ước lượng | 0,94 | **2,08** | Trượt |
| `tgt` | thật | 0,81 | **0,57** | Đạt điểm ước lượng |
| `tgt2` niêm phong | thật | 0,75 | 0,75 | Đạt điểm ước lượng |
| **`tgt3` niêm phong** | T9 v2 (phủ 59,5%) | 0,85 | **2,71** | Trượt |
| `tgt3` | T9 cũ (phủ 69,8%) | 0,83 | 2,41 | Trượt |
| `tgt3` | thật (phủ 100%) | 0,80 | **0,90** | Đạt điểm ước lượng |
| `tgt3` | **T9 v2 + nhãn thật chỉ cho phần thiếu** | 0,80 | **0,87** | Đạt điểm ước lượng |
| `tgt3` | T9 v2 + nhãn thật cho 50% / 80% phần thiếu | 0,83 / 0,80 | 2,07 / 1,37 | Trượt |
| **`tgt5` niêm phong** | T9 v2 (phủ 60,6%) | 0,90 | 2,01 | Trượt |
| **`tgt5` niêm phong** | **T9 v2 + nhãn mềm (phủ 94,8%)** | 0,90 | **0,77** | **Đạt sát ngưỡng** (20 sự kiện, CI trên 1,17) |
| `tgt3` (lặp lại, không niêm phong) | T9 v2 + nhãn mềm (phủ 93,8%) | 0,80 | **1,81** | **Trượt**, nhưng giảm 33% so với 2,71 |
| **`tgt6` niêm phong** | T9 v2 + **kế toán duyệt ~3 giao dịch/DN/tuần** + nhãn mềm | 0,81 | **0,97** | **Đạt sát ngưỡng** (nhãn thật: 0,94) |
| `tgt3` (lặp lại) | T9 v2 + duyệt ~3/DN/tuần + nhãn mềm | 0,83 | **1,37** | **Trượt** (nhãn thật: 0,90) |

**Cách đọc, theo từng bước:**
1. Có nhãn thật thì chính sách cảnh báo **đạt** (trên cả 3 bộ đích). Vậy chính sách không phải vấn đề.
2. Với nhãn do T9 ước lượng thì báo giả gấp 3 lần. Vậy vấn đề nằm ở nhãn.
3. **Nhãn chính xác hơn không giúp** (T9 v2 chính xác ngày hơn nhiều nhưng báo giả không giảm). Báo giả đi theo **độ phủ**: càng nhiều hoá đơn đã trả được gán nhãn thì càng ít báo giả.
4. **Thí nghiệm quyết định:** giữ nguyên nhãn T9 v2, chỉ điền nhãn thật vào chỗ thiếu ⇒ báo giả về 0,87. Vậy thiếu nhãn chiếm khoảng 3/4 báo giả.

**Hình ảnh dễ nhớ:** hoá đơn đã trả mà không có nhãn giống như tiền đã vào ví nhưng sổ vẫn ghi "chưa thu". Hệ thống tưởng còn thiếu tiền nên báo động nhầm.

**Nhãn mềm là gì?** Khi biết *khách nào* chuyển tiền (mô hình gán khách rất chắc) nhưng không biết *hoá đơn nào*, hệ thống phân bổ phần tiền dư cho các hoá đơn chưa có nhãn của khách đó, theo thứ tự hạn sớm nhất. Ngày nhãn có thể lệch (khoảng 1/3 nhãn mềm sai hơn 14 ngày) nhưng độ phủ nhãn tăng từ khoảng 60% lên 94%.

**Hàng chờ duyệt thông minh (24/10):** kế toán chỉ duyệt các giao dịch còn nhiều tiền chưa giải thích nhất, khoảng 3 lượt/doanh nghiệp/tuần. Giảm thêm 19–24% báo giả so với chỉ nhãn mềm. Đạt sát trên `tgt6`, trượt trên `tgt3` ⇒ theo quy tắc dừng đã ghi trước, **dừng tối ưu G13 trên dữ liệu sinh**. Phát hiện kèm theo: ngay cả nhãn thật cũng cho báo giả 0,90–0,94 ở hai thế giới khó, tức tiêu chí ≤ 1 nằm sát trần của mô hình dòng tiền.

**Kết luận thận trọng về nhãn mềm:** đúng hướng ở **cả hai** thế giới (giảm 33–62% báo giả, Brier ngang nhãn thật), nhưng chỉ **1/2 thế giới đạt cổng**. Vì vậy G13 vẫn chưa thể coi là đã giải một cách vững. Phải đánh dấu nhãn mềm là "ước lượng" trong sản phẩm.

Đã thử và loại: gộp các đợt cảnh báo bị tách nhỏ (không đổi được đánh đổi giữa phát hiện và báo giả).

### 7.6 T9 — ghép sao kê

| Phiên bản | Precision | Recall | F1 | Sai số ngày trả |
|---|---|---|---|---|
| `tgt3`, cấu hình cũ | 0,899 | 0,603 | 0,722 | 2,53 ngày |
| `tgt3`, **T9 v2** | **0,962** | 0,557 | 0,706 | **0,82 ngày** |
| Cổng yêu cầu | ≥ 0,95 | — | ≥ 0,80 | ≤ 3 |

**Cách hiểu precision/recall:** precision = "trong số liên kết hệ thống tự làm, bao nhiêu % đúng". Recall = "trong tất cả khoản tiền, hệ thống ghép được bao nhiêu %".

**T9 v2 làm gì:** chỉ tự động ghép tổ hợp **tối đa 2 hoá đơn**; tổ hợp lớn hơn vào hàng chờ cho người duyệt; tắt nhánh đoán theo xác suất (chỉ đúng 54% trên nguồn).
**Kết quả:** liên kết tự động **đáng tin hơn nhiều** và ngày trả chính xác hơn 3 lần, nhưng ghép được ít hơn (recall giảm) nên F1 chưa đạt.

**Đã thử và loại:**
- Lớp chặn theo độ tin cậy: vô tác dụng vì mô hình gán khách **tự tin quá mức** (trung vị 1,0 cả khi sai).
- Phân bổ tiền theo thứ tự hạn (FIFO) cho khách trả từng phần: chỉ đúng ~20%.

**Điểm nghẽn thật:** nhiều khoản tiền **không có số hoá đơn trong nội dung** nên không thể xác định được. Đòn bẩy lớn nhất nằm *ngoài mô hình*: khuyến khích khách ghi số hoá đơn khi chuyển khoản.

**Thử lần 3 (T9 v3 trên bộ `tgt4`, do agent kia làm):** precision 0,968, recall 0,491, F1 0,651. Vẫn chưa đạt: chỉnh quy tắc không nâng được recall.

**Liên hệ quan trọng:** vì G13 cần *độ phủ nhãn* (mục 7.5) và G15 cần F1, hai cổng này cùng cần T9 ghép được nhiều hơn mà vẫn chính xác.

---

## 8. Bảng 18 cổng

Cổng = điều kiện nghiệm thu đã **viết trước** và **không đổi** sau khi xem kết quả.

### 8.1 Tình trạng: 9 đạt · 8 trượt · 1 ngoài phạm vi

| Cổng | Kiểm cái gì | Trạng thái |
|---|---|---|
| G1 | T1 giảm WAPE ≥ 30% ở hai mốc thời gian | ✅ Đạt |
| G2 | T1 tốt hơn B1 theo IBS | ✅ Đạt |
| G3 | Khoảng dự báo T1 phủ 75–85% | ❌ cov80 0,867 / 0,844 (hơi rộng); agent kia thử Mondrian theo nhóm đáo hạn còn xấu hơn |
| G4 | Xác suất 4 tuần hiệu chỉnh tốt (ECE ≤ 0,05) | ❌ |
| G5 | T1 thắng B1 ≥ 10% trên dữ liệu thật | ✅ Đạt (giao thức v2) |
| G6 | T1 không thua B1d trên cả hai bộ thật | ✅ Đạt (nhờ BLEND) |
| G7 | Tinh chỉnh 12 tháng cải thiện ≥ 10% | ❌ thử tinh chỉnh có dừng sớm vẫn không cải thiện (một biến thể còn −8,5%) |
| G8 | Xác suất vỡ nợ trên SBA thật (ECE ≤ 0,02, tỉ lệ 0,8–1,25) | ❌ ECE 0,021; tỉ lệ 0,74 (đã thử hiệu chỉnh hằng năm, vẫn trượt vì năm 2022 vỡ nợ tăng thật gấp 4–5 lần) |
| G9 | T4 doanh thu thắng mốc | ✅ Đạt |
| G10 | T4 thắng trên dữ liệu thật | ✅ Đạt |
| G11 | Quy tắc được **chuyên gia** xác minh | ⏸ **Ngoài phạm vi** (cần chuyên gia) |
| G12 | Dải số dư E2E cov80 75–85% | ✅ Đạt |
| G13 | Cảnh báo thiếu tiền | ❌ cổng chính thức (`tgt` 2,08; `tgt3` 2,71). Với nhãn mềm: ✔ `tgt5` (0,77, sát ngưỡng) nhưng ❌ `tgt3` (1,81). Đạt khi có nhãn thật (0,33–0,90) |
| G14 | Phát hiện đổi hành vi (≥ 0,5 phát hiện, ≤ 0,5 báo giả) | ❌ cổng cũ. ✔ bản mới (CUSUM + nghỉ 60 ngày) trên `tgt2`+`tgt3`: 0,576 / 0,431, đạt điểm ước lượng, **không có CI, sát ngưỡng** |
| G15 | T9 ghép sao kê (F1 ≥ 0,8, precision ≥ 0,95...) | ❌ F1 0,706 |
| G16 | T0 phát hiện lỗi dữ liệu chèn sẵn | ✅ Đạt |
| G17 | Lời hứa giảm MAE ≥ 10% | ❌ cổng cũ (nhiễu −7,6%). ✔ bản mới thêm 6 đặc trưng: sạch −22,9%, nhiễu −10,8% [8,2; 13,0], **sát ngưỡng**, chưa tách đóng góp từng đặc trưng |
| G18 | T9 thu hẹp ≥ 50% khoảng cách với nhãn thật | ✅ Đạt |

### 8.2 Hai trạng thái pilot (đừng nhầm)

| Trạng thái | Giá trị | Vì sao |
|---|---|---|
| **Pilot THẬT** | **NO-GO** | Còn G11, G13, G15 |
| **Giai đoạn chỉ dữ liệu sinh** (bỏ G11) | **Chưa đạt, còn thiếu: G13, G15** (cộng G3, G4, G7, G8 trượt) | G14 và G17 có bản mới đạt sát ngưỡng |

> **G11 không được tính là "đạt".** Nó chỉ tạm ra khỏi phạm vi vì không có chuyên gia. Pilot thật vẫn đòi nó.

---

## 9. Làm sai và bài học

Minh bạch về sai sót giúp bạn biết **khi nào nên nghi ngờ** một con số.

| # | Chuyện gì xảy ra | Hệ quả | Bài học |
|---|---|---|---|
| 1 | **Lỗi `expand` trong T1:** giữ lại sự kiện trong tuần quan sát dở nhưng bỏ không-sự-kiện → xác suất trả bị thổi phồng (BPI: 0,99) | Mọi kết quả hazard trước 20/10 phải **chạy lại** | Chỉ tin CSV có hậu tố `fullweek` |
| 2 | Mô hình tuyến tính ngoại suy vô lý (lệch 17 độ lệch chuẩn) | MAE 105 ngày | Đã kẹp giá trị cực đoan |
| 3 | Báo "AUC 0,996 = máy phát tệ" | Thực ra phần lớn là khác biệt **có chủ đích** (kỳ hạn VN vs Mỹ) | Phải tách đặc trưng thiết kế khỏi hành vi |
| 4 | Báo "T9 recall 0,47" | Đó là số của **quy tắc R1**, không phải phương pháp triển khai | Đã đính chính; luôn ghi rõ *phương pháp nào* |
| 5 | Hai job nặng chạy chồng nhau | RAM cạn, **cả hai chết**, mất vài giờ | Giờ chạy tuần tự, có kiểm tra RAM |
| 6 | Ước lượng thời gian lệch (có lúc quá lạc quan, có lúc quá bi quan) | — | Đừng tin ước lượng giờ của tôi |
| 7 | Ý tưởng nào cũng có thể sai: lớp chặn T9, FIFO, lấp khoảng trống G13, khách mua lẻ trong máy phát | Ghi lại, không dùng | Kết quả âm tính cũng là kết quả |
| 8 | Nói "khoảng nghỉ G14 không làm mất phát hiện" và "nhãn SBA 2022 chưa chín" | Cả hai **sai** khi đo (nhóm cũ mất 1 khách; dữ liệu SBA tới 2026 nên nhãn đã chín) | Giả thuyết phải được thử, và sai thì sửa công khai trong tài liệu |
| 9 | Kỳ vọng "T9 chính xác hơn thì G13 tốt hơn" | Sai: T9 v2 chính xác hơn nhưng báo giả không giảm; nguyên nhân là **độ phủ nhãn** (đã kiểm bằng ablation) | Hỏi "thiếu gì" trước khi hỏi "sai ở đâu" |

---

## 10. Tin được tới đâu

| Khẳng định | Mức tin cậy | Vì sao |
|---|---|---|
| Hệ thống chạy trọn vẹn, tái lập được | **Cao** | 351 kiểm thử đạt; mọi kết quả sinh lại được từ mã |
| Mô hình + BLEND không thua mốc đơn giản trên dữ liệu thật nước ngoài | **Trung bình–cao** | 2 bộ thật, CI theo cụm; nhưng chỉ 2 bộ |
| Dải số dư (copula-t + ACI) có độ phủ đúng | **Trung bình** | Đúng trên 2 bộ đích sinh; chưa thấy dữ liệu thật |
| Cảnh báo thiếu tiền dùng được | **Thấp–trung bình** | Phụ thuộc T9; CI chạm ngưỡng; chỉ làm *gợi ý có người duyệt* |
| Dữ liệu sinh giống SME Việt Nam | **Không kiểm chứng được** | Bộ thật tham chiếu chỉ 6 công ty |
| **Hiệu năng trên doanh nghiệp Việt Nam thật** | **Chưa biết** | **Chưa có một dữ liệu thật nào** |

**Nguyên tắc đọc số:** kết quả trên `tgt2`/`tgt3` (niêm phong, nhãn thật) là **cận trên**; kết quả E2E với nhãn T9 ước lượng gần thực tế hơn; kết quả trên `tgt` (đã bị nhìn) chỉ để so sánh lịch sử.

**Cam kết duy nhất hợp lệ với khách hàng:**
> *"Không tệ hơn cách đoán đơn giản (B1d), và tự động quay về cách đó nếu tệ hơn."*

Không được hứa "chính xác X%" dựa trên dữ liệu sinh.

---

## 11. Triển khai an toàn

### 11.1 Bốn bậc

| Bậc | Việc | Điều kiện lên bậc kế |
|---|---|---|
| **0. Chạy bóng** | Chạy song song, **chỉ ghi dự báo**, không ai hành động | ≥ 8 tuần; BLEND không thua B1d; dải phủ 75–85% trên dữ liệu thật của họ |
| 1. Gợi ý | Hiện dự báo cho kế toán, ghi nhận có làm theo không | ≥ 1 quý; sai số tuần 1–4 giảm so với B1d trên dữ liệu thật |
| 2. Cảnh báo có duyệt | Cảnh báo thiếu tiền 13 tuần, người duyệt | Phát hiện ≥ 70% sự kiện thật, báo giả ≤ 1/năm, cần ≥ 5 sự kiện thật |
| 3. Tự động | — | Cần ≥ 2 mùa pilot thật |

**Quyết định hiện tại: GO bậc 0; NO-GO bậc 1–3.**

### 11.2 Năm luật an toàn (nhớ bằng "N-C-D-M-D")

1. **N**eo mốc đơn giản: luôn BLEND với B1d.
2. **C**ầu dao: thua 4 tuần liên tiếp → tự về B1d.
3. **D**ải hiệu chỉnh tại chỗ (ACI): chỉ công bố độ phủ khi đủ 8 tuần số dư lộ diện.
4. **M**ới vào thì thận trọng: doanh nghiệp < 6 tháng lịch sử chỉ dùng B1d + khoảng rộng.
5. **D**uyệt người: mọi cảnh báo thiếu tiền có người xem cho tới khi có ≥ 2 mùa dữ liệu thật.

---

## 12. Tình hình hiện tại

### 12.1 Tỉ lệ hoàn thành (nói thẳng)

| Phần | Tỉ lệ |
|---|---|
| Mã và tài liệu | ~85–90% |
| Cổng đạt (tất cả) | 9/18 (50%) |
| Cổng bắt buộc cho pilot thật | 6/9 (67%) |
| **Tổng quan "hệ thống chạy được và đạt chuẩn trên dữ liệu sinh/thật nước ngoài"** | **~60%** |
| **Kiểm chứng trên doanh nghiệp Việt Nam thật** | **0%** |

### 12.2 Dòng thời gian ngắn

| Ngày | Việc |
|---|---|
| 14–16/10 | Xây dữ liệu và mô hình ban đầu; viết bộ tài liệu 5 phần; đẩy lên `agent1-Khanh` |
| 20/10 | Phát hiện và sửa lỗi `expand` ⇒ phải chạy lại cả chuỗi |
| 21/10 | Chạy lại chuỗi; G13 chính sách mới; sinh `tgt2`; cầu dao; dịch vụ dùng ACI |
| 22/10 | T9 v2 với `tgt3`; cầu dao trên dữ liệu thật; phát hiện G13 phụ thuộc T9; chuyển sang phạm vi "dữ liệu sinh"; G14 (khoảng nghỉ) và G8 (hiệu chỉnh hằng năm) đo xong; agent kia bắt đầu sprint 6 (T9 v3, G3/G4, G7) |

### 12.3 Việc tiếp theo

**Đã làm xong trong đợt cuối (22/10):** G14 (khoảng nghỉ), G8 (hiệu chỉnh hằng năm, không đạt vì năm 2022 vỡ nợ tăng thật), G17 (6 đặc trưng mới), G13 trên `tgt3` + ablation, sprint 6 của agent kia (G3/G4/G7 không đạt, T9 v3 chưa đạt).

**Còn lại, theo thứ tự đáng làm:**
1. **Tăng độ phủ nhãn T9 mà giữ precision.** Mở khoá đồng thời G13 và G15. Việc đầu tiên: đo *độ phủ tối thiểu đủ dùng* (ablation mới chỉ thử 100%; thử 70/80/90%) trước khi thiết kế thuật toán mới.
2. **G17:** tách đóng góp từng đặc trưng; kiểm trên bộ lời hứa nhiễu mới để cận dưới khoảng tin cậy vượt 10%.
3. **G14:** bootstrap khoảng tin cậy theo công ty trên bộ đích mới.
4. **G3, G4, G7:** hai sprint đã thử không thắng; cần ý tưởng khác (ví dụ ngừng đặt mục tiêu 75–85% nếu khoảng rộng hơn là chấp nhận được về mặt kinh doanh).
5. **G8:** đổi hướng sang phát hiện trôi tỉ lệ vỡ nợ gốc và cảnh báo, thay vì cam kết hiệu chỉnh (chủ dự án quyết).

### 12.4 Việc không giải bằng mã được

- Hiệu năng thật: cần **một doanh nghiệp cho chạy bóng** (dù chỉ 3–5 công ty nhỏ).
- G11: cần chuyên gia.
- Kiểm định "giống thật": cần bộ dữ liệu AR thật nhiều công ty.

### 12.5 Một lời khuyên chiến lược

Làm thêm vài ngày sẽ nâng số cổng đạt từ 9 lên khoảng 11–12. Nhưng **không** biến "đúng trên dữ liệu sinh" thành "đúng với doanh nghiệp thật". Bước có giá trị nhất không phải thêm cổng, mà là **tìm một doanh nghiệp để chạy bóng**.

---

## 13. Từ điển

| Thuật ngữ | Giải thích ngắn, dễ nhớ |
|---|---|
| **SME** | Doanh nghiệp nhỏ và vừa |
| **AR** | Công nợ phải thu (khách còn nợ mình) |
| **B1 / B1d** | Cách đoán đơn giản: trung vị / cả phân phối thói quen trả của khách |
| **Hazard** | Xác suất "trả trong tuần này, biết rằng đến giờ chưa trả" |
| **DH-GBM** | Mô hình hazard dùng LightGBM (cây quyết định tăng cường) |
| **BLEND** | Trộn mô hình với B1d theo trọng số `w` |
| **Pinball loss** | Sai số của dự báo phân vị; thấp hơn là tốt hơn |
| **CI 95%** | Khoảng tin cậy; nếu không chứa 0 thì cải thiện "thật" |
| **cov80** | Tỉ lệ giá trị thật nằm trong dải P10–P90 (lý tưởng ~80%) |
| **CQR** | Conformal Quantile Regression: chỉnh độ rộng khoảng dự báo |
| **ACI** | Conformal thích ứng: tự nới/thu dải theo kết quả đã lộ diện |
| **Copula-t** | Cách mô phỏng nhiều khách "cùng chậm" với đuôi rủi ro dày |
| **Monte Carlo** | Chạy hàng nghìn kịch bản ngẫu nhiên rồi lấy phân vị |
| **Domain adaptation** | Mô hình học ở miền này, dùng ở miền khác (Mỹ → Việt Nam, nguồn → đích) |
| **src / tgt** | Miền nguồn (học, chọn tham số) / miền đích (đo) |
| **Niêm phong** | Bộ đích chỉ được đo một lần, cấm chọn tham số trên đó |
| **Đăng ký trước** | Ghi tiêu chí vào git **trước** khi xem kết quả |
| **Precision / Recall / F1** | Đúng trong số đã ghép / ghép được trong tất cả / trung bình điều hoà của hai |
| **C2ST** | Phép thử "phân biệt dữ liệu thật và sinh"; AUC càng gần 0,5 càng giống |
| **Hard-case** | Tình huống khó chèn sẵn để thử độ bền |
| **E2E** | Từ đầu đến cuối: sao kê → ghép → dự báo → cảnh báo |
| **Out of scope** | Tạm ra khỏi phạm vi; **không** có nghĩa là đạt |
| **`fullweek`** | Hậu tố của CSV chạy sau khi sửa lỗi `expand`; chỉ tin các CSV này |

---

## 14. Bản đồ file

```
docs/
├── HIEU_DU_AN_AGENT1.md                ← bạn đang đọc
├── 00_INDEX.md                         tóm tắt một trang
├── 01_Business_Analyst/                vì sao sản phẩm tồn tại, ai trả tiền
├── 02_Data/                            dữ liệu thật, máy phát, hard-case; 10_realism_v2.md
├── 03_Evaluation/
│   ├── GATES_CURRENT.md                bảng cổng sinh tự động  (đọc đầu tiên)
│   ├── GO_NO_GO_SYNTHETIC_ONLY.md      quyết định triển khai   (đọc thứ hai)
│   ├── G13_ALERT_POLICY.md             cảnh báo thiếu tiền
│   ├── G15_T9_V2_PREREG.md             T9 v2, đăng ký trước + kết quả
│   └── T9_RECALL_DIAGNOSIS.md          vì sao T9 trượt
├── 04_AI_Methods/                      pipeline và mô hình từng trạm
└── 05_Coding_Agent_Plan/
    ├── NHAT_KY_SPRINT1_2026-10-20.md   nhật ký thực thi (mục 8–16 là mới nhất)
    └── PROMPT_GIAO_VIEC_2026-10-22.md  việc giao agent kế tiếp

outputs/   kết quả CSV (sinh ra bởi mã)     scripts/sprint5/   mã đợt gần nhất
agent1/    thư viện mô hình                 agent1_service/    API + dashboard
data/synthetic/  cấu hình thế giới sinh (dữ liệu parquet không đưa lên git)
```

**Git:** `https://github.com/Khanhhh239/Multi-Agent-Finance.git`, nhánh `agent1-Khanh`.

---

## Phụ lục — Năm câu để nhớ cả dự án

1. **Làm gì?** Dự báo *khi nào tiền về* và *khi nào có thể hết tiền* cho SME Việt Nam.
2. **Bằng gì?** Dây chuyền 6 trạm: kiểm dữ liệu → ghép sao kê → đoán ngày trả → dự báo doanh thu → mô phỏng số dư → gợi ý hành động.
3. **Đo thế nào?** Chọn tham số trên nguồn, đo **một lần** trên "đề thi niêm phong", tiêu chí **ghi trước**.
4. **Tới đâu?** 9/18 cổng; chạy được; **chưa thấy dữ liệu Việt Nam thật**.
5. **Làm gì tiếp?** Sửa T9 (mở khoá cảnh báo) → rồi tìm **một doanh nghiệp chạy bóng**.
