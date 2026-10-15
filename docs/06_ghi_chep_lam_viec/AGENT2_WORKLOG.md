# Nhật ký công việc — Agent 2 (Giám sát rủi ro / Phát hiện gian lận nội bộ SME Việt Nam)

Cập nhật liên tục. Mỗi mục: việc đã làm, kết quả đo được, quyết định, việc còn lại. Số liệu chỉ ghi khi đã chạy lại trong môi trường này.

## 0. Phạm vi và nguyên tắc (không lạc đề)
- Bài toán: gian lận **nội bộ** ở doanh nghiệp nhỏ và vừa Việt Nam (nhà cung cấp ma, chia nhỏ thanh toán, thanh toán trùng, tạm ứng, nhân sự ma, bút toán cuối kỳ, hóa đơn rủi ro). Ưu tiên: precision và ngân sách cảnh báo thấp, không phải recall tối đa.
- Dữ liệu ngoài như PaySim, Elliptic, BAF chỉ là gian lận bên ngoài hoặc rửa tiền (đã kết luận ở Phần 6/8), không dùng làm tiêu chí chính.
- Ràng buộc: không dùng nhãn test để chọn luật, trọng số hay ngưỡng; dữ liệu tổng hợp không được trình bày như bằng chứng về SME thật.

## 1. Tiếp nhận `zipp.zip` (2026-10-14)
- Người dùng nói `zip.zip`. Thực tế: `zip.zip` (39 KB, 13/08) là web app AI Studio không liên quan; `zipp.zip` (544 MB, tải 14/10) là dự án của bạn bạn. Tôi dùng `zipp.zip` (giả định ghi ở đây để người dùng xác nhận).
- Giải nén vào `agent2_fraud/friend_zipp/` (bản gốc, không sửa). Công việc của tôi nằm ngoài thư mục này.
- Nội dung: bộ sinh dữ liệu SME (`sme_fraud/generate.py`), kế toán TT133/TT200, 190 đặc trưng, Isolation Forest, bộ 31 luật A–F (`rules.py`), kiểm toán luật, hàng đợi hồ sơ + giao diện duyệt, 3 bộ dữ liệu v2 (100.000 quan sát, tỷ lệ gian lận 0,1%/0,3%/0,5%), 29 test.
- Môi trường: các bản Python hệ thống trên máy đã bị xoá (py launcher lỗi 0x80070003). Dùng Python 3.12 của runtime `.cache/codex-runtimes` để tạo venv `agent2_fraud/.venv`.

## 2. Đánh giá bộ dữ liệu và mã của bạn bạn (đã kiểm chứng bằng chạy lại)

**Tái lập:** 64 test gốc đều qua trong venv mới; engine luật chạy lại cho đúng số của họ (Rules AP 0,6026; Rules+Graph 0,6136; IF 0,0342; Rules+Graph+IF 0,4525 trên `sme_fraud_003`).

**Điểm tốt (giữ nguyên):** đặc trưng chỉ dùng quá khứ (có test chống rò rỉ), sổ cái TT133/TT200 cân bằng Nợ=Có, hàng đợi hồ sơ + SLA + nhật ký phản hồi có chuỗi hash, hard negatives, quy tắc "không đủ dữ liệu thì ghi not_evaluable".

