# Sửa R02 — B2 giữ nhân viên ở công ty cũ — 24/10/2026

**Đã sửa trong mã nguồn.** Khi master ghi nhận nhân viên chuyển C001 → C002, giao dịch C001 sau thời điểm chuyển không còn nhận 3 điểm B2 chỉ vì điện thoại hoặc địa chỉ của người đã chuyển. Công ty mới vẫn nhận diện đúng người đó; kết quả của giao dịch trước ngày chuyển giữ nguyên.

Tại [rules.py](../sme_fraud/rules.py), bản sửa thực hiện ba việc:

1. Gỡ bank account, phone, address và national ID khỏi chỉ mục dùng `old.company_id`, rồi thêm định danh hiện hành vào công ty mới.
2. Kiểm tra lại công ty hiện hành của nhân viên trước khi đưa ID vào `B2.direct_matches`.
3. Khi master đổi công ty, kết thúc các cạnh master bank/phone/representative ở công ty cũ tại đúng `recorded_at`. Dấu kết thúc có ưu tiên master để liên kết mirror cùng thời điểm hoặc cũ hơn không khôi phục cạnh đã hết hiệu lực.

Điểm thứ ba cần thiết vì kiểm tra bổ sung tái hiện được trường hợp: sau khi sửa chỉ mục trực tiếp, graph vẫn đi qua nhân viên đã chuyển rồi tới nhân viên C001 khác và cộng **8 điểm B2**. Bản sửa cuối cùng chặn cả đường này. Đồ thị được xử lý theo thời gian nên không xóa bằng chứng của cảnh báo đã phát hiện trước thời điểm chuyển.

| Ca kiểm tra | Kết quả sau sửa |
|---|---|
| Giao dịch C001 trước chuyển; trùng điện thoại, tắt graph để đo khớp trực tiếp | Giữ 3 điểm B2 và nguyên hit lịch sử |
| Giao dịch C001 sau chuyển; chỉ trùng người đã chuyển | 0 điểm B2, không còn hit B2 do người đó |
| Giao dịch C002 sau chuyển; trùng cùng người đó | 3 điểm B2 từ khớp trực tiếp |
| Graph C001 đi qua người đã chuyển tới nhân viên còn ở C001 | Không còn hit B2 từ đường cũ |
| C001 vẫn có nhân viên hiện hành khác trùng thông tin | Vẫn có cảnh báo cho người còn ở C001 |
| Nhân viên chuyển về C001 | Khớp được khôi phục ở C001, không giữ khớp cũ tại C002 |

[Tái hiện C001 → C002 sau sửa](b2_company_transfer_fix_20261024/reproduction_after.json). [Bằng chứng đường graph còn sót trước khi gỡ cạnh](b2_company_transfer_fix_20261024/graph_bridge_before.json), [kết quả sau sửa đầy đủ](b2_company_transfer_fix_20261024/graph_bridge_after.json). Các điểm nêu trên là đóng góp B2, không phải tổng điểm hồ sơ hoặc kết luận gian lận.

Đã thêm [12 kiểm thử hồi quy](../tests/test_b2_company_transfer.py), gồm phone/address, hai chế độ policy, nhận diện ở công ty mới, chuyển về công ty cũ, thay/xóa thông tin, ranh giới đúng thời điểm chuyển, bảo toàn lịch sử, nhân viên trùng thông tin còn ở lại, chỉ mục B1 legacy và đường graph/mirror. Trước sửa, 9 kiểm thử ban đầu có 14 lỗi assertion/subtest, không lỗi chạy. Sau sửa chỉ mục, hai kiểm thử graph bổ sung còn thất bại; bản sửa cuối cùng đạt toàn bộ.

**Kết quả cuối cùng: 137 kiểm thử thuộc 8 module đạt, 0 thất bại, 0 lỗi chạy, 0 bỏ qua.** Các module: `test_b2_company_transfer` (12), `test_graph_history` (16), `test_bank_identity_controls` (21), `test_spec_policy` (26), `test_noise_policy` (17), `test_rule_repairs` (24), `test_b4_evidence_timing` (9), `test_rules` (12). [Kết quả cuối cùng](b2_company_transfer_fix_20261024/final_fix.json), [log cuối cùng](b2_company_transfer_fix_20261024/final_fix.log). Đây là hồi quy phù hợp với bản sửa này, không phải chạy lại toàn bộ bộ kiểm thử dự án.

[Kiểm tra bảo toàn](b2_company_transfer_fix_20261024/verification.json) xác nhận **2.283 tệp đã khóa không đổi checksum**, gồm bằng chứng B4 vừa bàn giao. Mã hiện có chỉ thay đổi `sme_fraud/rules.py`, thêm một tệp test mới; đối chiếu ngược xác nhận thay đổi trong `rules.py` chỉ gồm ba phần sửa phạm vi công ty nêu trên. Bản sửa B4 được giữ nguyên và 9 kiểm thử B4 đều đạt. Feature contract ML không đổi; không huấn luyện model, không chấm lại nguồn/holdout hoặc ghi đè hàng đợi, shadow hay phiếu rà đã khóa.

Bản sửa áp dụng cho lượt chạy engine mới. Chưa phát hành lại app hoặc tái tạo kết quả đã chốt. Lượt này không sửa feature ML và không đóng các hạng mục M01–M03, RR09 còn lại trong báo cáo rà soát trước.
