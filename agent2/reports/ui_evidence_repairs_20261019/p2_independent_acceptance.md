# Phiếu nghiệm thu kế toán độc lập — P2

Trạng thái: **chưa có người nghiệm thu / chưa ký**. Phiếu này được chuẩn bị sẵn, không phải biên bản đã phê duyệt.

Phạm vi: 32 tình huống / 73 giao dịch mô phỏng. Sau khi ký chỉ xác nhận logic/giải thích/giao diện trong phạm vi này; không nghiệm thu chất lượng phát hiện trên SME thật.

- Người rà kế toán độc lập với người phát triển: ____________________
- Người chịu trách nhiệm chốt chính sách / phân xử: ____________________
- Ngày rà và môi trường browser: ____________________
- Phiên bản UI: điền hash trong verification.json của đợt sửa này.
- Nguồn P2: data/p2_controls_20261018_v2; kết quả reports/p2_controls_20261018.
- Biên bản/phê duyệt cuối cùng, người ký và thời điểm: ____________________

Mỗi tình huống cần kiểm tra đủ giao dịch, gồm cả dòng không mở hồ sơ: hiểu căn cứ; tài liệu còn thiếu; thời điểm dữ kiện; mức ưu tiên; thao tác và cách lưu. Ghi lý do và mã bằng chứng trong UI. Nhận xét ASSISTANT_SYNTHETIC_REVIEW và kết quả khớp tự động chỉ là tài liệu tham khảo. Không tính chúng như chữ ký hoặc kết luận của kế toán.

Các tình huống trọng tâm: FUTURE_INVOICE, INSTALL_CASH/MIXED, LIMIT_FUTURE/EXPIRED, LIMIT_FOREIGN, REFUND_FULL/PART và REVERSAL_JOURNAL. Với RR09, ghi quyết định chính sách riêng; không tự đổi điểm.

| Tình huống | Số giao dịch | Kết quả / lý do / chứng từ | Người rà / thời điểm |
|---|---:|---|---|
| FULL_BELOW | 1 | Chưa rà | Chưa có |
| FULL_EQUAL | 1 | Chưa rà | Chưa có |
| FULL_ABOVE | 1 | Chưa rà | Chưa có |
| OLD_BELOW | 1 | Chưa rà | Chưa có |
| OLD_EQUAL | 1 | Chưa rà | Chưa có |
| FULL_BANK | 1 | Chưa rà | Chưa có |
| NO_INVOICE | 1 | Chưa rà | Chưa có |
| NO_DATE | 1 | Chưa rà | Chưa có |
| NO_GROSS | 1 | Chưa rà | Chưa có |
| NO_IDENTITY | 1 | Chưa rà | Chưa có |
| FUTURE_INVOICE | 1 | Chưa rà | Chưa có |
| INSTALL_CASH | 2 | Chưa rà | Chưa có |
| INSTALL_SMALL | 2 | Chưa rà | Chưa có |
| INSTALL_MIXED | 2 | Chưa rà | Chưa có |
| INSTALL_SAME_TIME | 2 | Chưa rà | Chưa có |
| INSTALL_GAP | 2 | Chưa rà | Chưa có |
| REFUND_FULL | 2 | Chưa rà | Chưa có |
| REFUND_PART | 2 | Chưa rà | Chưa có |
| REFUND_BANK | 2 | Chưa rà | Chưa có |
| REVERSAL_JOURNAL | 2 | Chưa rà | Chưa có |
| RECEIPT_UNLINKED | 1 | Chưa rà | Chưa có |
| REFUND_MULTI | 3 | Chưa rà | Chưa có |
| RECUR_SMALL | 3 | Chưa rà | Chưa có |
| RECUR_BANK | 3 | Chưa rà | Chưa có |
| RECUR_CASH | 3 | Chưa rà | Chưa có |
| RECUR_GAP | 3 | Chưa rà | Chưa có |
| RECUR_A5 | 23 | Chưa rà | Chưa có |
| LIMIT_VERIFIED | 1 | Chưa rà | Chưa có |
| LIMIT_UNVERIFIED | 1 | Chưa rà | Chưa có |
| LIMIT_FUTURE | 1 | Chưa rà | Chưa có |
| LIMIT_EXPIRED | 1 | Chưa rà | Chưa có |
| LIMIT_FOREIGN | 1 | Chưa rà | Chưa có |

Trước khi ký, kiểm tra số mẫu đã rà đủ 32/73, không có lỗi chặn còn mở, các bất đồng đã được phân xử và các giới hạn/ngoại lệ được ghi rõ. Nếu còn việc chưa đạt, ghi rõ chấp nhận có điều kiện hay chưa nghiệm thu, phạm vi và người chịu trách nhiệm.

[Bằng chứng trước/sau](before_after.html) · [Phiếu RR09](rr09_policy_decision.md).
