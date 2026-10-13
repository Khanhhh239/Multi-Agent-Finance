# Dataset card — plan00-v1

> Cập nhật scope: PLAN_00 DONE cho `technical-functional-v1` theo [decision record](technical_scope_decision.md). Chỉ fixture project là đầu vào bắt buộc của gate kỹ thuật; real-data acceptance và independent review chuyển PLAN_05–06. Không đổi dataset version/labels/hashes hoặc accuracy eligibility.

Ngày: 11/10/2026. Purpose: contracts, PDF routing, evidence geometry, partial-field semantics và chức năng review của capture MVP. Chưa có bộ đủ điều kiện chứng minh accuracy hóa đơn thuế Việt Nam thực tế.

**Bổ sung FATURA:** [dataset riêng fatura-mapped-v1](fatura_preparation_report.md) có 10.000 logical instances/20.000 variants, annotations chuẩn v1 và split 30/10/10 templates; pilot 50 dev-only đã AI-review. Catalog trỏ cả bộ bên dưới và FATURA riêng, không ghi đè manifests cũ. Terms/human review chưa hoàn tất, accuracy eligibility vẫn false. Các số lượng trong phần dưới mô tả bộ PLAN_00 ban đầu; FATURA là phần bổ sung riêng.

## Thành phần

| Thành phần | Số lượng | Annotation | Được dùng cho |
|---|---:|---|---|
| Fixture tổng hợp text PDF | 10 | Generator ground truth, text/bbox checked | Chức năng native text/geometry |
| Fixture tổng hợp scan PDF | 10 | Cùng nguồn rendering và ground truth | Chức năng OCR routing/geometry |
| Fixture tổng hợp PNG | 10 | Cùng nguồn rendering và ground truth | Chức năng image routing/candidates |
| Known duplicate variants | 2, ngoài 30 chính | Resize và rotate fixture có lineage | Kiểm duplicate detector, không tăng số document logic |
| Negative contract cases | 6, không phải file ảnh riêng | JSON expectations | Field statuses, absence, VAT, missing page và page grouping |
| Receipt MC-OCR local | 1.153 trong existing manifests | 4 field label types, chưa review lại | Inventory/hash/coverage, QUARANTINE cho bộ mới |
| Hóa đơn thuế Việt Nam thực tế | 0 | Chưa có | Không được claim accuracy |

30 file tổng hợp biểu diễn **10 chứng từ logic**, không phải 30 hóa đơn thực độc lập. Layout variants chỉ dịch vị trí có kiểm soát; không đại diện 10 template nhà cung cấp thực tế. Một nhóm có 2 trang PDF; PNG của nhóm đó chỉ trang đầu, totals nằm trang 2 phải NOT_ANNOTATED và không được coi discovery complete. Fixture KCT/KKKNT/0% chỉ kiểm semantics, không là ví dụ xác nhận áp dụng luật.

## Splits và duplicate policy

Fixture nhóm 00–05 thuộc dev (18 file), 06–07 calibration (6), 08–09 test (6). Cả 3 format của cùng chứng từ ở cùng split. “Calibration/test” ở đây là phân nhóm chuẩn bị chức năng, **không đủ kích thước/tính độc lập để hiệu chỉnh confidence hoặc công bố model accuracy**. Các offset templates được gán group cho kiểm chống leakage, không claim generalization ngoài template.

Real source giữ `legacy_split` làm provenance; split mới là QUARANTINE vì chưa có bằng chứng quyền/nhóm template. Không random resplit receipt để giả một test sạch, không dùng crops/rotations cùng tài liệu ở split khác. Existing smoke đã dùng một phần legacy test. Test accuracy mới chỉ được freeze khi có dataset/importer/labels phù hợp.

Duplicate exact dùng SHA-256; gần trùng dùng dHash 9×8, ngưỡng khoảng cách ≤4 và xét 4 góc xoay. Đây là candidate detector, có false positive/negative; nhóm template khác chưa chắc là duplicate và dHash khác chưa chứng minh độc lập. Manual audit là bước bắt buộc để mở scope real evaluation.

## Nguồn, quyền và riêng tư

Fixture sinh tại project, dữ liệu tên/MST cố ý giả và có dòng cảnh báo. MST demo không được dùng cho checksum/existence acceptance. Ground truth là ý đồ render được đối chiếu text/PDF bounds, chưa human review độc lập.

MC-OCR đã có trong workspace; [nguồn chính thức](https://www.rivf2021-mc-ocr.vietnlp.com/dataset) nêu research-only + registration agreement. Không thấy hồ sơ đăng ký ở lần kiểm kê này, vì vậy chưa mở cho pipeline mới. Raw vẫn ở chỗ cũ, không sửa/xóa hoặc tái phân phối. Manifest/duplicate IDs thật ở `data invoice/plan00_local/` ignored; public reports chỉ counts/hashes. `.gitignore` không là encryption/access control; dữ liệu thật cần storage permissions phù hợp khi vận hành.

## Label coverage và đánh giá

Annotation statuses: OBSERVED/ABSENT_CONFIRMED/UNREADABLE/NOT_ANNOTATED. Không dùng runtime MISSING thay cho nhãn chưa gán. Xem [hướng dẫn nhãn](annotation_guideline.md) và [metrics](acceptance_matrix.csv).

Field accuracy chỉ trên labels OBSERVED có semantic mapping đã xác minh; all-required accuracy chỉ trên documents đầy đủ required labels của family. Báo riêng số samples bị loại và coverage. Real invoice thresholds chưa có baseline: TBD; không bật auto acceptance. Geometry IoU 0.5 là diagnostic matching threshold, không là target accuracy 50%.

## Tái hiện và phiên bản

Generator/config/font/runtime versions, manifest và split SHA-256 nằm ở [build_summary.json](build_summary.json). Lệnh và policies trong [README](README.md). Build không chạy OCR/inference. Hash phụ thuộc runtime/font, không hứa cùng binary PDF trên runtime khác. Khi đổi runtime/render/config phải version và kiểm lại geometry; khi đã khóa release dataset không build ghi đè version đó.

## Hạn chế và bước gỡ

1. Chưa có invoice thật hoặc independent reviewer: dùng [nguồn tải](data_sources_and_downloads.md), import riêng rồi gán/đối chiếu nhãn đúng scope.
2. Không đủ dữ liệu calibration: PLAN_05 giữ UNAVAILABLE/manual review.
3. Chưa có mixed PDF và multi-document functional binary: bổ sung fixtures trong PLAN_02/04; không claim coverage từ text/scan riêng lẻ.
4. Negative cases hiện là contract expectations, chưa là test chạy trên pipeline production chưa tồn tại. PLAN_01–06 hiện thực assertions theo stage.
5. REAL manifest chưa template-disjoint, duplicate candidates chưa phân xử: không tuyên bố gate split real đã đạt.
