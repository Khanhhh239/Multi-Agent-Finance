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

## 15. Tiếp nhận và tái lập pha A (2026-10-16)

- Đọc trạng thái, quy tắc R1 đến R10 và kế hoạch A đến E. Giữ nguyên tiêu chí chọn ở mục 14. Không chạy bộ phát hiện trên seed niêm phong khi chưa hoàn thành các cổng.
- Các Python đăng ký qua `py` trên máy đã bị xóa. Dùng Python 3.12.14 của workspace runtime để tạo `.venv`; cài đúng toàn bộ phiên bản trong `requirements.txt`. Không thay đổi môi trường của dự án khác.
- Kiểm thử gốc: **84 passed, 18 subtests passed**, 121,71 giây; log tại `work/tests_baseline.log`.
- Bổ sung `agent2/stats_v4.py`: bootstrap ghép cặp theo vụ trong từng công ty, khoảng 95% cho hiệu recall dòng, recall vụ và số vụ phát hiện. Tái lấy mẫu các dòng hợp lệ không ảnh hưởng hai mẫu số recall nên được tích phân bỏ chính xác. Không chọn lại ngân sách trong mẫu bootstrap; đây là độ bất định của quyết định cảnh báo cố định.
- Bổ sung `eval_v4 --save-alerts`: lưu thứ tự mã giao dịch, công ty, vụ, nhãn và cờ bool của mọi cấu hình P1 vào NPZ không cần pickle. Chưa thay đổi ứng viên, đặc trưng, tham số hoặc cách chọn cảnh báo.
- Đối chiếu `select_v4` với mục 14 trước lần chạy đầu: sửa biên hòa từ nhỏ hơn hoặc bằng 0,01 thành **nhỏ hơn 0,01**; báo lỗi rõ khi không có ứng viên hợp lệ; từ chối ghi đè tệp đóng băng trước khi ghi bảng chọn. Chưa chạy chọn cấu hình.
- Bổ sung kiểm thử cho thống kê, lưu cờ đúng thứ tự, bộ chọn và các chốt chặn niêm phong (tệp ra tồn tại, băm sai), cùng tính recall đã biết, mới và báo nhầm mồi mới. **14 kiểm thử mới qua**. Các bài kiểm thử niêm phong dùng bảng nhỏ và đường dẫn giả, không nạp thế giới niêm phong thật.
- Bổ sung `agent2/repro_v4.py` đối chiếu sáu dấu vân tay đúng tài liệu và lưu phiên bản môi trường. Trạng thái thiếu hoặc lệch là `blocked`, mã thoát 1. Chỉ chuyển A2 khi cả sáu thế giới khớp.
- Sinh lại dữ liệu phát triển từ đầu trong `work/data`, không dùng lại kết quả dở dang để lựa chọn. Kết quả kiểm định và đối chiếu được ghi tiếp bên dưới khi có.
- Bộ kiểm thử sau các bổ sung: **107 passed, 18 subtests passed**, 251,61 giây (`work/tests_phase_a.log`). Sau đó thêm một bài kiểm tra luồng niêm phong giả; cả bốn bài trong `test_sealed_v4.py` qua. Bài mới xác nhận ẩn nhãn lịch sử S1, giữ nhãn kiểm thử, đúng tham chiếu S2 và ghi kết quả trước khi in chỉ số. Đây chưa phải thử khô A4 trên thế giới 80.000 dòng.
- Sửa lỗi lưu đầu ra ở `sealed_v4.py`: tạo thư mục đích trước khi chấm; dùng chế độ tạo tệp độc quyền và chỉ in số sau khi ghi đầy đủ kết quả. Trước đây, lỗi ghi tệp cuối phiên có thể làm mất kết quả trong khi đã lộ chỉ số từng thế giới.
- Thực hiện phần độc lập của C3 trong lúc chờ A1: `schema.validate_input`, chín kiểm thử, hợp đồng dữ liệu. Thử trên 200.000 dòng tổng hợp của `w4_s411`: `passed`, không lỗi hoặc cảnh báo (`results/v4/schema_w4_s411.json`). Chế độ giảm mới là báo cáo; chưa nối vào pipeline, chưa coi C3 vận hành hoàn chỉnh.
- **A1 hoàn tất:** cả sáu thế giới tái sinh khớp dấu vân tay; kết quả và môi trường tại `results/v4/a1_repro.json`. Không thay bộ sinh. Đã đặt `core.autocrlf=false` riêng kho này và chuẩn hóa sáu tệp sẽ đóng băng về LF trước khi chạy A2 để băm không phụ thuộc chuyển dòng tự động.
- **A2:** bắt đầu tiến trình tách rời chạy lại P1/P2/P3, đầu ra `work/results/v4_methods`, log `work/v4_methods.log`, có lưu cờ P1. Không sao chép kết quả dở cũ. Chưa chạy chọn hoặc niêm phong.
- C4: chủ dự án trả lời chưa có tệp mẫu thật. Thêm CSV ánh xạ YAML, kiểu dữ liệu và múi giờ; XML khung theo tài liệu kỹ thuật công khai, luôn ghi chưa kiểm chứng, không suy diễn sổ kế toán hoặc xác nhận chữ ký. Sáu kiểm thử adapter qua. Vòng nhập 1.000 giao dịch tổng hợp đổi tên cột giữ nguyên ID và số tiền, lược đồ `passed` (`results/v4/adapter_smoke.json`). Thêm hai thư viện chỉ cho adapter: PyYAML 6.0.3 và defusedxml 0.7.1.
- C2: `explain_v4`, `explain_check`, năm kiểm thử qua. Đủ 15 mẫu theo các đặc trưng đã có, không thay điểm hoặc bộ phát hiện. Không báo tỷ lệ dự phòng của hai đặc trưng thiếu mẫu số thành tỷ lệ quan sát thật. Chưa nối pipeline hoặc đánh giá đầy đủ.
- E2: soạn sáu mẫu dự thảo, cần luật sư duyệt. Đối chiếu nguồn Chính phủ cho Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP, hiệu lực 2026-01-01; cập nhật hồ sơ câu hỏi E1. Chưa có thẩm định, doanh nghiệp, dữ liệu thật hoặc kết quả thí điểm.
- Tối ưu thực thi A2 trước khi đóng băng: thêm `--workers` để khớp tối đa ba ứng viên độc lập đồng thời, không thay lưới tham số hoặc thứ tự cấu hình. Đối chiếu P1 tái chạy trên 411 với lần tuần tự mới của cùng dữ liệu: **50.713 dòng, 24 cấu hình, không khác cờ nào, chênh chỉ số lớn nhất bằng không**; thời gian giao thức 91 xuống 64 giây (`results/v4/execution_regression.json`). Chọn ba ứng viên đồng thời cho phần còn lại. Dùng kết quả P1 mới đã đối chiếu, chạy lại P2 từ đầu; không sử dụng hai nhánh P2 chưa ghi thành giao thức của lần tuần tự. Log tiếp tại `work/v4_methods_parallel.log`. Số worker được ghi vào kết quả dev, tệp đóng băng và sử dụng lại ở niêm phong. Kiểm thử bộ chọn, lưu cờ và niêm phong: 11 bài qua sau thay đổi.
- Đã viết khung huấn luyện A6, bộ nạp chính sách và tín hiệu theo công ty; các kiểm thử đơn vị qua. Chưa huấn luyện mô hình v2: mã yêu cầu báo cáo A5 đủ ba thế giới khớp tệp đóng băng, và chỉ cho huấn luyện trên 411/412, giữ 413 kiểm thử.

