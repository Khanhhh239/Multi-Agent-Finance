# Agent 3: Trợ lý thuế cho doanh nghiệp nhỏ và vừa

Đọc hóa đơn điện tử XML, đối chiếu sao kê ngân hàng và bảng kê cổng thuế, báo các hóa đơn có nguy cơ bị loại khấu trừ GTGT, kèm điều khoản luật làm căn cứ. Phần tính tiền và kết luận là quy tắc xác định; AI chạy trên máy chỉ đề xuất, người duyệt quyết định, mọi quyết định đều được ghi nhật ký. Dữ liệu không rời khỏi máy.

- Tài liệu mô tả và hướng dẫn đầy đủ: [tai_lieu/AGENT3_MO_TA_VA_HUONG_DAN.pdf](tai_lieu/AGENT3_MO_TA_VA_HUONG_DAN.pdf) (bản nguồn: `.md` cùng thư mục)
- Demo từng bước, dữ liệu mô phỏng: [demo/DN_Phan_mem_Sao_Viet/HUONG_DAN.md](demo/DN_Phan_mem_Sao_Viet/HUONG_DAN.md)

## Yêu cầu

- Windows 10 hoặc 11, Python 3.10 trở lên.
- [Ollama](https://ollama.com) cho phần AI và hỏi đáp (phần kiểm tra hóa đơn vẫn chạy khi không có Ollama).
- Máy có GPU 6 GB trở lên cho kết quả nhanh; chạy bằng CPU vẫn được nhưng chậm.
- Node.js chỉ cần khi sửa giao diện (`webui/`); bản đã build nằm sẵn trong `src/assistant/static`.

## Cài đặt (làm một lần)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Tải mô hình cho Ollama (khoảng 10 GB):

```bash
ollama pull qwen3:8b
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull bge-m3
```

Mô hình xếp hạng lại điều luật (tùy chọn, tăng độ chính xác tìm điều luật từ 39 lên 45 trên 54 câu thử). Không có thì hệ thống tự bỏ qua bước này:

```bash
.venv\Scripts\python -m huggingface_hub.commands.huggingface_cli download AITeamVN/Vietnamese_Reranker --local-dir models/Vietnamese_Reranker
```

Kho luật (tải văn bản thuế từ vbpl.vn, tách theo điều khoản, rồi tính vectơ; cần mạng, làm một lần):

```bash
.venv\Scripts\python -m src.lawbase.cli sync
.venv\Scripts\python -m src.lawbase.dense build
```

## Chạy

Bấm đúp `chay_agent3.bat`, hoặc:

```bash
.venv\Scripts\python -m src.assistant.web
```

Mở http://127.0.0.1:8640 và giữ cửa sổ dòng lệnh mở trong lúc dùng.

## Dùng thử trong 10 phút

1. Bấm biểu tượng bánh răng, đặt mật khẩu quản trị (chỉ cần khi sửa cấu hình).
2. Thêm doanh nghiệp theo bảng trong `demo/DN_Phan_mem_Sao_Viet/HUONG_DAN.md`.
3. Kéo cả 6 tệp trong `demo/DN_Phan_mem_Sao_Viet/A_tha_vao_Nap_nhanh/` vào trang **Nạp dữ liệu**. Kết quả đúng: 22 tệp, 12 việc, thuế có nguy cơ 17.400.000 đồng.
4. Làm tiếp các bước 4 đến 7 trong `HUONG_DAN.md` (danh sách rủi ro, xử lý việc, AI, hỏi đáp).

## Kiểm thử

```bash
.venv\Scripts\python -m pytest tests/assistant tests/lawbase tests/xml_v1 -q
```

Lần chạy gần nhất: 137 test đạt. Chạy riêng bộ đo bộ định tuyến câu hỏi: `python -m src.assistant.chat.evaluate dev`.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `src/assistant/` | Ứng dụng web (FastAPI), nạp tệp, phân tích, quản trị, trợ lý hỏi đáp (`chat/`) |
| `src/lawbase/` | Kho luật: tải, tách điều khoản, tìm kiếm lai, xếp hạng lại, kiểm tra trích dẫn |
| `rules/`, `configs/` | Luật rủi ro và danh mục cấu hình (quy định chi tiêu, ngày nghỉ, loại câu hỏi) |
| `webui/` | Mã nguồn giao diện (Vite); `npm install && npm run build` ghi vào `src/assistant/static` |
| `tests/` | Kiểm thử tự động |
| `demo/`, `tai_lieu/` | Dữ liệu demo và tài liệu |

## Giới hạn đã biết

- Hỏi đáp luật mất 30 đến 60 giây mỗi câu; 6 câu thử không trả lời được thì trả nguyên văn điều khoản thay vì tự diễn giải.
- Lịch nghỉ lễ 2026 chưa đối chiếu với thông báo chính thức của Bộ Nội vụ.
- Chưa có dữ liệu thật và chưa có chuyên gia thuế rà soát; kết quả chỉ để tham khảo, không thay kết luận của cơ quan thuế.
