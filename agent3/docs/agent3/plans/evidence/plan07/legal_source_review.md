# Đối chiếu nguồn pháp lý PLAN_07

Ngày đối chiếu: 14/10/2026. Chỉ đánh dấu `PDF_REVIEWED` cho các locator cụ thể đã xem bản PDF; không có nghĩa toàn văn, chữ ký hoặc toàn bộ ngoại lệ đã được duyệt. Rule thực tế đều `DRAFT`.

Các số trang dưới đây là trang PDF tính từ 1, không phải số trang Công báo. Hash từng nguồn và quan hệ văn bản được lưu tại [Legal Registry](../../../../../agent3_tax_compliance/rules/registry/legal_registry_v1.json). Bản tải và manifest local: `agent3_tax_compliance/data/plan07/legal/`.

| Văn bản | Đối chiếu thực hiện | Giới hạn |
|---|---|---|
| [NĐ 254/2026](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf) | Trang 21: Điều 10, nội dung hóa đơn. Trang 16: Điều 9 là thời điểm lập. Trang 46: Điều 43 hiệu lực 01/07/2026, thay NĐ123, NĐ70 và chỉ Điều 1 NĐ41/2022 | Điều 44 bắt đầu trang 46; chưa duyệt hết chuyển tiếp/ngoại lệ, chưa publish rule |
| [NĐ 181/2025](https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/181nd.signed.pdf) | Điều 26 trang 32–34: non-cash và tổng mua cùng nhà cung cấp/cùng ngày | Phải ghép sửa đổi 359/2025 và 144/2026; chưa duyệt đầy đủ mọi trường hợp đặc biệt |
| [NĐ 144/2026](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/144-ndcp.signed.pdf) | Trang 3: Điều 4 sửa điểm g khoản 2 Điều 26; Điều 6 hiệu lực 20/06/2026 | Không coi ngày ban hành là ngày hiệu lực; các phụ lục chưa được chuyển thành mapping đã duyệt |
| [TT 91/2026](https://vanban.chinhphu.vn/?docid=219006&pageid=27160) | Điều 25 trang 32: hiệu lực 01/07/2026, TT32/2025 hết hiệu lực | Chuyển tiếp và mọi nghĩa vụ chi tiết vẫn cần rà đầy đủ |
| [NĐ 123/2020](https://vanban.chinhphu.vn/default.aspx?docid=201365&pageid=27160), [NĐ 70/2025](https://vanban.chinhphu.vn/?docid=213179&pageid=27160), [TT78/2021](https://vanban.chinhphu.vn/?docid=204200&pageid=27160), [TT32/2025](https://chinhphu.vn/?classid=1&docid=213855&orggroupid=4&pageid=27160) | Đã tải nguồn, giữ lịch sử rule | Chưa duyệt đầy đủ locator lịch sử; quan hệ chưa xác minh không tự thêm |
| [NĐ 359/2025](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-359-2025-nd-cp-468511.htm) | Đã tải PDF qua liên kết Công báo, hash trong registry | Chưa đối chiếu đầy đủ sửa đổi; phiên bản non-cash liên quan vẫn DRAFT |
| [NĐ 174/2025](https://congbao.chinhphu.vn/tai-ve-van-ban-so-174-2025-nd-cp-45374-57334?format=pdf) | Đã tải PDF kèm phụ lục | Chưa có mappings mã hàng hóa/dịch vụ được duyệt; không suy từ observed VAT rate |
| [Luật 108/2025/QH15](https://vanban.chinhphu.vn/?docid=216541&pageid=27160) | Đã tải nguồn | Chưa duyệt locator áp dụng cho từng rule |
| NĐ 41/2022 | Chỉ ghi quan hệ bãi bỏ Điều 1 theo Điều 43 NĐ254 | REFERENCED_ONLY; không có hash bản độc lập, không tuyên bố bãi bỏ toàn văn |

Draft lấy ý kiến sửa NĐ181 trong tháng 10/2026 không được đưa thành luật đang có hiệu lực. Việc tải PDF không thay kiểm tra nội dung, quyền sử dụng, chữ ký số hay phê duyệt nghiệp vụ. Registry hiện phục vụ truy nguyên và chặn rule chưa đủ căn cứ.
