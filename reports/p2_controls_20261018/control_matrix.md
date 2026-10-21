# Ma trận đối chứng P2 đã khai báo trước

Khóa tổng hợp là `(control_id, transaction_id)`. Kỳ vọng được khóa trong nguồn trước khi chấm, không điều chỉnh theo kết quả detector.

| Mã | Nhóm | Tình huống | Số giao dịch | Kỳ vọng P2 | Nguồn / Kết quả |
| --- | --- | --- | ---: | --- | --- |
| `FULL_BELOW` | Hóa đơn đầy đủ | Hóa đơn đủ, dưới ngưỡng đối chiếu | 1 | 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/FULL_BELOW/tables.json) / [Kết quả](FULL_BELOW/predictions.json) |
| `FULL_EQUAL` | Hóa đơn đầy đủ | Hóa đơn đủ, đúng ngưỡng đối chiếu | 1 | 1 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/FULL_EQUAL/tables.json) / [Kết quả](FULL_EQUAL/predictions.json) |
| `FULL_ABOVE` | Hóa đơn đầy đủ | Hóa đơn đủ, trên ngưỡng đối chiếu | 1 | 1 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/FULL_ABOVE/tables.json) / [Kết quả](FULL_ABOVE/predictions.json) |
| `OLD_BELOW` | Hóa đơn đầy đủ | Mốc lịch sử: dưới ngưỡng phiên bản cũ | 1 | 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/OLD_BELOW/tables.json) / [Kết quả](OLD_BELOW/predictions.json) |
| `OLD_EQUAL` | Hóa đơn đầy đủ | Mốc lịch sử: đúng ngưỡng phiên bản cũ | 1 | 1 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/OLD_EQUAL/tables.json) / [Kết quả](OLD_EQUAL/predictions.json) |
| `FULL_BANK` | Hóa đơn đầy đủ | Hóa đơn đủ, trả qua ngân hàng | 1 | 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/FULL_BANK/tables.json) / [Kết quả](FULL_BANK/predictions.json) |
| `NO_INVOICE` | Thiếu chứng từ | Không có thông tin hóa đơn | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/NO_INVOICE/tables.json) / [Kết quả](NO_INVOICE/predictions.json) |
| `NO_DATE` | Thiếu chứng từ | Thiếu ngày hóa đơn | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/NO_DATE/tables.json) / [Kết quả](NO_DATE/predictions.json) |
| `NO_GROSS` | Thiếu chứng từ | Thiếu tổng tiền hóa đơn | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/NO_GROSS/tables.json) / [Kết quả](NO_GROSS/predictions.json) |
| `NO_IDENTITY` | Thiếu chứng từ | Thiếu mã và số hóa đơn | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/NO_IDENTITY/tables.json) / [Kết quả](NO_IDENTITY/predictions.json) |
| `FUTURE_INVOICE` | Thiếu chứng từ | Hóa đơn chỉ có sau lúc chi | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/FUTURE_INVOICE/tables.json) / [Kết quả](FUTURE_INVOICE/predictions.json) |
| `INSTALL_CASH` | Trả nhiều đợt | Hai đợt tiền mặt nhỏ thuộc một hóa đơn lớn | 2 | 2 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/INSTALL_CASH/tables.json) / [Kết quả](INSTALL_CASH/predictions.json) |
| `INSTALL_SMALL` | Trả nhiều đợt | Hai đợt nhỏ, hóa đơn tổng dưới ngưỡng | 2 | 2 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/INSTALL_SMALL/tables.json) / [Kết quả](INSTALL_SMALL/predictions.json) |
| `INSTALL_MIXED` | Trả nhiều đợt | Một đợt ngân hàng và một đợt tiền mặt | 2 | 1 × Không P2; 1 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/INSTALL_MIXED/tables.json) / [Kết quả](INSTALL_MIXED/predictions.json) |
| `INSTALL_SAME_TIME` | Trả nhiều đợt | Hai khoản cùng thời điểm dùng cùng hóa đơn | 2 | 2 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/INSTALL_SAME_TIME/tables.json) / [Kết quả](INSTALL_SAME_TIME/predictions.json) |
| `INSTALL_GAP` | Trả nhiều đợt | Có tổng hóa đơn nhưng chưa có ngày phát hành | 2 | 2 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/INSTALL_GAP/tables.json) / [Kết quả](INSTALL_GAP/predictions.json) |
| `REFUND_FULL` | Hoàn/đảo | Hoàn đủ tiền mặt sau khoản chi | 2 | 1 × Đối chiếu · 8 điểm; 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/REFUND_FULL/tables.json) / [Kết quả](REFUND_FULL/predictions.json) |
| `REFUND_PART` | Hoàn/đảo | Hoàn một phần tiền mặt | 2 | 1 × Đối chiếu · 8 điểm; 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/REFUND_PART/tables.json) / [Kết quả](REFUND_PART/predictions.json) |
| `REFUND_BANK` | Hoàn/đảo | Hoàn khoản chi qua ngân hàng | 2 | 2 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/REFUND_BANK/tables.json) / [Kết quả](REFUND_BANK/predictions.json) |
| `REVERSAL_JOURNAL` | Hoàn/đảo | Đảo bút toán, không có khoản chi mới | 2 | 1 × Đối chiếu · 8 điểm; 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/REVERSAL_JOURNAL/tables.json) / [Kết quả](REVERSAL_JOURNAL/predictions.json) |
| `RECEIPT_UNLINKED` | Hoàn/đảo | Thu tiền mặt chưa nối chứng từ gốc; không phải chi | 1 | 1 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/RECEIPT_UNLINKED/tables.json) / [Kết quả](RECEIPT_UNLINKED/predictions.json) |
| `REFUND_MULTI` | Hoàn/đảo | Hai lần hoàn một phần, giữ bằng chứng khoản gốc | 3 | 1 × Đối chiếu · 8 điểm; 2 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/REFUND_MULTI/tables.json) / [Kết quả](REFUND_MULTI/predictions.json) |
| `RECUR_SMALL` | Định kỳ | Định kỳ đã duyệt, tiền mặt dưới ngưỡng | 3 | 3 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/RECUR_SMALL/tables.json) / [Kết quả](RECUR_SMALL/predictions.json) |
| `RECUR_BANK` | Định kỳ | Định kỳ đã duyệt, trả ngân hàng | 3 | 3 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/RECUR_BANK/tables.json) / [Kết quả](RECUR_BANK/predictions.json) |
| `RECUR_CASH` | Định kỳ | Định kỳ đã duyệt vẫn cần đối chiếu thanh toán | 3 | 3 × Đối chiếu · 8 điểm | [Nguồn](../../data/p2_controls_20261018_v2/RECUR_CASH/tables.json) / [Kết quả](RECUR_CASH/predictions.json) |
| `RECUR_GAP` | Định kỳ | Hợp đồng định kỳ không thay thế hóa đơn còn thiếu | 3 | 3 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/RECUR_GAP/tables.json) / [Kết quả](RECUR_GAP/predictions.json) |
| `RECUR_A5` | Định kỳ | Định kỳ có bằng chứng được loại khỏi tín hiệu A5 | 23 | 23 × Không P2 | [Nguồn](../../data/p2_controls_20261018_v2/RECUR_A5/tables.json) / [Kết quả](RECUR_A5/predictions.json) |
| `LIMIT_VERIFIED` | Hạn mức nội bộ | Hạn mức đã xác minh, hóa đơn vẫn thiếu | 1 | 1 × Hạn mức · 14 điểm | [Nguồn](../../data/p2_controls_20261018_v2/LIMIT_VERIFIED/tables.json) / [Kết quả](LIMIT_VERIFIED/predictions.json) |
| `LIMIT_UNVERIFIED` | Hạn mức nội bộ | Hạn mức chỉ có con số, chưa có xác minh | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/LIMIT_UNVERIFIED/tables.json) / [Kết quả](LIMIT_UNVERIFIED/predictions.json) |
| `LIMIT_FUTURE` | Hạn mức nội bộ | Xác minh hạn mức chỉ có sau thời điểm chi | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/LIMIT_FUTURE/tables.json) / [Kết quả](LIMIT_FUTURE/predictions.json) |
| `LIMIT_EXPIRED` | Hạn mức nội bộ | Hạn mức đã hết hiệu lực lúc chi | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/LIMIT_EXPIRED/tables.json) / [Kết quả](LIMIT_EXPIRED/predictions.json) |
| `LIMIT_FOREIGN` | Hạn mức nội bộ | Ngoại tệ chưa xác minh số tiền VND | 1 | 1 × Bổ sung · 0 điểm | [Nguồn](../../data/p2_controls_20261018_v2/LIMIT_FOREIGN/tables.json) / [Kết quả](LIMIT_FOREIGN/predictions.json) |
