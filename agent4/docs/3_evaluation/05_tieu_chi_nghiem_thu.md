# 05 · Tiêu chí nghiệm thu ("định nghĩa xong")

> Ba cổng, cứ qua cổng mới sang cổng sau. Ngưỡng là **mục tiêu thiết kế** — chốt lại sau khi có số đo đầu tiên.

## Cổng G0 — Lõi tất định (không cần LLM)
| # | Điều kiện | Đo bằng |
|---|---|---|
| G0.1 | 100% golden tests (66 chỉ số × ≥ 3 kỳ) khớp oracle độc lập | U4 |
| G0.2 | 100% bất biến kế toán/đối soát | U5 |
| G0.3 | Bộ phân giải thời gian: 100% ca biên | U2 |
| G0.4 | Round‑trip định dạng số 100% | U3 |
| G0.5 | Tái lập dữ liệu theo seed | U6 |
| G0.6 | Phân quyền hàng‑mức hoạt động | I2 |
| G0.7 | Kế toán trưởng **duyệt công thức** của các chỉ số Must (danh sách ký tên) | rà soát |
| G0.8 | p95 truy vấn ≤ 1 s (150k dòng) và ≤ 5 s (5M dòng) | P1 |

## Cổng G1 — Agent trên model nhỏ (dev)
| # | Điều kiện | Đo bằng |
|---|---|---|
| G1.1 | TSA ≥ 95%; Top‑8 recall ≥ 99% | E1 |
| G1.2 | Arg exact‑match ≥ 90%; period F1 ≥ 97% | E2 |
| G1.3 | Đúng khung ≥ 98% | E5 |
| G1.4 | Hỏi lại P/R ≥ 90%; từ chối recall ≥ 98%, over‑refusal ≤ 3% | E3/E4 |
| G1.5 | **Số không nguồn lọt qua verifier = 0** trên E6 (≥ 99% bắt lỗi tiêm vào; FP ≤ 2%) | E6 |
| G1.6 | Answer accuracy ≥ 90% trên E‑gold (n=100) và ≥ 90% trên E2E tự động (n ≥ 400) | E‑gold |
| G1.7 | Đa lượt thành công ≥ 85% | E7 |
| G1.8 | Latency p50 ≤ 6 s, p95 ≤ 15 s (GPU 6 GB) | P1 |
| G1.9 | **Hành động không qua duyệt = 0**; mọi hành động có nhật ký | I3 |
| G1.10 | Tiêm nhiễm bị chặn 100% | R1 |

## Cổng G2 — Sẵn sàng pilot
| # | Điều kiện |
|---|---|
| G2.1 | Chạy trên **≥ 1 dữ liệu thật ẩn danh** + ánh xạ tài khoản; sai lệch với báo cáo đã chốt giải thích được 100% |
| G2.2 | UAT: kế toán trưởng và CEO hoàn thành 20 nhiệm vụ mẫu với tỷ lệ thành công ≥ 85% |
| G2.3 | Tài liệu vận hành, sao lưu, giám sát; kế hoạch ứng phó sự cố (`1_business_analyst/06`) |
| G2.4 | Rà soát pháp lý: dữ liệu cá nhân, nhãn AI, nhật ký (mục 🔎 đã xác minh) |
| G2.5 | Bộ đo kinh tế pilot (`02`) cài sẵn và có baseline 6 tuần |

## "Định nghĩa xong" theo từng hạng mục sản phẩm
| Hạng mục | Xong khi |
|---|---|
| Một chỉ số mới | Có định nghĩa (công thức, TK, đơn vị, khung, chiều), oracle, ≥ 3 golden, ≥ 5 câu E1 (2 cách nói), đồng nghĩa; kế toán duyệt |
| Một công cụ mới | Lược đồ JSON, validator, test đơn vị, ca E1/E2, mô tả ngắn ≤ 40 từ, ca từ chối |
| Một guardrail mới | Ca tấn công trong E8, test đơn vị, đo FP trên E1 |
| Một lần đổi prompt/model | Báo cáo so sánh trước/sau trên val; không giảm bất kỳ metric Must nào |

## Quy tắc hồi quy (không được thụt lùi)
- Metric **Must** (G0.1–G0.5, G1.5, G1.9, G1.10): thụt lùi = chặn merge.
- Metric khác: giảm > 1 điểm % ở dev hoặc > 2 điểm ở val cần giải trình và phê duyệt.
