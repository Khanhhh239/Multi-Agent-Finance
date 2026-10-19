# 0001 — Tổ chức tài liệu và cập nhật cùng code

- Ngày: 2026-10-19
- Trạng thái: Áp dụng trong repo

## Bối cảnh

Repo kết hợp notebook, thiết kế sản phẩm và nghiên cứu nguồn dữ liệu. Nhiều trang tóm tắt cùng nội dung dễ lệch trạng thái, trong khi kết quả lịch sử cần giữ để tra cứu.

## Quyết định

Giữ một nơi duy trì chính cho mỗi nội dung, chỉ định tại [Contributing](../CONTRIBUTING.md). README dẫn đường, `project-overview.md` ghi trạng thái hiện tại, `AGENTS.md` giữ quy tắc hành động ngắn. Tài liệu bị ảnh hưởng cập nhật cùng code; checker/CI kiểm tra lỗi cơ học, reviewer kiểm tra ngữ nghĩa.

| Hướng dẫn chính thức | Áp dụng trong repo |
|---|---|
| [AGENTS.md](https://agents.md/) | Hướng dẫn AI ở gốc, tập trung bối cảnh cần thiết, quy ước và lệnh kiểm tra. |
| [GitHub — README](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) và [contribution guidelines](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors) | README ngắn, link tương đối; `CONTRIBUTING.md` trong `docs/` và mẫu PR. |
| [Diátaxis](https://www.diataxis.fr/start-here/) | Phân biệt hướng dẫn thao tác, reference và explanation. Chỉ thêm tutorial khi có bài thực hành đủ điều kiện chạy. |
| [Write the Docs — Docs as Code](https://www.writethedocs.org/guide/docs-as-code/) | Tài liệu được version/review cùng code và kiểm tra tự động. |
| [arc42 — overview](https://arc42.org/overview/) | Các câu hỏi về mục tiêu, phạm vi, ràng buộc, quyết định và rủi ro định hướng tài liệu kiến trúc; liên kết tới thiết kế chi tiết. |

Đây là vận dụng hướng dẫn cộng đồng, không phải chứng nhận tuân thủ tiêu chuẩn ISO. Tên file, cây thư mục và bảng cập nhật tài liệu là quy ước dự án; các nguồn trên không bắt buộc một cây thư mục duy nhất.

## Hệ quả

Giảm việc chép schema, số liệu và trạng thái giữa nhiều trang. Giữ báo cáo có ngày/phạm vi, chuyển snapshot cũ vào `archive/`. Sửa link khi chuyển file. Không thêm nhiều README, bản tổng kết hoặc công cụ build tài liệu khi chưa phục vụ nhu cầu cụ thể.