**Lỗi/ý tưởng chưa ổn, đã đo được:**
1. **Bộ sinh dữ liệu để lộ nhãn qua nhà cung cấp:** cả 400 nhà cung cấp nền có cùng ngày onboard 01/01/2023, nên tuổi nhà cung cấp tự phân biệt gian lận (`vendor_tenure_log_days` là đặc trưng quan trọng thứ 2 của LightGBM). Tên 2.043 NCC cùng tiền tố nên rule E3 báo 100% dòng (12.625 FP). NCC được chọn đều ngẫu nhiên, số tiền không phụ thuộc NCC, không có mùa vụ/Tết.
2. **Đánh giá vòng tròn:** 31 luật được viết đúng theo 6 kịch bản mà bộ sinh chèn; chỉ 1 seed, 5 công ty gần giống nhau, một mức khó. Số 0,60 của luật vì thế không nói lên khả năng tổng quát.
3. **Chỉ thử Isolation Forest không giám sát** (AP 0,03) trên 190 đặc trưng gồm hàng trăm cột one-hot; chưa thử mô hình có giám sát dù có nhãn train, chưa thử ECOD/autoencoder/baseline theo thực thể.
4. **Ensemble 80% luật + 20% IF làm kết quả xấu đi** (AP 0,61 xuống 0,45): xếp hạng IF yếu đẩy dòng có hit luật ra khỏi đầu hàng đợi. Sửa bằng cổng (rules quyết định thứ tự, mô hình chỉ phá hòa).
5. **Ngưỡng vận hành 7 sinh ~900–1.000 cảnh báo trên 25.000 dòng test (3,6%)**, hơn 12 lần ngân sách 75; không phù hợp doanh nghiệp nhỏ.
6. Điểm luật rời rạc nhiều dòng bằng nhau; Precision@k phụ thuộc cách phá hòa.

## 3. World v3 (dữ liệu mới, đã sinh và kiểm tra)
- Mã: `agent2/world_v3.py` (kế thừa bộ sinh của bạn bạn, dùng lại kế toán/đặc trưng/luật), `agent2/validate_v3.py`.
- Sửa: NCC onboard rải 2018–2025 theo phân phối, độ phổ biến kiểu Zipf, số tiền theo NCC (có NCC tăng giá hợp lệ), tên NCC đa dạng + chi nhánh gần giống, mùa vụ (Tết, cuối tháng, tháng 11–12), 8 công ty quy mô 16–44 nhân sự.
- Thêm: 3 mức khó (dễ/vừa/khó) cho 6 họ gốc; 3 họ **không luật nào viết sẵn**: `kickback_overpricing` (cặp lập–duyệt thông đồng, giá cao 10–70%), `expense_padding` (chi tiền mặt sát hạn mức tự duyệt), `payroll_padding` (nâng lương một nhân viên); 4 loại mồi hợp lệ mới: thưởng Tết, thưởng cuối năm, tăng giá hợp lệ, mua dồn hợp lệ.
- Phát hiện khi kiểm tra: lỗi "tiền thuê định kỳ trả cho NCC chưa tồn tại" (validator bắt được, đã sửa); tuổi NCC vẫn tách gian lận (AUC 0,28) vì NCC vỏ mới lập là dấu hiệu thật, nên chuyển 40–70% ca vừa/khó sang NCC cũ ngủ đông.
- 5 bộ: `work/data/v3_s101..s105`, mỗi bộ 100.000 dòng, 300 gian lận (0,3%), 8 công ty, 36 giây/bộ.

## 4. Benchmark đầu tiên (seed 101, tập test, 75 gian lận)
Ghi chú đọc: B1/B3 = ngân sách 1/3 cảnh báo mỗi công ty mỗi tuần; "case" = tỷ lệ vụ có ít nhất một dòng bị cảnh báo.

| Phương pháp | AP | P@B3 | Recall@B3 | Case@B3 |
|---|---:|---:|---:|---:|
| Rules (của bạn bạn) | 0,243 | 4% | 35% | 49% |
| Rules+Graph | 0,251 | 5% | 43% | 53% |
| IF 190 đặc trưng (baseline của họ) | 0,018 | 1% | 8% | 12% |
| ECOD / HBOS | 0,006 | 0% | 3% | 4% |
| Autoencoder | 0,063 | 4% | 36% | 49% |
| Ensemble 80/20 của họ | 0,160 | 4% | 33% | 49% |
| LightGBM có giám sát, 190 đặc trưng | 0,538 | 9% | 76% | 92% |
| LightGBM + đặc trưng thực thể + hit luật | 0,768 | 10% | 87% | 96% |

(Tỷ lệ gian lận cơ sở 0,3% nên AP ngẫu nhiên = 0,003.)

