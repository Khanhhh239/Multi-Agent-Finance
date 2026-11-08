# 01 · Chiến lược dữ liệu

## 1. Vì sao dữ liệu là điểm nghẽn của Agent 4
Agent 4 không "học" từ dữ liệu tài chính (nó không huấn luyện dự báo); nó cần dữ liệu để (1) **chạy** lõi chỉ số trên một sổ cái đủ giàu, (2) **đánh giá** từng năng lực của agent (chọn công cụ, tham số, hỏi lại, từ chối, trung thực số, an toàn), (3) **tinh chỉnh** (tùy chọn) model nhỏ chọn công cụ. Dữ liệu thật của DN Việt Nam *không công khai*, nên chiến lược là **hai đường song song (dual‑track)**.

```
Đường 1 — Sổ cái tổng hợp có nhãn (synthetic, mô phỏng sự kiện)
   → kiểm thử đúng/sai tuyệt đối vì ta biết "sự thật" (ground truth)
Đường 2 — Dữ liệu công khai/thật ở mức phân phối (calibration)
   → bảo đảm các phân phối (độ trễ thanh toán, biên lợi nhuận, cơ cấu chi phí) không phi thực tế
Đường 3 — Bộ câu hỏi đánh giá (eval sets) sinh từ đường 1 + chuyên gia
   → đo từng năng lực của agent
```

## 2. Nguyên tắc
| # | Nguyên tắc | Thực thi |
|---|---|---|
| D1 | **Sinh theo nghiệp vụ, không sinh ngẫu nhiên từng dòng** | Mô phỏng ngày‑theo‑ngày: bán → xuất kho → thu tiền; mua → nhập kho → trả tiền; lương, thuế, khấu hao… (xem `04`). |
| D2 | **Cân đối tuyệt đối** | Mọi bút toán cân Nợ = Có (trừ ca lỗi cài chủ đích); sổ chi tiết AR/AP/Kho đối soát = sổ cái. |
| D3 | **Có sự thật nền (ground truth)** | Bảng `ground_truth` ghi mọi ca cài đặt (A1…A10, thanh khoản). |
| D4 | **Hard case là công dân hạng nhất** | Hạch toán lô, khách mất khả năng trả, chi phí tăng đột biến, trả trùng, tiêm nhiễm lệnh… (xem `05`). |
| D5 | **Tái lập được** | Một seed → một kho dữ liệu; `company_info` ghi seed/phiên bản. |
| D6 | **Tách dữ liệu dev / test** | Bộ eval sinh từ seed khác kho dùng để chỉnh prompt (xem `07`). |
| D7 | **Trung thực về độ "thật"** | Dữ liệu tổng hợp *không* chứng minh hiệu năng ngoài thực địa; có quy trình kiểm thử trên dữ liệu thật ẩn danh (xem `06`). |

## 3. Bản đồ lớp dữ liệu
| Lớp | Nội dung | Nguồn | Trạng thái |
|---|---|---|---|
| **L0 — Tham chiếu pháp lý** | Hệ thống tài khoản TT133, tỷ lệ BH, thuế suất, mức lương tối thiểu, biểu thuế | Văn bản pháp luật (đã tra, `1_business_analyst/07`) | ✅ nạp vào bộ sinh |
| **L1 — Sổ cái & sổ chi tiết tổng hợp** | `gl_entry` + AR/AP/kho/lương/TSCĐ/vay/ngân sách | Bộ sinh `agent4/datagen/*` | ✅ 140.583 dòng sổ cái, 21,5 tháng |
| **L2 — Nhãn sự thật** | `ground_truth` (20 ca) | Bộ sinh | ✅ |
| **L3 — Calibration** | Phân phối độ trễ thanh toán, biên LN theo ngành, cơ cấu chi phí | Dữ liệu công khai/khảo sát | ⏳ chỉ mới dùng tham số tay (xem `06`) |
| **L4 — Bộ câu hỏi đánh giá** | E1–E12 (định tuyến, tham số, hỏi lại, từ chối, trung thực số, an toàn…) | Sinh từ L1 + soạn tay | ⏳ spec ở `07`, chưa sinh |
| **L5 — Dữ liệu tinh chỉnh (tùy chọn)** | Cặp (câu hỏi → lời gọi công cụ) cho LoRA | Sinh từ L4 (phần train) | ⏳ |

## 4. Năng lực ↔ dữ liệu cần
| Năng lực agent | Dữ liệu cần | Nguồn |
|---|---|---|
| Chọn đúng chỉ số | Câu hỏi + nhãn chỉ số (đa dạng cách nói) | E1 |
| Trích tham số (kỳ, thực thể, chiều, so sánh) | Câu hỏi + JSON tham số chuẩn | E2 |
| Hỏi lại khi mơ hồ / từ chối | Câu mơ hồ & ngoài phạm vi có nhãn hành vi | E3, E4 |
| Chọn đúng khung (quản trị/thuế) | Câu hỏi + nhãn khung | E5 |
| Trung thực số | Kết quả công cụ + câu trả lời (đúng/sai) | E6 |
| Hội thoại nhiều lượt | Kịch bản 2–5 lượt có tham chiếu | E7 |
| Chống tiêm nhiễm | Chứng từ có diễn giải độc + câu hỏi kích hoạt | E8 (+ ca A8) |
| Text‑to‑SQL dự phòng | Câu hỏi ngoài thư viện + SQL chuẩn | E9 |
| Bản tin / bất thường | Kho có ca cài + danh sách ca phải nêu | E10 (+ A1…A10) |
| Chịu nhiễu ngôn ngữ | Biến thể không dấu, viết tắt, lỗi STT | E11 |
| Hiệu năng/tải | Luồng câu hỏi + kho lớn | E12 |

## 5. Quyết định then chốt đã chốt
1. **Doanh nghiệp mẫu chọn "phân phối thiết bị CNTT/văn phòng + dịch vụ kỹ thuật"** vì có đủ: tồn kho, công nợ lớn, bán chịu, dịch vụ định kỳ, dự án nhà nước, biên mỏng — phản ánh đúng "nỗi đau" của DNVVN thương mại.
2. **TT133** (chế độ DNNVV phổ biến): không TK 521, 6421/6422, 2293; có thêm hợp phần TT200/TT99 ở tầng chỉ số (đa chế độ).
3. **Hai khung dữ liệu từ một nguồn**: cột `tax_deductible`/`tax_note` trên từng dòng sổ cái sinh `v_tax`; không nhân đôi dữ liệu.
4. **Dữ liệu cố định tại `as_of` = 14/10/2026**, khóa sổ đến 08/2026 — để agent luôn phải xử lý *kỳ chưa khóa sổ*.