## 16. Hoàn tất phát triển và đóng băng v4 (2026-10-16)

- A2 hoàn tất: cả ba thế giới có 24 kết quả P1, 10 nhánh ACFE P2 và 24 kết quả P3. Lưu tại `results/v4/method_study/`; bảng so sánh và kết luận giả thuyết tại `docs/03_danh_gia_va_hieu_qua_kinh_te/06_so_sanh_phuong_phap_v4.md`.
- Bootstrap ghép cặp 2.000 lần theo vụ, seed 0: khoảng 95% của hiệu recall L4 trừ L3 vẫn chứa hoặc chạm 0 trên từng thế giới. H1 chưa đạt; không tuyên bố hơn chắc chắn. Số chi tiết: `results/v4/paired_bootstrap.json`.
- Kiểm thử liên quan chọn, niêm phong, lưu cờ và bootstrap: 15 bài qua trong 2,61 giây trước A3. Ghi mã đánh giá tại commit `eee088e`, sáu tệp bị đóng băng sạch trong Git.
- A3 chạy lần đầu bằng đúng quy tắc mục 14: chọn **L4-FB**, khởi đầu lạnh **Novelty max(R,E)**. Điểm của L4-FB là 0,7416; điểm lớn nhất 0,7489 của `max(L4-FB,max(R,E))`, chênh nhỏ hơn 0,01 nên ưu tiên L4-FB đứng trước. Báo nhầm P1 của cấu hình chọn 16,62%, đáp ứng trần 20%. Không thay tiêu chí theo kết quả.
- Đã lưu tệp đóng băng và bảng chọn vào `results/v4/`. Từ đây giữ nguyên sáu tệp cho đến khi kết thúc niêm phong. Thế giới thử khô là seed 939, 80.000 dòng, 16 công ty; không dùng seed 931 đến 933 cho thử khô.
- Bộ kiểm thử đầy đủ trước thử khô: **141 passed, 18 subtests passed**, 117,42 giây (`work/full_tests_v4.log`).
- Lần thử khô đầu bị lỗi cấp phát bộ nhớ tại huấn luyện S2, chưa ghi JSON đầu ra và chưa in chỉ số. Một tác vụ kiểm tra lý do chạy đồng thời cũng lỗi OpenBLAS; dừng chạy đồng thời các tác vụ nặng của dự án. Không có lần chấm nào trên ba seed niêm phong thật.
- Sửa quản lý vòng đời dữ liệu trong trình điều phối `sealed_v4.py` (không thuộc sáu tệp đóng băng): loại dòng kiểm thử của các thế giới phát triển ngay khi nạp, chỉ giữ một bản gộp huấn luyện và kiểm định dùng chung, giải phóng bản sao S1 trước S2. Giữ nguyên thứ tự dòng, kiểu và giá trị; thêm kiểm thử so đúng toàn bảng với cách gộp cũ. Năm kiểm thử niêm phong qua trong 2,83 giây. Tệp đóng băng và sáu băm không thay đổi. Chạy lại thử khô trước khi cho phép A5.
- Kiểm tra giao diện trước đó đã mở hồ sơ và lưu một phản hồi QA trên dữ liệu tổng hợp. Khi tiếp tục phiên, công cụ trình duyệt lỗi khởi tạo `failed to write kernel assets`; reset rồi thử lại vẫn lỗi. Không coi ảnh cũ là bằng chứng cho các thay đổi giao diện mới; tiếp tục kiểm tra API bằng client thử.
- A4 hoàn tất sau khi chạy riêng: 80.000 dòng, 24 cấu hình ở cả S1 và S2, 185 dòng gian lận kiểm thử, trong đó 47 dòng thuộc kịch bản mới khớp đếm nhãn. `results/v4/dryrun_verification.json` ghi `passed`; JSON thử khô được lưu riêng, không dùng làm kết quả niêm phong thật.
- A5 bắt đầu lúc 14:08 ngày 2026-10-16 sau commit `8d3ab69`, dùng đúng ba seed niêm phong và băm gốc. Không chạy tác vụ nặng khác của Agent 2 trong khi chờ. Tắt riêng dịch vụ QA của dự án để giải phóng bộ nhớ; không tác động tiến trình dự án khác.
- C1 đến C5: có bộ nạp vận hành không nhãn, chấm theo tuần và công ty, bộ nạp mô hình theo cấu hình có băm, lời giải thích có bằng chứng, SQLite chỉ thêm quyết định, API có khóa công ty và giao diện mới. So đặc trưng vận hành với bộ nạp nghiên cứu trên 2.113 dòng của C001: 273 cột số giống hệt (`results/v4/inference_feature_regression.json`). Phiên QA dùng riêng Rules, không thay tệp khóa chính thức; chưa phải kết quả L4-FB v2 đầu-cuối.
- C3 bổ sung chế độ giảm: hợp đồng đầy đủ theo `configs/v4_input_columns.json`; khi thiếu bảng hoặc cột, không đưa giá trị mặc định vào mô hình. Chỉ dùng lại điều kiện C3 và, khi có danh mục quan sát cùng hạn mức, C2; các mô hình và luật khác bị tắt có báo cáo. Năm kiểm thử liên quan qua trong 3,22 giây. Không tuyên bố chế độ này có hiệu năng của cấu hình niêm phong.
- D4: soạn bộ mẫu bàn giao cho người viết độc lập; đã hỏi chủ dự án về người đảm nhận. Chưa tự viết kịch bản v5 để giả lập tính độc lập.
- Chủ dự án xác nhận **chưa có người viết độc lập** cho D4. Giữ phần này đang chờ; mẫu tại `docs/05_ke_hoach_giao_viec/independent_scenarios/README.md`.
- Lần thực thi A5 đầu dừng do `LightGBMError: bad allocation` ở huấn luyện S2. Kiểm `work/results/sealed_v4.json` chưa tồn tại, `work/sealed_v4.log` rỗng; không có chỉ số từng phần được in hoặc đọc. Giữ log lỗi tại `work/sealed_v4_oom.err`. Dùng ngoại lệ hạ tầng được A5 cho phép để khôi phục, không coi đây là một báo cáo niêm phong hoàn chỉnh.
- Trình điều phối có tùy chọn giới hạn số ứng viên thực thi đồng thời, giữ nguyên hàm huấn luyện, tham số, thứ tự và sáu băm. Khi giới hạn bộ nhớ: chuẩn bị từng thế giới trước khi cấp phát tập gộp S2; xóa bộ nhớ đệm phân tích thời gian và chuẩn hóa chuỗi sau tính đặc trưng. Tiến độ chỉ in tên giai đoạn và ứng viên, không in chỉ số cho tới khi lưu đủ báo cáo. Trước khi khôi phục, kiểm hồi quy P3 413 với thực thi lần lượt và thử khô lại; không tự bỏ qua các cổng này.
- C6 bổ sung khung học phản hồi theo từng công ty, có phiên bản và băm, chỉ nhận kết luận `confirmed` hoặc `legitimate`; không coi hồ sơ chưa xem, nghi vấn hoặc đánh giá đáng kiểm tra là nhãn gian lận. Mặc định không bật. Nếu bật bằng cấu hình riêng, báo `unvalidated_feedback`, không sử dụng kết quả G5 của cấu hình gốc làm bằng chứng cho biến thể này. Kiểm thời điểm học trước tuần chấm, cách ly công ty và bảo vệ mức ưu tiên hard trigger. Mười hai kiểm thử chọn lọc mới nhất qua trong 6,86 giây; chưa có nhãn người dùng thật để học.
- Trước khi có báo cáo niêm phong hoàn chỉnh, làm rõ cách tổng hợp cổng: dùng trung bình đều ba thế giới, riêng S1 và S2, nhất quán với tổng hợp thế giới ở G1 và bộ chọn. Báo cáo vẫn kiểm và công bố từng thế giới riêng. Điều kiện dừng M2 áp dụng recall chung và báo nhầm toàn bộ ca khó của từng giao thức sau tổng hợp; không lấy báo nhầm ca mới thay cho báo nhầm toàn bộ ca khó. Chỉ số không xác định phải dừng quy trình, không được tự coi là đạt. Đây là cách diễn giải phần kế hoạch chưa nêu rõ phép tổng hợp, ghi trước khi đọc kết quả; không đổi các ngưỡng.

