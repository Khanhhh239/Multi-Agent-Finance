# Dữ liệu của dự án

Dữ liệu local hiện có phục vụ **T1 — dự báo thời điểm thanh toán hóa đơn**, được gom trong [T1/](T1/README.md). Chưa có dataset riêng cho T2–T8.

```text
data/
  README.md
  T1/
    README.md
    raw/        # Dữ liệu gốc và thông tin nguồn tải
    interim/    # Bảng kiểm tra, chưa phải bộ train hoàn chỉnh
```

Khi có dữ liệu riêng cho task khác, tạo nhánh `T2/`, `T3/`… tương ứng. Một nguồn có thể hỗ trợ nhiều task, nhưng chỉ dùng để đánh giá task khác khi có nhãn và phạm vi phù hợp; không cần sao chép dữ liệu sang nhiều nhánh.

Notebook cũ vẫn yêu cầu `data/dataset.csv` và xuất `data/processed/`. Hai đường dẫn đó hiện chưa có dữ liệu; bộ Séc trong `T1/` chưa được nối vào pipeline notebook. Các file dữ liệu lớn trong `raw`, `interim`, `processed` được loại khỏi Git bằng `.gitignore`.