**Ba kết luận đo được:**
1. Trên thế giới khó hơn, **AP của bộ luật rơi từ 0,60 xuống 0,25**: số cũ chủ yếu do vòng tròn. Luật 0% với 3 họ mới (expense_padding, kickback, payroll_padding) và chỉ 16% với ca khó.
2. **Mô hình có giám sát trong cùng phân phối rất mạnh (AP 0,77) nhưng không chuyển giao được:** khi bỏ một họ khỏi huấn luyện, AP trên họ đó về ~0 (leave-family-out), dù qua công ty lạ thì còn tốt (AP 0,64). Vậy mô hình học thuộc mẫu kịch bản, không học "gian lận". Không được trình bày AP 0,77 như năng lực thực.
3. Phương pháp không giám sát chuẩn (IF, ECOD, HBOS) gần như ngẫu nhiên; autoencoder khá hơn (AP 0,063) nhưng báo nhầm 19% ca hợp lệ giống gian lận.

Mã: `agent2/{data,feats,methods,metrics,bench}.py`. Kết quả thô: `work/results/try1/`.

## 5. Dữ liệu ngoài đã tải và đo (đã được người dùng yêu cầu "crawl dữ liệu từ các bài")
| Nguồn | Tệp | Kích thước | Giấy phép | Kiểm tra |
|---|---|---|---|---|
| DFKI General Ledger (Gronewald và cộng sự, Data in Brief 2026) | `external/dfki_gl/journal_entries_4203.csv` | 31,1 MB | CC BY 4.0 | MD5 khớp Zenodo (d7659d06…); 256.232 dòng, 102.429 bút toán, 850 bất thường chèn (0,83%), 6 người dùng, 2023–2024 |
| ERP Fraud Data (Tritscher và cộng sự, Univ. Würzburg) | `external/erp_fraud/erp_fraud_data.zip` (190 MB), chỉ giải nén `joint/*.csv` | 199,6 MB | trang gốc không nêu giấy phép | 5 lần chạy ERPsim/SAP, nhãn từng dòng, 12 kịch bản; không chạy mã hay notebook nào |
Không tải: PaySim/BankSim/BAF/Elliptic (gian lận bên ngoài/rửa tiền, ngoài phạm vi Agent 2, đã kết luận ở Phần 6 và 8), BPI 2019/2020 (không nhãn, lược đồ khác; chỉ hữu ích để đếm cảnh báo trên 1.000 giao dịch, để lại).

**Kết quả trên dữ liệu ngoài (`agent2/external.py`):**
- DFKI (test = nửa cuối 2024, 1 nhãn = 1 bút toán): danh sách phép thử bút toán (JET) tự nó chỉ đạt AP 0,083; ECOD 0,097; Isolation Forest 0,064; autoencoder 0,122; IF + cờ JET 0,190; LightGBM có giám sát 0,80–0,85 (nhưng nhãn được chèn trong danh sách JET nên đây là vòng tròn). ROC-AUC 0,85–0,99 trong khi AP thấp: **ROC-AUC không dùng được khi tỷ lệ dương 0,8%**.
- ERP Fraud Data (huấn luyện không giám sát chỉ trên 2 lần chạy bình thường): AP của ECOD 0,495/0,059/0,147, IF 0,459/0,050/0,117, autoencoder 0,144/0,147/0,212 cho fraud_1/2/3. Không phương pháp nào thắng ổn định (khớp kết luận ADBench). Có giám sát từ các lần chạy khác: 0,556/0,249/0,397; bỏ một kịch bản: Invoice Kickback AP 0,00–0,05 (khớp việc "mua đắt" khó thấy từ sổ cái).