## 17. Tiếp tục khôi phục và kiểm chứng sản phẩm (2026-10-17)

- Sau khi thu nhỏ kiểu lưu số nguyên có kiểm tra từng giá trị, hồi quy P3 413 tiếp tục qua: 1.020 chỉ số của 24 cấu hình giống chính xác; không đổi sáu băm, đặc trưng hoặc tham số. Báo cáo mới ghi `lossless_integer_compaction=true`. Lưu bằng chứng trước thu nhỏ riêng tại `results/v4/bounded_execution_before_compaction.json`.
- Lượt thử khô chỉ giới hạn ứng viên trước đó vẫn thiếu bộ nhớ ở S2; không có kết quả thật được ghi hay chỉ số thật từng phần được in. Cách hiện tại thu nhỏ số nguyên, giải phóng đối tượng sau từng ứng viên và chờ đủ bộ nhớ cấp phát. Chỉ chờ tài nguyên, không dừng tiến trình dự án khác hoặc đổi thiết lập hệ thống.
- Khởi động chuỗi khôi phục mới bằng `scripts/recover_sealed_v4.py --attempt compact`, sau 11 kiểm thử niêm phong và cổng qua. Chuỗi dừng nếu hồi quy, thử khô, phép kiểm khô hoặc điều kiện dừng M2 thất bại; giữ nguyên đầu ra niêm phong đã có, không tự ghi đè.
- Sửa đầu vào vận hành: chuẩn hóa tất cả thời điểm `_at` trước so lịch sử, dùng múi giờ nguồn của adapter hoặc giờ Việt Nam ở đầu vào chuẩn; giữ đúng thời điểm khi trộn độ lệch múi giờ. Chuẩn hóa token số nguyên khi đọc CSV để không lỗi ở biểu diễn như `1000.0`. Giữ kiểu số đã khai báo của adapter. Mười hai kiểm thử liên quan qua; một lỗi đổi kiểu số nguyên thành chuỗi trong adapter đã được phát hiện bằng kiểm thử và sửa trước khi dùng.
- Chạy lại đối chiếu vận hành và nghiên cứu sau sửa: 2.113 dòng, 273 cột số, chênh lớn nhất bằng không (`results/v4/inference_feature_regression.json`). Các tệp nghiên cứu đóng băng không thay đổi.
- Công cụ trình duyệt hoạt động lại sau cập nhật. Trên bộ QA tổng hợp riêng: chuyển C001 sang EMPTY hiển thị 0 hồ sơ, chuyển lại khôi phục đúng hàng đợi; lưu phản hồi `legitimate`, thời gian 1,5 phút, đánh giá không đáng kiểm tra bằng người giả `QA_SYNTHETIC_17`. Hàng đợi và mẫu số đánh giá cập nhật đúng. Ảnh giao diện mới: `work/ui_smoke/review-after17.png`. Các tỷ lệ trên màn hình này chỉ là thao tác QA, không phải kết quả nghiệp vụ.
- Thử khô sau thu nhỏ kiểu lưu đã qua: đủ 24 cấu hình mỗi giao thức, 185 dòng gian lận kiểm thử và 47 dòng mới. Đối chiếu toàn bộ đối tượng `worlds` của hai JSON thử khô: giống chính xác ở mọi trường S1 và S2. Lưu bản mới tại `results/v4/sealed_v4_bounded_dryrun.json`; báo cáo kiểm tại `results/v4/bounded_dryrun_verification.json`. Sau đó mới chạy lại A5 theo ngoại lệ hạ tầng.
- Lệnh huấn luyện v2 kiểm trực tiếp điều kiện dừng M2 từ báo cáo niêm phong; không chỉ phụ thuộc trình điều phối. Sáu kiểm thử đầu vào và huấn luyện chọn lọc qua sau bổ sung. Chưa huấn luyện v2 khi chưa biết kết quả A5 đầy đủ.
- **A5 hoàn tất lúc 11:07 ngày 2026-10-17:** đủ ba thế giới, hai giao thức và 24 cấu hình; kết quả đầy đủ đã ghi trước khi in chỉ số. Lưu nguyên báo cáo tại `results/v4/sealed_v4.json`, đánh giá cổng tại `results/v4/sealed_gates.json`, báo cáo tiếng Việt tại `docs/03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md`. Không thay lựa chọn L4-FB hoặc băm khóa.
- Trung bình đều ba thế giới: S1 recall chung **41,31%**, đã biết 53,54%, mới 20,32%, vụ 68,48%, báo nhầm ca mới 6,27%, toàn bộ ca khó 10,37%; S2 tương ứng **63,87%**, 83,25%, 31,22%, 85,47%, 11,05%, 11,39%. G5 không đạt; S1 dưới 50% kích hoạt **dừng toàn dự án tại M2**, đúng phép tổng hợp đã ghi trước khi có kết quả ở mục 16.
- Trình điều phối chuyển sang nhánh dừng: không huấn luyện A6, không tạo mô hình v2 hoặc cấu hình chính thức, không chạy kiểm tích hợp v2, kiểm giải thích đầy đủ hoặc đo hiệu năng 100.000 dòng. Không bắt đầu B, D hoặc thí điểm. Không dùng bảng chẩn đoán để chọn lại cấu hình và không chạy lại niêm phong. Những phần C đã viết được giữ là hiện vật nghiên cứu, chưa được chấp nhận vận hành doanh nghiệp thật.
- Kiểm thử cuối sau A5: **165 passed, 18 subtests passed**, 72,36 giây, mã thoát 0; log lỗi rỗng. Python `compileall` và JavaScript `node --check review_ui/v4.js` qua. Bằng chứng tổng hợp tại `results/v4/test_verification.json`; ảnh và biên bản QA tại `results/v4/ui_review_qa.png`, `results/v4/ui_review_qa.json`. Dừng riêng dịch vụ QA cục bộ cổng 8776 sau khi lưu bằng chứng; không tác động tiến trình dự án khác.
- Kết luận bàn giao: đã hoàn thành A1 đến A5 và kiểm chứng kỹ thuật nêu trên, **chưa hoàn tất toàn bộ kế hoạch A đến E**. Cần chủ dự án xem lại bài toán theo điều kiện dừng; vẫn chưa có tệp xuất thật, người viết kịch bản độc lập, dữ liệu thí điểm hoặc thẩm định pháp lý. Không suy diễn các số tổng hợp thành hiệu năng doanh nghiệp thật.

