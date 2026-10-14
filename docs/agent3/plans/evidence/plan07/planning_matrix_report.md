# Ma trận quyết định và bằng chứng kỹ thuật

Nguồn tái hiện: `tests/planning/test_planning.py`. Số test thực chạy nằm ở [validation_summary.json](validation_summary.json). Các test dùng luật/bằng chứng tổng hợp để kiểm logic; không đo accuracy OCR hoặc độ đúng pháp lý của catalog.

| Điều kiện | Kết quả kỳ vọng |
|---|---|
| Ngày thiếu/ambiguous | Không chọn version; UNKNOWN applicability, không gọi engine |
| Ngày ngoài support | Lý do ngoài lịch sử hỗ trợ |
| Timeline gap/overlap | NOT_EVALUATED_PLANNING_ERROR |
| Rule DRAFT hoặc legal locator chưa reviewed | NOT_EVALUATED_PLANNING_ERROR, không ELIGIBLE/NOT_APPLICABLE giả |
| Applicability NO_MATCH đã chứng minh, rule được duyệt | NOT_APPLICABLE |
| Applicability UNKNOWN, capability SUPPORTED | UNKNOWN_APPLICABILITY và hướng dẫn review |
| Applicability UNKNOWN, capability UNSUPPORTED | UNKNOWN_APPLICABILITY và COLLECT_OTHER_SOURCE; không scope-exclude giả |
| Applicability MATCH, capability UNSUPPORTED | OUT_OF_SCOPE_FOR_SOURCE |
| Capability chưa xác định | Planning error, không chạy engine |
| MATCH, SUPPORTED, field missing/low-confidence/invalid | Blocker đúng nguyên nhân; chưa ELIGIBLE |
| Tất cả điều kiện đủ, rule tổng hợp approved | ELIGIBLE là đủ điều kiện chạy sau này; chưa có verdict |
| OCR trống hoặc observation sai revision/profile | Không chứng minh CONFIRMED_ABSENT |
| Một hóa đơn dưới 5 triệu, ledger chưa đủ | UNKNOWN, không tự NOT_APPLICABLE |
| Tổng đầy đủ cùng supplier/ngày đạt ngưỡng | MATCH với proof phiên bản ledger |
| Taxonomy chỉ có VAT rate hoặc mapping hết hạn | Review, không suy nhóm pháp lý |
| KCT, KKKNT, rate 0; reorder items | Semantics và identity nhóm riêng; identity không đổi khi reorder |
| Items trống, discovery chưa đủ | Discovery blocker; không vacuous PASS |
| Cross-tenant hoặc quality/hash/revision lệch | Từ chối trước lập/lưu plan |
| Replay/idempotency/audit lỗi | Replay pin snapshot+code; không artifact trùng; audit lỗi rollback |

Ngoài các ca riêng còn có ma trận 18 tổ hợp applicability × capability × input-missing. Các case đặc biệt gồm số âm, tiền khác VND, SPECIAL payment policy chưa hỗ trợ, ledger sai current revision, threshold literal kiểu float/NaN và predicate sai kiểu. Không tự ghép MST 13 số với MST 10 số theo prefix; quan hệ đơn vị phụ thuộc cần master relation tin cậy ở tích hợp tiếp theo.