## 6. Vòng phản hồi (mô phỏng, `agent2/feedback_sim.py`, 52 tuần triển khai, ngân sách 3 cảnh báo/công ty/tuần)
- Seed 202, lưới lr × trọng số dương × nhiễu của người duyệt. Chưa học (static): 60 dòng gian lận được cảnh báo.
- "Nới ngưỡng theo tín hiệu" (thiết kế tham khảo): gần như không đổi (50 so với 49 trên seed 201).
- Học lại trọng số kiểu AAD (lr 0,3, trọng số dương 3): 84–88 dòng khi người duyệt đúng; 76 khi sai 15%; **47–48 (thấp hơn không học) khi sai 30%**. Nhiễu làm tổn hại vì ~95% cảnh báo vốn là báo sai, nên 15–30% đảo nhãn tạo ra nhiều "gian lận giả" hơn gian lận thật.
- Làm mịn nhãn không cứu được. Khuyến nghị thiết kế: nhãn dương cần hai người xác nhận hoặc bằng chứng gắn kèm; tách "không đủ thông tin" khỏi "báo sai"; giữ mẫu kiểm toán đột xuất; kiểm tra bản học lại trên mẫu đột xuất trước khi bật.

## 7. Đường ống end-to-end và kiểm thử
- `python -m agent2.pipeline --data DIR --out DIR [--learned model.joblib] [--fdr q]`: nạp → đặc trưng quá khứ → 31 luật + đồ thị → lệch so với lịch sử từng thực thể → (tuỳ chọn) bộ xếp hạng học trước → hợp nhất theo xếp hạng (lấy max) → ngân sách cảnh báo (+ sàn conformal/BH) → hồ sơ theo thực thể kèm lý do tiếng Việt, mức ưu tiên và hành động → `cases.csv`, `case_queue.csv` (cột tương thích công cụ của bạn bạn), `report.json`.
- Thử thật trên seed 205: 1.272 cảnh báo dòng → 952 hồ sơ; Rules AP 0,254, EntityDeviation 0,011; lý do tiếng Việt có mặt cho từng hồ sơ. Phát hiện: mức ưu tiên đang suy ra từ thứ hạng điểm nên các luật nhiễu (A5, C1, E3) đẩy hồ sơ lên "cao nhất". Sẽ sửa bằng trọng số luật học trước + ưu tiên theo xác suất ước lượng.
- 11 test mới (`tests_agent2/`), gồm kiểm tra tính nhân quả của đặc trưng (cắt dữ liệu tương lai thì đặc trưng quá khứ không đổi), ngân sách tuần, p-giá trị conformal hợp lệ, pickle mô hình, hard trigger không bị hạ.

## 8. Kết quả benchmark 5 seed (thế giới v3, `work/results/bench_w3/summary.md`)
Giao thức theo thời gian (huấn luyện 2024, kiểm thử nửa cuối 2025, 75 gian lận mỗi seed, ngân sách B3 = 3 cảnh báo/công ty/tuần ≈ 26 cảnh báo/1000 dòng). Trung bình ± độ lệch chuẩn qua 5 seed:
| Phương pháp | Chế độ | AP | Recall@B3 | Vụ tìm thấy | Báo nhầm ca hợp lệ giống gian lận |
|---|:-:|---:|---:|---:|---:|
| 31 luật (bạn bạn) | R | 0,240 ± 0,019 | 30,9% | 43% | 2,9% |
| Isolation Forest 190 đặc trưng (baseline của họ) | U | 0,021 ± 0,013 | 9,9% | 15% | 13,1% |
| ECOD / HBOS | U | 0,005 / 0,004 | 5% / 4% | 4–5% | 5% |
| Autoencoder | U | 0,065 ± 0,020 | 32,8% | 46% | 20,3% |
| Lệch so với lịch sử từng thực thể (mới) | U | 0,012 ± 0,002 | 16,5% | 11% | 7,8% |
| Trọng số luật học lại | S | 0,387 ± 0,019 | 47,5% | 64% | 3,7% |
| LightGBM 190 đặc trưng | S | 0,633 ± 0,046 | 74,9% | 87% | 11,9% |
| LightGBM + đặc trưng thực thể + hit luật | S | 0,817 ± 0,022 | 88,8% | 95% | 16,1% |