## 18. Mở vòng v5 theo giao việc mới, Bước 0 (2026-10-19)

- Chủ dự án cho phép hậu kiểm R0 trên v4 và soạn đăng ký trước R1, rồi dừng chờ trả lời “duyệt”. Đây là ngoại lệ được chủ dự án chỉ định cho quy tắc R1 cũ: kết quả mới chỉ là hậu kiểm, không phải niêm phong. Kết luận v4 không đạt G5 giữ nguyên; chưa được bắt đầu R2, R3 hoặc R4.
- Push bốn commit bị từ chối vì remote có thêm `f593a78`. Fetch và hợp nhất giữ toàn bộ lịch sử, không force-push; giải quyết README bằng cách giữ cả kết luận v4 và hướng dẫn bộ luật mới. Không sửa sáu tệp khóa hoặc kết quả v4.
- Lần gọi pytest chung cả ba thư mục lỗi trùng tên module; chế độ importlib lại không đáp ứng các import fixture của bộ mới. Chạy riêng đúng hai bộ như hướng dẫn repository. Bộ tương thích qua 166 bài và 18 kiểm tra con trong 129,52 giây. Phiên kiểm bộ mới trước bị ngắt; lượt sau lỗi thiếu thư mục `.runtime`; đã tạo thư mục theo hướng dẫn và chạy lại: 373 bài qua, 88,748 giây. Chỉ push sau các kết quả qua này.
- Bằng chứng kiểm thử và băm được lưu tại `results/v5/step0_merge_verification.json`. Mã hậu kiểm và kiểm thử R0 được chuẩn bị riêng, chưa chạy trên dữ liệu tổng hợp của ba thế giới hậu kiểm tại mốc Bước 0.

