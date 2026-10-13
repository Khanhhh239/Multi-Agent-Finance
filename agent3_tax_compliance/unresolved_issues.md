# Các Hạng Mục Chưa Triển Khai (Môi Trường Production)

Dưới đây là tổng hợp chi tiết các hạng mục và bài toán kỹ thuật cần được giải quyết khi chuyển dịch dự án **Agent 3: Tax Compliance Engine** từ giai đoạn thử nghiệm (Demo/Development) hiện tại sang môi trường chạy thực tế (Production).

---

## 1. Tầng Nhận Diện Hình Ảnh & Văn Bản (OCR)
*   **Hiện trạng**: Đang sử dụng Mock Skeleton nhận diện thô dựa trên quy ước tên tệp.
*   **Hạng mục cần làm**:
    *   Tích hợp dịch vụ OCR thực tế (như **Google Cloud Vision API** cho độ chính xác cao hoặc **PaddleOCR** chạy offline tự lưu trữ).
    *   Xây dựng bộ tiền xử lý hình ảnh (xoay, tăng độ tương phản, lọc nhiễu) để xử lý ảnh hóa đơn chụp từ điện thoại bị mờ, lệch góc.

## 2. Bản Địa Hóa & Bảo Mật Dữ Liệu Nội Bộ (Fine-tune PhoBERT)
*   **Hiện trạng**: Đang gọi API đám mây bên ngoài (OpenAI/Groq) để phân loại giao dịch và che PII.
*   **Hạng mục cần làm**:
    *   **Huấn luyện (Fine-tune) PhoBERT**: Xây dựng mô hình phân loại Tiếng Việt chạy cục bộ (Offline) để phân danh mục chi phí (`expense_category`) và hình thức thanh toán (`payment_method`).
    *   **PhoBERT NER (Named Entity Recognition)**: Thay thế Regex bằng mô hình nhận diện thực thực thể thông minh để quét sạch thông tin nhạy cảm (PII) như tên người, số điện thoại, tài khoản ngân hàng không theo quy chuẩn.
    *   *Mục tiêu*: Tiết kiệm chi phí API, giảm độ trễ dưới 20ms và đảm bảo an toàn tuyệt đối thông tin tài chính của doanh nghiệp.

## 3. Tích Hợp Cơ Sở Dữ Liệu Thuế Quốc Gia (GDT)
*   **Hiện trạng**: Luật rủi ro nhà cung cấp (`R-VENDOR-RISK`) đang đối chiếu trên bảng dữ liệu tĩnh nội bộ.
*   **Hạng mục cần làm**:
    *   Thiết lập luồng tự động đồng bộ hàng ngày (Daily Cron job) với danh sách doanh nghiệp rủi ro về hóa đơn của Tổng cục Thuế.
    *   Tích hợp cổng kiểm tra trạng thái MST hoạt động của doanh nghiệp theo thời gian thực (Real-time).

## 4. Hỗ Trợ Giao Dịch Phức Tạp (Multi-item & XML Verification)
*   **Hiện trạng**: Chỉ kiểm tra giao dịch đơn lẻ gồm một hóa đơn/một nội dung chi.
*   **Hạng mục cần làm**:
    *   **Xử lý đa dòng hàng**: Hỗ trợ bóc tách hóa đơn có nhiều dòng sản phẩm khác nhau (loại được trừ thuế và loại không được trừ thuế).
    *   **Xác thực hóa đơn điện tử gốc (XML)**: Đọc file XML hóa đơn điện tử gốc từ Tổng cục Thuế, kiểm tra tính hợp pháp của chữ ký số (Digital Signature) chống sửa đổi hóa đơn giả.

## 5. Kiểm Soát Tranh Chấp Dữ Liệu (Race Conditions)
*   **Hiện trạng**: Hệ thống kiểm tra luật động (như trần quỹ lương phúc lợi) bằng cách truy vấn tổng tiền đã chi.
*   **Hạng mục cần làm**:
    *   Áp dụng cơ chế khóa cơ sở dữ liệu (**Database Transactions Locking** hoặc **Redis Lock**) để xử lý các yêu cầu thanh toán đồng thời tại cùng một thời điểm, tránh ghi nhận sai lệch tổng tiền lũy kế (YTD).