Họ gian lận chưa thấy khi huấn luyện (leave-family-out, recall@B3, TB 9 họ): LightGBM thuần 16%; LightGBM + luật + thực thể 51%; luật 34%; lệch thực thể 19% (nhưng 80% cho kickback và 82% cho nâng lương); hợp nhất lấy max(luật, thực thể) 43%; max(L3, luật, thực thể) 58%.
Công ty chưa thấy (cùng thế giới): LightGBM đầy đủ AP 0,78, recall 86%.

## 9. Mô hình "chồng bằng chứng đã hiệu chỉnh" (CES) và phân khe thăm dò
- CES = trọng số luật học trước (leave-one-world-out) + điểm đuôi 12 bộ phát hiện lệch thực thể, 13 trọng số + 1 hằng số, huấn luyện trên các thế giới khác; chính quy hoá L2 quanh một tiên nghiệm đơn điệu (độ lệch lớn không bao giờ an toàn hơn). Trọng số đọc được: luật học 1,04; lương lệch 0,62; tiền mặt tự duyệt sát hạn mức 0,77; thiếu chứng từ lặp 0,45.
- Chéo thế giới (huấn luyện trên 4 thế giới, kiểm thử thế giới thứ 5): CES AP 0,51 (so với luật 0,25), recall@B3 72%, báo nhầm ca giống gian lận 6,2%.
- Vấn đề: với họ gian lận chưa thấy CES chỉ đạt recall 24% (bộ phát hiện chưa từng giúp bị trọng số hoá về ~0). Giải pháp thiết kế: **mỗi công ty-tuần dành khe cho kênh "mới lạ" không học** (hợp nhất max của luật và lệch thực thể). Kết quả: CES 2+1 (2 khe CES + 1 khe mới lạ): 68% trong phân phối, 32% họ chưa thấy; CES 1+2: 59% / 37%; chỉ kênh mới lạ: 38% / 40%.
- **Cấu hình đóng băng trước khi chạy tập niêm phong (2026-10-14):** hồ sơ mặc định "chính xác" = CES 2+1 ở B3 (hoặc CES 1+1 ở B2, CES ở B1); hồ sơ "phủ rộng" = L3 2+1; khởi đầu lạnh = kênh mới lạ. Tiêu chí chọn đặt trước: trung bình (recall trong phân phối, recall họ chưa thấy) với ràng buộc báo nhầm ca hợp lệ giống gian lận ≤ 10% → CES 2+1 thắng; L3 2+1 điểm cao hơn (0,69 so với 0,50) nhưng báo nhầm 12,6%.
- Tập niêm phong: `work/data/sealed_s901..903` (3 thế giới, 12 họ gồm 3 họ mới `price_creep`, `off_cycle_payroll`, `vendor_burst`, và mồi `legit_offcycle_payroll`), chạy đúng một lần.
- Lỗi tìm thấy khi sinh tập niêm phong: thanh toán của NCC ma có thể vượt cửa sổ thời gian (`9 ngày × j` không bị chặn). Đã sửa (không đổi RNG); các bộ dev vẫn hợp lệ.

## 10. Kết quả tập niêm phong (chạy đúng một lần, 2026-10-14, cấu hình đã đóng băng ở mục 9)
Trung bình 3 thế giới, ngân sách B3: luật tay recall 28,9%; kênh mới lạ 31,9%; CES 2+1 53,3% (họ mới 17,5%, báo nhầm ca giống gian lận 7,0%); LightGBM 2+1 83,3% (họ mới 58,7%, báo nhầm 10,9%). B1: CES precision 16,5%, LightGBM 27,2%. Chi tiết và cách diễn giải trong [AGENT2_REPORT_VI.md](AGENT2_REPORT_VI.md), mục 5.4. Hai điều cần nhớ: tiêu chí đặt trước chọn CES nhưng LightGBM thắng về recall; phần thắng của LightGBM một phần do bộ sinh chia sẻ cơ chế (lương luôn ngày 28 khiến `off_cycle_payroll` dễ).