- Trong lúc kiểm thử, remote bổ sung `2954ee0` hoàn tác toàn bộ `f593a78`. Push bị từ chối lần nữa. Hợp nhất commit hoàn tác, tôn trọng trạng thái bộ luật trên remote, giữ phần v4 cục bộ trong README; không khôi phục lại bản cập nhật bị hoàn tác. Kiểm thử lại bản cuối trước push; kết quả 166 và 373 bài ở trên là bằng chứng trạng thái trung gian, không thay cho kiểm thử bản cuối.

- Bản cuối sau hợp nhất hoàn tác qua **165 bài pytest và 18 kiểm tra con**, 125,82 giây, mã thoát 0. Chưa đưa mã hoặc kiểm thử R0 đang chuẩn bị vào commit Bước 0. Kiểm lại băm kết quả và sáu tệp v4 trước push: không đổi.

## 19. R0 hậu kiểm v4, kế hoạch trước khi chạy (2026-10-19)

- Bước 0 đã push thành công tới `3a3cfe3`, giữ bốn commit cục bộ, cả cập nhật và hoàn tác trên remote. Bắt đầu R0 theo quyền mới của chủ dự án. Mọi kết quả mới là **hậu kiểm, không phải niêm phong**, trên **dữ liệu tổng hợp**. Không thay kết quả, khóa, ngưỡng hoặc kết luận v4 không đạt G5.
- Chỉ phân tích L3, L4-FB và cấu hình khởi đầu lạnh đã chọn `Novelty max(R,E)`. Bắt buộc dùng bộ đệm đặc trưng v4 có sẵn; không dựng lại bằng bộ luật khác. Tái lập toàn bộ chỉ số gốc S1 và S2 của ba phương pháp, sai số cho phép 0,000000000001; nếu lệch thì dừng trước can thiệp. Ghi băm nguồn, bộ đệm, cờ P1 và tệp được bảo vệ vào manifest.
- Năm giao thức cố định: S1 gốc giữ nhãn mới thành 0; S2 gốc; S1 chỉ loại dòng kịch bản mới khỏi huấn luyện; S1 loại khỏi cả huấn luyện và kiểm định để kiểm độ nhạy; S1 giữ dòng và giảm trọng số mọi dòng nhãn 0 xuống **0,2**. Không thử hệ số khác. Giữ lưới, seed, đặc trưng, ngân sách và cách chọn theo kiểm định gốc. Kênh không nhãn luôn dùng cùng tham chiếu gốc, là đối chứng không đổi.
- Loại dòng mới dùng nhãn thật tổng hợp như một can thiệp biết trước, không phải giải pháp triển khai. Không tái khớp đặc trưng không nhãn; hiệu ứng gồm loại dòng và thay đổi cân bằng lớp, không được gọi là ước lượng nhân quả thuần về nhiễu nhãn. Biến thể giảm trọng số chỉ là kiểm độ nhạy R0, chưa phải cài đặt PU của R2.
- Phân rã cộng theo thứ tự: A recall P1; B recall P1 tái trọng số theo cơ cấu kịch bản đã biết ở đích; C recall S2 trên kịch bản đã biết; D recall S2 chung; E recall S1 loại dòng mới chỉ khỏi huấn luyện; F recall S1 gốc. Năm hiệu liên tiếp cộng đúng về A trừ F, xấp xỉ 39,5 điểm ở L4-FB. Đây là đồng nhất thức mô tả có thứ tự, không phải cách quy nguyên nhân duy nhất. Phần D trừ E giữ cả khác biệt nguồn, quy mô huấn luyện và lịch sử kiểm định chưa được tách riêng.
- Bootstrap **2.000 lần**, seed **20261019**, gom nguyên vụ. Với phân rã, tái lấy mẫu trong từng thế giới và từng họ ở phát triển để bảo đảm tỷ lệ theo họ xác định; ở đích lấy nguyên vụ trong từng thế giới, dùng chung mẫu cho các giao thức. Không chọn lại ngân sách hoặc khớp lại mô hình trong bootstrap. Khoảng 95% có điều kiện trên ba thế giới, cơ cấu họ phát triển và mô hình cố định; không đo độ bất định khi sinh thế giới hoặc huấn luyện lại.
- Phân nhóm lịch lương theo đúng ba lịch chỉ có trong bộ sinh niêm phong: ngày 1, ngày 20, ngày 7 và 22; báo cả quy mô micro, small, medium, nhóm chéo và riêng kịch bản lương đã biết. Lịch lương không được ngẫu nhiên can thiệp độc lập ở R0, nên khác biệt nhóm là liên hệ, không phải tác động nhân quả.
- Đầu ra riêng tại `results/v5/postmortem_v4/`, lưu JSON sau từng giao thức và kiểm lại băm tệp v4 khi kết thúc. R0 xong mới soạn kết luận và R1 để chủ dự án duyệt; không tự bắt đầu R2.

