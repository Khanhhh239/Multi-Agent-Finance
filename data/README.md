# Dữ liệu của dự án

Dữ liệu được chia theo task:

- [T0](T0/README.md): BenchRec GL–bank giữ benchmark riêng; v0.4 có AR/flow khác ngày, FX theo quote, refund–bank, ledger nhiều phiên bản và journal theo policy, bên cạnh AP FinRCA/payout–bank/statement/Gold và gate chất lượng. `examples/v04` là fixture tổng hợp để chạy CLI. Chưa có invoice–bank SME được gán nhãn độc lập.
- [T1](T1/README.md): nguồn hóa đơn công khai và bảng audit; chưa phải đầu vào train hoàn chỉnh.

Chưa có dataset riêng cho T2–T8. Xem [cấu trúc repository](../docs/reference/repository-structure.md) để tìm thư mục.

Khi có dữ liệu riêng cho task khác, tạo nhánh tương ứng. Một nguồn có thể hỗ trợ nhiều task, nhưng chỉ dùng để đánh giá task khác khi có nhãn và phạm vi phù hợp; không cần sao chép dữ liệu sang nhiều nhánh.

Notebook cũ vẫn yêu cầu `data/dataset.csv` và xuất `data/processed/`. Hai đường dẫn đó hiện chưa có dữ liệu; bộ Séc trong `T1/` chưa được nối vào pipeline notebook. Các file dữ liệu lớn trong `raw`, `interim`, `processed` được loại khỏi Git bằng `.gitignore`.
