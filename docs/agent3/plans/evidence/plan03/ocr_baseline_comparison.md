# So sánh OCR trên cùng functional development split

Chạy 12/10/2026 bằng `scripts/build_plan03_baseline.py`. Ba cấu hình cùng Tesseract, Việt–Anh, cùng 10 PNG của project (`syn-00`…`syn-09`), cùng image/reference hashes và máy CPU. Không dùng MC-OCR/FATURA hoặc frozen test để chọn baseline.

| Cấu hình | CER micro | WER micro | Ngày exact / có nhãn | Tổng tiền exact / có nhãn | Lỗi invocation | Có geometry |
|---|---:|---:|---:|---:|---:|---:|
| PSM 3 | 15,94% | 56,20% | 10/10 | 7/9 | 0/10 | 10/10 |
| PSM 6 | 15,94% | 56,20% | 10/10 | 7/9 | 0/10 | 10/10 |
| PSM 11 | 15,38% | 58,53% | 0/10 | 7/9 | 0/10 | 10/10 |

CER/WER dùng khoảng trắng chuẩn hóa + NFC, vẫn phân biệt dấu/chữ hoa và dấu câu. Reference là text generator từ trang 1 native PDF tương ứng. PNG syn-08 chỉ biểu diễn trang 1; trang 2 được kiểm tra pipeline bằng PDF đầy đủ trong vòng chạy 38 tài liệu.

Ngày/tổng tiền dùng bbox nhãn generator để chọn detection, rồi so giá trị nhận dạng chính xác theo mẫu ký tự. Đây là **oracle-region OCR recognition**, không phải accuracy tìm trường hoặc CFR. Một mẫu không có tổng tiền OBSERVED bị loại khỏi mẫu số; không thay nhãn thiếu bằng giá trị suy đoán. Diagnostic keys `*_exact_line_value` trong JSON là tên wire ban đầu; phương pháp thực tế là exact-region, thể hiện trong từng run record.

Latency p50/p95, cold-first/warm median, adapter-load, peak committed RAM và run SHA nằm trong [summary](baseline_summary.json). P95 dùng nearest rank; chỉ 10 mẫu nên không phải SLO. Mỗi batch tạo process mới, một adapter cho 10 trang. Adapter-load chỉ tính import/init Python; Tesseract executable và language data được load lại trong mỗi inference. Vì vậy warm ở đây là process Python còn sống, không phải model GPU được giữ trong RAM. RAM đo Windows Job Object của cả cây worker, giới hạn 512 MiB; không dùng GPU, VRAM không áp dụng.

Lần chạy pipeline đầy đủ có **38 tài liệu / 41 trang**, gồm native, scan, mixed, hybrid, hidden layer, garbage text, rotation/crop, EXIF và ảnh. Cả 38 hoàn tất chức năng; trang trắng/garbage có thể không tạo block, để PLAN_04/05 quyết định thiếu dữ liệu. Native routes không gọi model. Các fixture PDF corrupt/encrypted/oversized đã bị PLAN_02 từ chối trước OCR.

Raw predictions, references hash, diagnostics và normalized document artifacts nằm trong `data invoice/plan03_local/`, tránh đưa nội dung tài liệu vào báo cáo công khai. Summary giữ đường dẫn/checksum để validator đối chiếu.

Các giới hạn chất lượng còn mở: dữ liệu tổng hợp nhỏ và cùng font/layout; chưa có nhãn người đối chiếu; chưa đo hóa đơn thuế Việt Nam thật; không chứng minh chịu blur/perspective/bảng phức tạp; không phải so sánh nhiều engine. Không chuyển CER hay heuristic confidence thành quyết định tự chấp nhận.