- Lượt R0 đầu dừng ngay cổng tái lập S1 931, trước mọi can thiệp: AP L3 lệch 0,00000000075098569, trong khi các chỉ số ngân sách và recall khớp. Không nới dung sai hoặc bỏ cổng. Chuyển cách gọi sang đúng `eval_v4.run_candidates` và số worker đã khóa như trình điều phối gốc, thay cho gọi trực tiếp factory; giữ nguyên các công thức. Giữ manifest lần dừng ở thư mục gốc; chạy tiếp vào `results/v5/postmortem_v4/run2/` với băm mã riêng.

- Lượt 2 bằng đúng hàm thực thi gốc vẫn cho cùng chênh AP L3 S1 931; các chỉ số quyết định theo ngân sách vẫn khớp. Trước mọi can thiệp, sửa phạm vi chốt tái lập: giữ dung sai 0,000000000001 cho toàn bộ trường ngoài AP; lưu AP lịch sử, AP chạy lại và hiệu riêng cho từng mô hình, không dùng AP để chọn gì hoặc phân rã. Không xác định được nguyên nhân chính xác, không tuyên bố điểm thô trùng bit. Không sửa, nới hay thay bất kỳ cổng v4 nào. Thêm kiểm thử xác nhận chênh recall vẫn phải dừng. Giữ hai manifest lỗi, chạy chính thức vào `results/v5/postmortem_v4/run3/`.