## 11. Sửa trong bản làm việc của bạn bạn (`sme_fraud/`)
- `run_rules.py`: thêm biến thể "Rules+Graph gated by IF" (điểm luật + 0,5 × xếp hạng IF). Trên `sme_fraud_003` của chính họ: AP 0,665, so với 0,4525 của ensemble 80/20 và 0,6136 của Rules+Graph. 64 test gốc vẫn qua. Các tệp còn lại giữ nguyên; lỗi của bộ sinh được xử lý bằng lớp kế thừa `agent2/world_v3.py` thay vì sửa trực tiếp, để tái lập được số liệu cũ.

## 12. Đã bàn giao
- Mã: `agent2/` (15 test mới, `tests_agent2/`), README, báo cáo, nhật ký này, thư mục `results/` (JSON/CSV, ví dụ chạy `results/example_run_precision/`), trang rà soát `review.html` cho người không chuyên (ngoại tuyến, không gửi dữ liệu đi).
- Chưa làm / để mở: nối `review.html` với `review_ui/` của bạn bạn; các luật còn mở A3, A4, A5, B1, B3; hình thức phản hồi hai người xác nhận; khai thác BPI 2019/2020 để đếm cảnh báo trên 1.000 giao dịch; kiểm tra pháp lý Nghị định 13/2023.
- Cần bạn xác nhận: tệp là `zipp.zip` (không phải `zip.zip`); hồ sơ mặc định `precision` hay `wide`.

## 13. Thế giới v4: nghiên cứu miền và dữ liệu sát thực tế hơn (2026-10-14)
Chi tiết đầy đủ trong [DATA_V4.md](DATA_V4.md).
- Nghiên cứu: ACFE 2024 (cấp người thực hiện, thông đồng, che giấu, dấu hiệu đỏ, thời gian kéo dài), các vụ án và bài báo Việt Nam (có link), Atradius 2025 về hành vi thanh toán B2B Việt Nam.
- Mở rộng từ 6 họ (v3) lên 30 kịch bản theo cây gian lận ACFE: biển thủ tiền, hóa đơn, lương, chi phí, hàng tồn, tham nhũng, báo cáo tài chính, lạm quyền của chủ.
- Quy trình mới:
  - bán chịu → thu tiền → xóa nợ;
  - trả hàng và hoàn tiền;
  - hủy hàng tồn;
  - rút tiền mặt;
  - lương theo lịch riêng của từng công ty;
  - nghỉ việc và tuyển thay thế.
  - Có thêm 5 loại bút toán mới, sổ vẫn cân.
- Bối cảnh: 48 công ty, mỗi công ty được ngẫu nhiên hóa riêng (ngành, quy mô, ngày lương, kỳ hạn công nợ, thói quen tiền mặt). Khoảng một nửa số công ty không có vụ nào.
- Mỗi vụ có cấp người thực hiện, có hoặc không thông đồng, và mức che giấu L0/L1/L2. Mỗi kịch bản có ca hợp lệ mồi. Có thêm bảng `truth_cases.csv`.
- Các điểm phản biện đã được kiểm tra và sửa:
  - `put(dict(r))`;
  - payroll_padding trả về phần ngân sách còn lại;
  - tràn cửa sổ `timedelta`;
  - đánh giá theo cả dòng và vụ;
  - rò rỉ thời gian.
- Kiểm định `validate_v4.py`: các trường vô nghĩa (phút, giây, số thứ tự ID, chữ số hóa đơn) không thêm tín hiệu so với chỉ dùng loại nghiệp vụ (mức tăng ≤ 0).
- 15 đặc trưng dấu hiệu đỏ mới (`feats_v4.py`), chỉ dùng thông tin quá khứ.
- Kết quả (3 thế giới, B3):
  - Luật: AP 0,079.
  - LightGBM[friend190]: AP 0,069.
  - L3: AP 0,577, recall 77,5%.
  - max(L3, Luật, Entity): recall vụ 90,5%.
  - Che giấu L0 → L2 làm recall của L3 giảm từ 91 xuống 69.
  - Kịch bản chưa từng thấy (thế giới 411): fusion đạt 70,2%, nhưng ghost_employee 0%.
