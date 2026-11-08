# 08 · Kiểm định chất lượng dữ liệu

## 1. Đã kiểm tra (chạy ngay khi sinh — `build._validate`)
| # | Kiểm tra | Kết quả (seed 20251) | Ghi chú |
|---|---|---|---|
| Q1 | Chứng từ cân Nợ = Có | **1** chứng từ lệch (ca A4 cài chủ đích) | Còn lại cân 100% (39.480/39.481) |
| Q2 | Sổ cái 131 = Σ(hóa đơn − thu − điều chỉnh) | chênh **0** | Đối soát AR |
| Q3 | Sổ cái 331 = Σ(hóa đơn mua − thanh toán) | chênh **0** | Đối soát AP |
| Q4 | Sổ cái 156 = Σ `inventory_txn.value` | chênh **0** | Đối soát kho |
| Q5 | Tiền gửi không âm | nhỏ nhất ≈ 1,37 tỷ | Có áp lực thanh khoản nhưng không âm |
| Q6 | Ràng buộc dòng | CHECK Nợ/Có XOR ≥ 0 trên `gl_entry` | DuckDB từ chối dòng vi phạm |
| Q7 | Tái lập | cùng seed → cùng kết quả | Cần kiểm lại tự động (xem §3) |
| Q8 | 12 test hợp đồng v0 | 12/12 xanh | `tests/test_legacy_contract.py` |
| Q9 | Chạy mọi chỉ số × 3 kỳ | 0 lỗi | Smoke; **chưa** là test đúng/sai (xem §3) |

## 2. Biến động theo thời gian (nhìn nhanh để bắt lỗi hiển nhiên)
| Chỉ tiêu | 2025 | 2026 đến 14/10 |
|---|---|---|
| Doanh thu thuần | 185,6 tỷ | 169,0 tỷ (≈ 215 tỷ quy năm, +16%) |
| Biên lợi nhuận gộp | 19,2% | 19,3% |
| Lợi nhuận sau thuế | 1,57 tỷ | 3,87 tỷ (tạm tính, nhiều tháng chưa khóa) |
| DSO | 53 ngày | 62 ngày (Q3) |
| Dư nợ vay cuối kỳ | — | 25,1 tỷ |

## 3. Việc kiểm định còn thiếu (giao ở `5_handoff`)
| # | Kiểm tra cần thêm | Mục đích | Cách làm |
|---|---|---|---|
| V1 | **Golden test độc lập** cho từng chỉ số (SQL tay, không dùng engine) trên ≥ 3 kỳ | Phát hiện lỗi công thức/dấu | `tests/test_metrics_golden.py` + `eval/oracle.py` |
| V2 | **Bất biến kế toán** | Phương trình kế toán: Tài sản = Nợ + Vốn (theo từng ngày cuối tháng) | Property test |
| V3 | **Lợi nhuận qua hai đường** | LN = ΣTK 5–8 (phát sinh) = Δ(4212) cho tháng đã khóa | So sánh engine ↔ số dư 421 |
| V4 | **Tổng nhóm = tổng** | Σ rows theo chiều = value cho mọi chỉ số/ chiều | Test tự động trên lưới (chỉ số × chiều) |
| V5 | **Tái lập seed** | cùng seed → cùng hash bảng | Test băm |
| V6 | **Độ nhạy đối với nhiễu hạch toán lô** | `dso_actual` dùng `bank_txn_date`? (hiện dùng `receipt_date`) | Quyết định & test |
| V7 | **Fidelity so dữ liệu thật** | Mục 3.4 của `06` | Notebook phân tích |
| V8 | **Kiểm tra tính hợp lý nhân sự/lương** | Lương/doanh thu, hoa hồng | Biểu đồ + ngưỡng |
| V9 | **Đối soát thuế** | 33311, 1331 vs hóa đơn; CIT = 20% × (LNTT + chi phí không được trừ) | Test số học |
| V10 | **Phát hiện ca cài** | Mọi ID trong `ground_truth` truy vết được bằng truy vấn | Test "oracle phát hiện" |

## 4. Giới hạn đã biết của dữ liệu (cần minh bạch khi báo cáo)
1. **Một công ty, một seed** — chưa chứng minh tổng quát hóa.
2. **Công thức sinh do nhóm đặt**, chưa hiệu chỉnh từ dữ liệu thật VN (xem `06`).
3. **Hạn mức vay chạm 20 tỷ** vào cuối kỳ và tiền gửi thấp ⇒ kịch bản khá căng; có thể phản ánh quá "xấu" cho một DN trung bình (đã chủ ý để tạo hard case thanh khoản).
4. **Ngân sách (`budget`) sinh từ chính số thực tế 2025** (±4–8% nhiễu; 2026 = 2025 × hệ số) → không độc lập; chỉ dùng để thử chức năng `budget_vs_actual`.
5. **Chỉ số lương** gồm cả kỹ thuật viên hạch toán qua 154 (sau đó vào giá vốn dịch vụ) — nhiều kế toán sẽ tách khác; cần rà soát công thức.
6. **TNCN/giảm trừ gia cảnh/bảo hiểm** theo giả định ở `04`; chưa xác minh với văn bản gốc.
7. Một số TK chi tiết (34111/34112, 11211/11212) do bộ sinh đặt để phục vụ chỉ số, không phải chuẩn bắt buộc.
8. Cột `description` chứa dữ liệu độc có chủ đích (ca A8): **mọi pipeline đọc cột này phải coi là dữ liệu không tin cậy**.