- Lượt 3 đã lưu đủ 15 giao thức và `summary.json`, kiểm băm không đổi; sau đó lỗi `UnicodeEncodeError` khi in dòng thông báo cuối ra đầu ra Windows cp1252. Khôi phục với `PYTHONIOENCODING=utf-8`, dùng lại checkpoint khớp manifest, không khớp lại mô hình. Giữ log lỗi trước, sau đó mới tạo báo cáo và chạy kiểm thử đầy đủ.

- **R0 hoàn tất và kiểm chứng:** đủ 15 giao thức, 18 cặp mô hình gốc. Lượt hoàn chỉnh có AP khớp cả 18 cặp; giữ nguyên hai lượt AP đã dừng. Khôi phục UTF-8 dùng lại toàn bộ checkpoint, không khớp lại mô hình. Mọi băm đầu vào, mã R0, kết quả và khóa v4 giữ nguyên; tập vụ không đổi; đối chứng Novelty không đổi qua can thiệp.
- L4-FB: loại dòng mới chỉ khỏi train tăng recall **5,59 điểm** [1,41; 9,91]; loại cả train và validation tăng **6,07 điểm** [1,88; 10,54]; giảm trọng số nhãn 0 xuống 0,2 tăng **10,07 điểm** [6,86; 13,40]. Đây là khoảng bootstrap có điều kiện, không khớp lại mô hình, không phải bằng chứng trên doanh nghiệp thật.
- Phân rã mô tả L4-FB: cơ cấu họ đã biết −0,63; chuyển giao trong họ đã biết −1,81; hỗn hợp kịch bản mới ở S2 19,38; nguồn học và lịch sử còn gộp 16,98; can thiệp loại dòng train 5,59 điểm. Tổng **39,50 điểm** [32,55; 45,34], sai số cộng bằng 0. Không gọi đây là phân bổ nhân quả duy nhất.
- 933 có 114 dòng dương đã biết train và 187 dòng mới bị ẩn train; test 57 vụ, 18 vụ L2, ít hơn 29 vụ L2 của 932. Chênh S1 so trung bình 931, 932 là 19,19 điểm, gồm 7,05 phần cơ cấu họ và 12,13 phần tỷ lệ trong họ theo đồng nhất thức mô tả. Không quy toàn bộ mức kém cho che giấu hoặc lịch lương.
- Báo cáo R0 có 18 bảng, đủ 30 kịch bản đã biết cho ba phương pháp ở S1 và S2; JSON tại `results/v5/postmortem_v4/run3/`. Kiểm thử đầy đủ cuối: **174 passed, 18 subtests passed**, 401,98 giây, mã thoát 0; bốn cảnh báo bỏ dần `eval_set` khi kiểm công thức gốc LightGBM, không sửa công thức chỉ để bỏ cảnh báo. `results/v5/r0_verification.json` qua mọi kiểm băm, tập vụ, đối chứng và phân rã. Chưa thực hiện R2 hoặc tải dữ liệu ngoài.

## 20. R1 đăng ký trước v5, chờ duyệt (2026-10-19)

