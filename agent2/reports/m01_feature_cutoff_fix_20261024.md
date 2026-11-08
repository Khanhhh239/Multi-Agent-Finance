# Sửa M01 — thời điểm khả dụng của feature chứng từ/hóa đơn — 24/10/2026

**Đã sửa trong mã nguồn:** giá trị chứng từ hoặc số tiền hóa đơn biết sau cutoff không còn đi vào các feature chứng từ, số tiền hóa đơn và tỷ lệ dẫn xuất của giao dịch đang chấm. Bổ sung trạng thái khả dụng, đọc phiên bản chứng từ theo thời gian và nâng feature contract để model cũ không nhận nhầm ý nghĩa đầu vào mới.

| Ca ngày chi 12/08/2025, dữ kiện chỉ biết 14/08/2025 | Trước sửa | Sau sửa |
|---|---:|---:|
| Điền thêm 2 chứng từ vào dữ liệu cuối kỳ: `support_doc_count` | 0 → 2 | **0 → 0** |
| Điền cờ giao nhận đã xác minh: `goods_receipt_verified` | 0 → 1 | **0 → 0** |
| Điền tổng hóa đơn 12 triệu phát hành sau ngày chi: `invoice_log_gross` | 0 → 16,30041729 | **0 → 0** |

Trong hai phép thử sau sửa, **toàn bộ vector feature lịch sử giữ nguyên**, không chỉ ba ô trên. Khi cùng dữ kiện thực sự đã biết tại cutoff, 2 chứng từ và cờ giao nhận vẫn được sử dụng, tổng hóa đơn 12 triệu vẫn cho `invoice_log_gross=16,30041729`. [Bằng chứng sau sửa](m01_feature_cutoff_fix_20261024/reproduction_after.json); [bằng chứng phát hiện trước sửa](deep_rules_ml_audit_20261023/edge_probes.json).

Mã [feature_evidence.py](../sme_fraud/feature_evidence.py) chọn phiên bản `transaction_documents` mới nhất có `observed_at <= posted_at` trước khi lọc trạng thái. Nguồn phải khớp công ty, NCC và giao dịch; định danh hóa đơn phải khớp. Phiên bản biết muộn không thay thế phiên bản đã biết; phiên bản thu hồi đã biết không được hồi sinh bằng cờ/tổng tiền cuối cùng trên giao dịch. Thứ tự dòng không ảnh hưởng kết quả. Các phiên bản mâu thuẫn hoặc đổi binding bị từ chối.

Nếu chưa có phiên bản chứng từ phù hợp đã biết, engine chỉ dùng scalar trên dòng giao dịch khi có thời điểm biết rõ ràng: `support_docs_observed_at` cho bộ chứng từ/cờ giao nhận, `invoice_observed_at` cho số tiền và thành phần hóa đơn. Hóa đơn phải có ngày phát hành không sau cutoff. Thiếu thời điểm biết thì các giá trị này bằng 0 **kèm cờ chưa khả dụng**, không coi số 0 đó là xác nhận không có chứng từ/hóa đơn. Không tự điền ngày biết cho nguồn cũ.

Thêm bốn feature để phân biệt dữ kiện thiếu với giá trị đã quan sát:

| Feature | Ý nghĩa của 1 |
|---|---|
| `support_docs_known` | Đã có snapshot bộ chứng từ tại cutoff; số lượng quan sát có thể bằng 0 |
| `invoice_known` | Số tiền hóa đơn có trong snapshot khả dụng, ngày phát hành không sau cutoff |
| `invoice_components_known` | Cả net và VAT thuộc cùng snapshot hóa đơn đã biết |
| `linked_input_vat_known` | VAT đầu vào liên kết có trong cùng snapshot hóa đơn đã biết |

[features.py](../sme_fraud/features.py) dùng tổng tiền đã chọn cho tỷ lệ thanh toán và tỷ lệ lũy kế; chỉ cập nhật lịch sử hóa đơn khi có định danh hóa đơn khả dụng tại thời điểm giao dịch đó. Các tỷ lệ VAT/sai lệch số học dùng cùng snapshot, không đọc net/VAT cuối kỳ. Thiếu thành phần không bị biến thành một sai lệch số học giả. Feature chứng từ xóa tạm ứng cũng dùng bằng chứng khả dụng, thay vì cờ cuối kỳ chưa có thời điểm biết. Đầu ra được sắp đúng thứ tự feature contract khi xuất CSV.

