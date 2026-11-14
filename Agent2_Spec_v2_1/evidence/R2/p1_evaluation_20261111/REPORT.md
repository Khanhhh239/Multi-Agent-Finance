# CR-019 — nối evaluator P1

Đã hoàn tất phần backend được giao: P1 đối chiếu thanh toán trước, nhóm đồng thời và điều chỉnh có dấu từ nguồn CR-018. R2 tổng thể **PARTIAL**, chưa nghiệm thu toàn pipeline/production.

- **640 kiểm thử hồi quy pass**, 0 lỗi/thất bại/bỏ qua, 657.524 giây: [JSON](native_tests.json), [log](native_tests.log). Gồm 24 ca P1 mới; [68 focused](focused_tests.json) qua, exit 0.
- [Native parity](native_parity.json): 8 tình huống/16 dòng khớp điểm/matched và tổng/điểm/phần vượt của nhóm; có lịch sử 45 ngày, tiền mặt/chuyển khoản, dung sai 1 VND và đồng thời. Miền dương/một hóa đơn; kernel cũ không nhận số âm, không tuyên bố parity ngoài miền này.
- [Demo](demo/summary.json): 5 tình huống, 13/13 dòng. Trả trước gây vượt → row 20; chỉ nhóm đồng thời vượt → row 0, kiểm nhóm 20; giảm âm hợp lệ → giảm số ròng; giảm biết muộn không sửa quá khứ; thiếu lịch sử → unavailable/null. Upload/preview/commit/retry không tạo snapshot trùng.
- [Demo đầu vào cũ](input_demo/summary.json) với evaluator mới vẫn 6/6. [Kiểm schema/thời gian](demo_validation.json) trên tổng 19 dòng của sáu tệp đều qua; mỗi dòng đủ 35 RuleResult và refs không vượt cutoff/event.

P1 dùng allocation amount, không lặp tiền giao dịch cho nhiều hóa đơn. Revision thay thế; adjustment là delta có dấu tính một lần. Kiểm chuỗi phân bổ/giao dịch gốc, revision, thời gian, dấu, cùng nghĩa vụ, over-reversal và phân bổ vượt tiền. Điều chỉnh thiếu phân bổ đúng nghĩa vụ trả unavailable, không bị bỏ qua.

Giữ native P1=20, total > cap+1 VND và row hit cần thanh toán trước. Khoản đầu tiên vượt cap chưa tự thành row hit P1; no-hit không xác nhận hợp lệ. details.simultaneous_checks tách khỏi row score; các dòng có thể tham chiếu cùng group_id, chưa phát event/queue và không cộng điểm nhóm vào row/tổng.

Giữ khóa DN/NCC/số hóa đơn chuẩn hóa, alias không nhân trần; giá trị mâu thuẫn hoặc alias thiếu coverage → unavailable. Credit note/điều chỉnh hóa đơn có liên kết gốc là delta có dấu; cap không xác định/không dương không tự suy. Nguồn chỉ dùng tại cutoff riêng, không nâng cutoff quá khứ theo global as_of.

Coverage complete/since_inception ràng buộc manifest là nguồn khai báo, không xác minh đầy đủ sổ bên ngoài. Thiếu/partial/unknown/bounded/stale vẫn unavailable. E3/P1 có evaluator; tổng rules vẫn rules_incomplete/null. Không đổi feature, kernel/model, trọng số/active hoặc fit nghiệp vụ; không mở UI/queue/R3 hoặc chốt D-03/04/09.

[Hướng dẫn](../../../../agent2/docs/P1_EVALUATION.md), [provenance](provenance.json), [bảo toàn kernel/model/schema/33 feature](preservation.json). Hai lỗi fixture trong focused đầu và log lượt hồi quy bị ngắt để sửa case điều chỉnh khác hóa đơn vẫn được giữ; lượt cuối đã chạy đầy đủ. Log PowerShell chỉ chuyển encoding sang UTF-8, không sửa nội dung. Evidence CR-018 cũ giữ nguyên; prior_R2_* lưu overview/index/map trước cập nhật.