- R0 đã commit tại `58d99ba`, 174 bài và 18 kiểm tra con qua. Soạn `docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md` trước bất kỳ thí nghiệm R2 nào. Bản này là đề xuất, **chưa được chủ dự án duyệt**. Câu “tiếp đi” để hoàn tất R0 không được tự diễn giải thành duyệt bản R1 chưa bàn giao.
- S2 chính, khởi đầu lạnh không nhãn riêng, S1 chỉ phụ với trạng thái P và U. Dùng đủ 20 thế giới seed 1001 đến 1020, S2 học từ 19 nguồn còn lại; phối hợp bỏ một nhánh ACFE. Chọn theo điểm nhỏ nhất của trung bình recall S2 và recall 10 nhánh ẩn, trần báo nhầm ca khó 15% ở từng thế giới và giao thức. Phá hòa dưới 0,01 theo danh sách đã khóa.
- Cổng đề xuất S2: recall chung trung bình từ 60%, mới từ 35%, từng thế giới từ 45%, chênh tuyệt đối so S2 phát triển không quá 15 điểm, ca khó từng thế giới không quá 15%. Cold có cổng riêng 35%, 30%, sàn 25%, ca khó 15%. Không thay G5 hoặc kết luận v4. Quyết định dùng ước lượng điểm, báo bootstrap theo vụ; không thay cách quyết định sau niêm phong.
- Bản đăng ký ghi nguồn dữ liệu, chia thời gian, PU, năm seed, ngân sách, số lần thử, giới hạn tính toán 220 giao thức cho mỗi ứng viên và 1.100 lượt khớp khi tập hợp năm seed, chưa phải thời gian đo. Đăng ký cơ chế niêm phong v5 và giới hạn độc lập giữa các phiên agent, không thay thế chuyên gia độc lập.
- Nếu S2 v5 trượt: giữ kết quả, không tự mở vòng v6 hoặc chỉnh rồi chấm lại; trình phương án dịch vụ rà soát định kỳ cho đơn vị kế toán. Nếu chỉ Cold trượt, không chào bán Cold và phải trình lại phạm vi sản phẩm. Trước dữ liệu ngoài phải xin duyệt riêng về tệp, nguồn, dung lượng, giấy phép.
- **Điểm dừng bắt buộc thứ nhất:** bàn giao R0 và R1, chờ chủ dự án trả lời “duyệt”. Chưa bắt đầu R2, R3, sinh dữ liệu v5, tải dữ liệu ngoài hoặc R4. Chỉ bổ sung tài liệu sau commit R0, không thay mã mô hình hoặc dữ liệu đã kiểm thử.

## 21. R1 v1.1 được duyệt có sửa đổi (2026-10-19)

- Chủ dự án duyệt rõ ràng bốn sửa đổi. Cập nhật đăng ký v1.1 trước R2, giữ nguyên toàn bộ byte bản v1 ở cuối tệp và ghi băm gốc. Đây là quyền tiếp tục R2; không cần hỏi duyệt lại khi chỉ thực hiện đúng sửa đổi.
- Khóa hai tầng: sàng lọc 1001 đến 1008, seed 0, 11 giao thức; ba ứng viên dẫn đầu sang tầng chọn 1001 đến 1020, năm seed trung bình điểm. J là trung bình Q của hai hoặc bốn thế giới thấp nhất; B gộp các nhánh dưới 10 dòng dương theo recall vi mô. Trần ca khó 15% từng thế giới và giao thức. Giữ 19 thế giới nguồn mỗi đích.
- Chọn w trong 0,1; 0,2; 0,5 trên L4-FB bằng J sàng lọc rồi khóa trước mô hình khác. Mọi mô hình có giám sát đều dùng w. Không thử nnPU trong danh sách chính; nếu bổ sung phải đăng ký riêng trước thử.
- Chốt chặn trước sinh niêm phong: S2 đồng thời 65% chung, 40% nhánh, 50% thế giới tệ nhất; Cold 40%, 33%, 30%. S2 trượt thì không sinh hoặc chấm v5 và viết đề xuất đổi hướng. Cold trượt thì bỏ Cold. Giữ các cổng niêm phong của v1.
- Cần làm rõ phạm vi ba suất chuyển tầng so với điều khoản chọn Cold riêng của v1; đã gửi câu hỏi trước mọi so sánh. Không tự quyết định bằng kết quả. Có thể tiếp tục sinh và kiểm định 20 thế giới vì không phụ thuộc cách xếp Cold.
- Sau commit tài liệu mới bắt đầu R2: khóa danh sách và tiêu chí giữ hoặc bỏ trước chạy, sinh và kiểm V1 đến V12, chọn w, triển khai thay đổi và công nợ với kiểm thử vét cạn, sàng lọc rồi chọn. Mọi kết quả là dữ liệu tổng hợp; không sửa tệp khóa hoặc kết luận v4.
