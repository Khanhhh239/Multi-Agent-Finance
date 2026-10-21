# Tổng quan dự án

Cập nhật: 2026-10-21. Đây là nơi ghi phạm vi và trạng thái hiện tại của checkout; kết quả thí nghiệm có bằng chứng riêng trong báo cáo.

## Bài toán và phạm vi

Đích sản phẩm là giúp SME Việt Nam bán chịu B2B dự báo dòng tiền 13 tuần, phát hiện nguy cơ thiếu tiền và ưu tiên thu nợ. [Bản đồ nhiệm vụ T0–T13](explanation/user-needs-and-tasks.md) mô tả phạm vi thiết kế đầy đủ.

Bộ notebook thử nghiệm trước đây về **thời điểm trả và cash-in từ hóa đơn phải thu đang mở** được giữ tại `reference_notebooks/`, chỉ để tham khảo phương pháp, code và kết quả lịch sử. Bộ này có baseline, LightGBM phân vị, conformal calibration, Monte Carlo, survival và các thử nghiệm ưu tiên thu nợ, stress, dashboard. Code T1 mới sẽ được xây riêng; hiện chưa có trong checkout. Có notebook hoặc thiết kế chưa đồng nghĩa chức năng đã được kiểm định trong doanh nghiệp.

## Thành phần hiện có

| Thành phần | Trạng thái và nguồn chi tiết |
|---|---|
| T0 offline v0.4 | Có N:M giới hạn qua nhiều ngày trong snapshot, FX có quote quan sát, refund–bank và version invoice/payment; giữ typed AP/AR, FinRCA, ledger/Gold, statement và gate riêng. [Dữ liệu và lệnh chạy](../data/T0/README.md), [hợp đồng T0](reference/t0-data-contracts.md#phần-mở-rộng-v04--khác-ngày-fx-phiên-bản-và-journal). **Chưa có invoice–bank SME có nhãn độc lập**; chưa kết nối ERP/ngân hàng. |
| Nguồn mở rộng T0 | FinRCA quality vẫn `null`; RecBench giữ endpoint thiếu unknown. Journal có engine nhiều dòng theo policy/facts tường minh, trial balance và kiểm dependency; baseline text FinBalance mở thêm supplier/utilities/loan/payroll, detector thêm running balance/loan/payroll. Chưa kiểm định broad accounting; FISCUS có bốn ca bank workflow. [Phạm vi và bằng chứng](reports/t0-method-review.md). |
| Mã tham khảo | Notebook 01–12 và helper Python tại `reference_notebooks/`; [mục lục](../reference_notebooks/README.md) xác định thứ tự cũ và nguồn `.py` của 11/12. Output lưu sẵn là kết quả lịch sử. |
| Code T1 mới | Chưa triển khai; sẽ xây riêng, không mặc định kế thừa pipeline notebook tham khảo. |
| Nguồn T1 | Đã tải và audit hai nguồn hóa đơn Séc; giữ thêm mẫu BPI/DC. [Hướng dẫn dữ liệu T1](../data/T1/README.md) giải thích nội dung, mục đích và giới hạn. |
| Đầu vào huấn luyện | `data/dataset.csv`, các bảng `data/processed/` và model mà notebook lịch sử yêu cầu chưa có. Chưa có adapter đưa dữ liệu Séc vào pipeline này. |
| Kiến trúc mở rộng | T0–T13 và hệ thống bốn agent nằm trong [tài liệu thiết kế](README.md); không mặc định đã có code triển khai ở checkout. |
| Kiểm tra repository | Có checker tài liệu, Python/JSON/JSONL trong CI và test hồi quy; [Contributing](CONTRIBUTING.md) hướng dẫn chạy và phạm vi bỏ qua. Đây không phải kiểm thử chất lượng mô hình. |

```mermaid
flowchart LR
    S[Nguồn hóa đơn Séc] --> R[Raw + manifest]
    R --> A[Audit và bảng interim]
    A -. Chưa triển khai .-> T[Code T1 mới]
    H[Đầu vào lịch sử chưa có] -.-> N[reference_notebooks: chỉ tham khảo]
    N --> O[Output thí nghiệm lịch sử]
```

## Giới hạn cần giữ khi phát triển

- Dữ liệu Séc là hóa đơn nhà cung cấp được tổ chức công thanh toán; cần kiểm định chuyển miền sang SME B2B Việt Nam. Không có bộ dữ liệu đầy đủ cho mọi task T2–T8.
- Thiếu ngày trả không tự chứng minh hóa đơn chưa trả; ngày ghi thanh toán không tự chứng minh ngày tiền khả dụng tại ngân hàng. Phải xác định nhãn và phạm vi quan sát trước khi train.
- Feature phải là thông tin biết được tại cutoff. Dữ liệu công bố sau thanh toán không mặc định dùng được để dự báo từ API công khai trước thanh toán. Quy ước cụ thể cho T1 nằm tại [hợp đồng dữ liệu T1](reference/t1-data-contracts.md); trang đó không định nghĩa hợp đồng cho toàn bộ T0–T13.
- Chưa có môi trường dependency được khóa phiên bản hoặc kết quả chạy lại toàn pipeline trên nguồn Séc. Chưa đủ bằng chứng để kết luận triển khai production hoặc đạt SOTA.

Khi phạm vi, khả năng chạy hoặc trạng thái tích hợp thay đổi, sửa trang này; hướng dẫn chi tiết và số liệu vẫn nằm ở tài liệu chuyên trách.

Hướng T0 được duy trì trong [kế hoạch thực hiện hợp nhất](../research/notes/t0_data_foundation_reconciliation.md#kế-hoạch-tiếp-tục-t0) và mục tiến độ 21/10: M0–M3 có triển khai offline trong phạm vi khai báo; M4 chỉ payout–bank, M5 chỉ một số chính sách journal. Tìm pilot SME diễn ra song song.

Ledger local lưu quyết định bền vững, tách approval/commit/unknown/verify/reversal; credit note không tạo cash và phí tách gross/net. V0.4 có FX/refund–bank tường minh và sửa giá trị invoice/payment giữ history/cutoff, chưa có sửa scope/ngày nghiệp vụ hoặc toàn bộ loại chứng từ. Gold có dư nợ, bank movement và đối chiếu opening/closing từ statement khai báo; chưa xác minh tính đầy đủ từ ngân hàng hoặc tạo dữ liệu train T1. Chargeback, ERP API, chính sách journal rộng và lịch sử SME vẫn thiếu; gate quality/evidence chưa hoàn tất, chưa có bằng chứng cải thiện dự báo T1 hoặc đủ điều kiện production.