- Hạn chế:
  - Đặc trưng v4 và bộ sinh do cùng một người viết, nên kết quả là giới hạn trên.
  - Vẫn là dữ liệu tổng hợp.
  - Chưa có tập niêm phong v4 với kịch bản do người khác viết.

## 14. Nghiên cứu phương pháp trên v4 và tập niêm phong v4 (đăng ký trước, ghi ngày 2026-10-14, trước khi có kết quả dev)
**Ứng viên** (`agent2/hybrid.py`, `agent2/eval_v4.py`; danh sách cố định trong `CANDIDATES` và `POLICIES`):
- Không cần nhãn:
  - Luật + đồ thị (bạn bạn);
  - Novelty max(R,E): max của luật và EntityDeviation;
  - Novelty max(R,E,AE).
- Có giám sát:
  - L3;
  - L3-FB: cân bằng trọng số theo họ gian lận;
  - L4: L3 cộng thêm điểm của các bộ phát hiện không nhãn làm đặc trưng;
  - L4-FB;
  - C-L4 và C-L4-FB: hai tầng, thêm "trí nhớ" 90 ngày theo thực thể.
- Chính sách cảnh báo:
  - mỗi mô hình có giám sát kết hợp với mỗi kênh Novelty theo kiểu 2+1 khe;
  - max-rank của L3, L4-FB, C-L4-FB với Novelty max(R,E).

**Giao thức dev** (chỉ dùng w4_s411..413):
- P1: theo thời gian.
- P2: ẩn nhãn một nhánh ACFE trong huấn luyện và kiểm định. Các dòng vẫn giữ, nhãn đặt thành 0 như gian lận chưa bị phát hiện.
- P3: doanh nghiệp mới, học có giám sát trên hai thế giới còn lại.

**Quy tắc chọn** (đặt trước khi chạy):
- Điểm dev của cấu hình c = trung bình trên 3 thế giới của (Recall@B3 ở P1 + trung bình Recall@B3 theo nhánh ở P2 + Recall@B3 ở P3) / 3.
- Ràng buộc: tỷ lệ báo nhầm ca hợp lệ giống gian lận ở P1 ≤ 20%.
- Chọn cấu hình có điểm cao nhất. Nếu chênh nhau dưới 0,01 thì chọn cấu hình xuất hiện trước trong danh sách (đơn giản hơn).
- Chọn riêng một cấu hình khởi đầu lạnh (không cần nhãn) theo cùng quy tắc, trong ba ứng viên không nhãn.

**Tập niêm phong v4** (`agent2/world_v4_sealed.py`, seed 931..933, 40 công ty):
- Viết và sinh trước khi chạy bất kỳ bộ phát hiện nào trên đó.
- 7 kịch bản mới không có trong 30 kịch bản dev:
  - hóa đơn bán khống cho đại lý thật;
  - bán giá thấp nhận lại quả;
  - rút tiền về quỹ ngoài kế hoạch;
  - tạm ứng xoay vòng;
  - nâng lương làm thêm cả nhóm;
  - hợp đồng thuê kho khống;
  - nộp thuế khống.
- 5 loại ca hợp lệ mồi mới.
- Lịch trả lương mới ở 35% công ty.

**Đánh giá niêm phong, chạy một lần:**
- S1, trong doanh nghiệp: nhãn của 7 kịch bản mới bị ẩn khỏi lịch sử.
- S2, doanh nghiệp mới: học có giám sát trên 3 thế giới dev.
- Báo cáo tất cả ứng viên, nhưng kết luận dựa trên cấu hình đã chọn ở trên.

**Giới hạn trung thực:** cùng một người viết cả kịch bản niêm phong lẫn phương pháp. Để giảm thiên lệch, sau khi nghĩ ra kịch bản niêm phong tôi không thêm đặc trưng hay bộ phát hiện mới nào; chỉ thay đổi cách học và cách kết hợp.
