# Đóng góp và bảo trì

## Quy trình một thay đổi

1. Đọc code và tài liệu chuyên trách; xác định hành vi cần sửa cùng tiêu chí kiểm chứng.
2. Thay đổi nhỏ, giữ nguyên phần ngoài phạm vi và thay đổi sẵn có của người khác.
3. Cập nhật tài liệu bị ảnh hưởng **trong cùng thay đổi/PR**, theo bảng dưới. Bug fix phục hồi đúng hành vi đã mô tả có thể không cần sửa tài liệu; phải ghi lý do.
4. Chạy kiểm tra phù hợp, xem diff và điền [mẫu PR](../.github/pull_request_template.md) khi tạo PR. Thiếu đầu vào phải báo phần chưa kiểm chứng.

## Nội dung chính và khi nào cập nhật

| Khi thay đổi | Nơi duy trì chính | Chỉ cập nhật thêm nếu bị ảnh hưởng |
|---|---|---|
| Mục tiêu, phạm vi, trạng thái tích hợp hoặc khả năng chạy | [Project overview](project-overview.md) | README gốc nếu thông tin vào dự án thay đổi |
| Môi trường, dependency, cách bắt đầu | [Getting started](getting-started.md) | Lệnh trong AGENTS và CI nếu thay đổi |
| Thêm, chuyển, đổi tên hoặc xóa file/thư mục quan trọng | [Repository structure](reference/repository-structure.md) | Link/import/config/script gọi đường dẫn đó; mục lục liên quan |
| Nguồn dữ liệu, snapshot, điều kiện sử dụng | `data/Tn/README.md` của task | `data/README.md` khi thêm task; manifest/nhật ký nguồn tại `research/references/` |
| Field, mapping, nhãn, cutoff, feature, censoring | Hợp đồng dữ liệu của task tương ứng trong `reference/` (ví dụ: [T1](reference/t1-data-contracts.md)) | Adapter/audit và báo cáo nghiên cứu liên quan |
| Lệnh/đầu ra/quy tắc audit dữ liệu | Hướng dẫn audit của task hoặc nguồn tương ứng trong `how-to/` (ví dụ: [audit T1](how-to/audit-t1-data.md)) | `data/Tn/README.md` của task; script và JSON thống kê khi cần tái lập |
| Thứ tự, đầu vào/đầu ra notebook và nguồn dùng chung | [Notebook README](../notebooks/README.md) | Hợp đồng dữ liệu của task tương ứng nếu ý nghĩa dữ liệu đổi; overview nếu đổi khả năng chạy |
| Kiến trúc, nhiệm vụ, quyết định quan trọng | Tài liệu tương ứng trong `explanation/`; quyết định có đánh đổi tại `decisions/` | Overview nếu đổi phạm vi thực tế |
| Kết quả thí nghiệm, đánh giá nguồn hoặc khuyến nghị phương pháp | Báo cáo phù hợp trong `docs/reports/` hoặc `research/notes/` | Bằng chứng cấu hình, dữ liệu và artifact tại `research/references/` |
| Quy trình làm việc hoặc lệnh kiểm tra | Trang này | `AGENTS.md`, CI và mẫu PR nếu hướng dẫn tương ứng đổi |

Mỗi hợp đồng dữ liệu và hướng dẫn audit phải ghi rõ phạm vi task/nguồn áp dụng. Khi bổ sung task hoặc nguồn mới, cập nhật tài liệu phù hợp hoặc tạo trang riêng nếu chưa có, rồi liên kết từ mục lục; không mặc định dùng schema, nhãn hoặc quy tắc audit của task khác. Các liên kết T1 trong bảng là ví dụ tài liệu hiện có.

Người sửa chịu trách nhiệm các tài liệu bị ảnh hưởng. Reviewer kiểm tra sự khớp giữa code, tài liệu và bằng chứng. Không cần sửa mọi README cho một thay đổi; dùng liên kết để tránh nhiều bản của cùng một sự thật.

## Quy ước nội dung

- Viết tiếng Việt, giữ tên field/API/thuật toán đúng mã nguồn. Dùng Markdown UTF-8 và link tương đối cho file trong repo.
- Tên tài liệu mới dùng `kebab-case.md`; giữ `README.md`, `CONTRIBUTING.md`, `AGENTS.md` theo vai trò. Không đổi tên notebook, script hoặc artifact chỉ để đồng nhất hình thức.
- README làm điểm vào/mục lục; hướng dẫn chứa bước thao tác; reference chứa quy ước/field; explanation chứa lý do và thiết kế. Chưa có tutorial chạy trọn vẹn thì chưa tạo thư mục tutorial rỗng.
- Báo cáo phải ghi ngày và phạm vi kiểm chứng. Giữ kết quả lịch sử theo snapshot; sửa kết luận cũ bằng đính chính có bằng chứng, không thay metric bằng số chưa chạy.
- Chỉ lưu quyết định khi có bối cảnh, lựa chọn và hệ quả cần tra cứu. Không tạo nhật ký hoặc file tóm tắt mới cho từng lần sửa nhỏ.
- `AGENTS.md` chỉ giữ quy tắc quan trọng và liên kết; không chép cây thư mục, toàn bộ schema, số liệu dataset hoặc nội dung báo cáo vào đó.

[Quyết định tổ chức tài liệu](decisions/0001-documentation-structure.md) ghi các hướng dẫn chính thức và phạm vi điều chỉnh cho repo này.

## Kiểm tra và điều kiện hoàn thành

Tất cả thay đổi chạy hai lệnh không cần dữ liệu:

```powershell
python scripts/checks/check_docs.py
python -m unittest discover -s tests -v
```

Checker kiểm tra file tài liệu bắt buộc và link tới file/thư mục trong Markdown, bỏ qua ví dụ trong code. Nó không kiểm tra URL trên mạng, heading anchor hoặc tính đúng của nội dung. CI tự chạy hai lệnh này; việc tài liệu phản ánh đúng thay đổi code vẫn cần người sửa và reviewer kiểm tra.

| Phạm vi sửa | Kiểm tra bổ sung |
|---|---|
| Tài liệu/đổi đường dẫn | Các đường dẫn gọi file liên quan; không cần train lại |
| Downloader/audit/adapter | Fixture kiểm chứng hành vi thay đổi; hash/count/schema và gate nếu thay logic audit. Chạy audit đầy đủ khi có dữ liệu và thay đổi cần kiểm chứng trên toàn bộ nguồn. |
| Snapshot/feature/survival/metric | Ca biên về cutoff, censoring, ngày/số tiền, invariant và chống leakage; thêm regression test khi sửa lỗi logic. |
| Huấn luyện/hiệu chỉnh/mô phỏng | Kiểm tra theo thời gian, baseline và metric tương ứng; ghi seed, cấu hình, môi trường, snapshot và artifact. Không dùng test để tune. |

Notebook 11/12: sửa `.py` trước rồi dựng bằng lệnh trong [Notebook README](../notebooks/README.md) nếu thay đổi nguồn và có đủ đầu vào. Nếu chưa thể chạy, ghi rõ `.ipynb` chưa dựng lại và output là lịch sử trong phần ghi chú notebook/README liên quan cùng bàn giao. Không chỉnh output để tạo cảm giác đã chạy. Với 01–10, `.ipynb` là nguồn chính; tránh diff metadata/output không liên quan.

Một thay đổi hoàn thành khi hành vi được kiểm chứng phù hợp, tài liệu liên quan đã đồng bộ, không còn link nội bộ bị gãy và phần chưa chạy được công bố rõ.
