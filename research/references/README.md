# Tài liệu và mã tham khảo

| Thư mục | Mục đích |
|---|---|
| `bibliography/` | Danh mục đọc có chú giải và BibTeX để trích dẫn |
| `data-checks/` | Bằng chứng kiểm tra dữ liệu, chia theo phạm vi task; không phải input huấn luyện |
| `papers/` | Bản PDF nguyên gốc và manifest tải paper |
| `code/` | Mã tham khảo bên ngoài, tách khỏi script vận hành của repo |

Giữ các file có vai trò trích dẫn, đối chiếu kết quả hoặc truy nguyên nguồn. Kết quả mẫu, audit toàn bộ và nhật ký toàn vẹn có phạm vi khác nhau; không coi chúng là các bản sao thay thế cho nhau.

## Bằng chứng kiểm tra dữ liệu

Nội dung nguồn, đường dẫn local và mục đích sử dụng được duy trì tại [data/T1 README](../../data/T1/README.md). Cách tạo lại kết quả nằm trong [hướng dẫn audit](../../docs/how-to/audit-t1-data.md).

| Bằng chứng | Phạm vi |
|---|---|
| [Kiểm tra khả năng truy cập T1–T8](data-checks/t1-t8/data_sources_t1_t8_access_checks.json) | Tình trạng nguồn khi rà soát |
| [Kiểm tra sâu dataset T1](data-checks/t1/t1_dataset_deep_checks.json) | URL, field và nhật ký kiểm tra nguồn |
| [Profile mẫu](data-checks/t1/t1_dataset_sample_profiles.json) | Kết quả mẫu lịch sử, gồm mẫu Séc đã được thay bằng bản tải đầy đủ |
| [Audit toàn bộ hai nguồn Séc](data-checks/t1/czech_t1_full_audit.json) | Thống kê và gate; [diễn giải kết quả](../notes/t1_czech_full_dataset_audit.md) |
| [Kiểm chứng tải và sắp xếp](data-checks/t1/czech_t1_full_verification.json) | Bản ghi kiểm tra lịch sử cho snapshot 2026-10-18; không phải kết quả chạy lại của checkout hiện tại |
| [Nhật ký tổ chức dữ liệu](data-checks/t1/t1_data_organization.json) | Lưu hash các file giữ lại và dấu vết hợp nhất metadata/chuyển dữ liệu ngày 19/10/2026 |

Script audit chỉ ghi lại JSON audit/profile tương ứng trong `data-checks/t1/`; các file kiểm tra truy cập và nhật ký lịch sử còn lại được giữ để đối chiếu, không tự tái tạo bằng hai script audit. Khi chuyển các file bằng chứng, giữ nguyên nội dung JSON để bảo toàn provenance.

## Paper và mã tham khảo

Xem thêm [danh mục 8 paper cho T0](bibliography/t0_reading_list.md): kiến trúc dữ liệu, temporal history, chất lượng dữ liệu và đối soát. Có bản PDF trong `papers/t0/`, [manifest nguồn tải](papers/t0/manifest.json) và [BibTeX](bibliography/t0_references.bib).

Các PDF và mã R dưới đây là tài liệu bên ngoài được lưu trong dự án. Tên file được đặt lại theo tiêu đề/chủ đề đọc từ tài liệu; nội dung file được giữ nguyên.

| Tài liệu | Liên quan |
|---|---|
| [Regression Quantiles](papers/regression_quantiles.pdf) | Nền tảng hồi quy phân vị |
| [LightGBM: A Highly Efficient Gradient Boosting Decision Tree](papers/lightgbm_efficient_gradient_boosting.pdf) | Thuật toán boosting dùng cho dự báo phân vị |
| [Conformalized Quantile Regression](papers/conformalized_quantile_regression.pdf) | Hiệu chỉnh khoảng dự báo |
| [Invoice level forecasting with discrete survival methods for effective forecasting of account receivables in supply chain](papers/invoice_forecasting_discrete_survival.pdf) | Dự báo thời điểm trả bằng survival; [mã R đi kèm](code/invoice_forecasting_discrete_survival.R) |
| [A framework for modelling customer invoice payment predictions](papers/customer_invoice_payment_prediction_framework.pdf) | Khung dự báo thanh toán, survival và Survival-Boost |
| [Predicting late payment of sales invoices with statistical learning methods](papers/predicting_late_payment_sales_invoices.pdf) | Luận văn về dự báo trả chậm và đối chứng theo lịch sử khách |
| [Selective review of offline change point detection methods](papers/offline_change_point_detection_review.pdf) | Phát hiện điểm gãy và công cụ `ruptures` |

Mã R là mã tham khảo của bài báo, không phải một bước trong pipeline notebook Python. Khi chạy riêng, cần chuẩn bị dữ liệu, gói R và đường dẫn theo yêu cầu của script gốc.