Phạm vi sửa là nhóm chứng từ/số tiền hóa đơn và các dẫn xuất nêu trên. Ngày hóa đơn trong header giao dịch legacy vẫn là tham chiếu cho tín hiệu registry theo quy ước cũ khi không có `invoice_observed_at`; ngày phát hành tương lai hoặc ngày biết hóa đơn khai báo muộn không đủ điều kiện cho tín hiệu này. Bản sửa không xác nhận mọi trường header/ledger của một nguồn chưa được nghiệm thu đều có lịch sử đầy đủ. M02/M03 và các vấn đề nguồn khác vẫn là hạng mục riêng.

**Kết quả xác minh cuối cùng: 200 kiểm thử thuộc 14 module đạt; 0 thất bại, 0 lỗi chạy, 0 bỏ qua.** Bao gồm [23 kiểm thử M01 mới](../tests/test_feature_evidence_timing.py), một kiểm thử bổ sung về thiếu thời điểm biết chứng từ xóa tạm ứng, kiểm tra tính nhân quả, nguồn/feature/model, train/calibration/evaluation, shadow, VAT, nguồn thuế và B4/B2. [Kết quả cuối cùng](m01_feature_cutoff_fix_20261024/verified_fix.json), [log cuối cùng](m01_feature_cutoff_fix_20261024/verified_fix.log). Kiểm thử kế toán cũ được bổ sung thời điểm biết trong bản sao fixture cho ca “bằng chứng hiện hành đã có”, đồng thời kiểm tra riêng trường hợp không có thời điểm biết. Không sửa fixture nguồn hoặc kết quả đã khóa.

Feature contract mới là **`causal-evidence-20261024-v2`**, tăng **190 → 194 cột**, có fingerprint bao gồm module chọn phiên bản bằng chứng mới. **Cache và hai model IF cũ 001/003 bị từ chối đúng quy tắc tương thích**; không thay nhãn phiên bản để ép model cũ chạy. Muốn dùng nguồn đang có với engine mới cần dựng cache theo contract mới và huấn luyện model mới trên train, hiệu chỉnh trên calibration, đánh giá trên evaluation. Nguồn thiếu thời điểm biết cần được bổ sung lịch sử từ hệ thống nguồn hoặc giữ trạng thái thiếu; không suy ngày biết từ ngày hóa đơn.

Đã tạo một model IF mới **chỉ để chạy thử kỹ thuật**, trong thư mục mới: 12 giao dịch train năm 2024, 6 calibration nửa đầu 2025, 6 evaluation nửa cuối 2025. Model nhận đúng 194 feature và chấm được cả 6 giao dịch evaluation; **0 dòng evaluation dùng để fit/hiệu chỉnh**. Không tạo hoặc đọc file nhãn/split/oracle cho lần chạy thử này. [Kết quả chạy thử và từ chối artifact cũ](m01_feature_cutoff_fix_20261024/model_smoke.json), [báo cáo huấn luyện](m01_feature_cutoff_fix_20261024/smoke_model/training_run.json), [kết quả shadow](m01_feature_cutoff_fix_20261024/smoke_scores/run.json). Đây không phải model thay thế hai cohort vận hành, không đo lợi ích rà hồ sơ và không phải nghiệm thu độc lập.

[Đối chiếu bảo toàn](m01_feature_cutoff_fix_20261024/verification.json): **2.303 tệp đã khóa không đổi checksum**, gồm nguồn, model và bằng chứng B4/B2 đã bàn giao. `rules.py` không thay đổi; 9 kiểm thử B4 và 12 kiểm thử B2 đều đạt. Chưa phát hành lại app, dựng lại cache/model hai cohort hoặc thay kết quả shadow/hàng đợi/phiếu rà đã chốt. [Quy ước dữ liệu đầu vào](m01_feature_cutoff_fix_20261024/source_contract.md).
