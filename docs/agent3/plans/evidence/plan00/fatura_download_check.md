# Kiểm tra FATURA2 tải về — 11/10/2026

**Kết luận: download và giải nén PASS.** Dữ liệu đã có tại `data invoice/plan00_incoming/`; chưa import vào CFR/manifest đánh giá chính và chưa chạy OCR/train.

Đây là snapshot kiểm download. **Bước sau đã mapping vào dataset cục bộ, chia template và rà pilot:** xem [preparation report](fatura_preparation_report.md); chưa nối CFR runtime hoặc chạy OCR/train.

## 1. Toàn vẹn file

| Kiểm tra | Kết quả |
|---|---|
| Archive | `FATURA2.zip`, 690.717.658 bytes |
| MD5 thực tế | `4c9404462f22c5241eb1a290a02eb2a2` |
| Đối chiếu MD5 | Khớp [record v2 chính thức](https://zenodo.org/records/10371464) |
| SHA-256 | `984e3812b8b7c632e668a2dd92afab5ae44631face24efe53e543910e5fca474` |
| ZIP CRC | PASS toàn archive |
| File giải nén | 50.004 file; mỗi file khớp size và CRC của archive; 0 file thiếu/sai/thừa |
| Ảnh | 20.000 JPG: 10.000 nền trắng + 10.000 nền màu; header mở được |
| Nhãn | 30.000 JSON parse được: 10.000 mỗi format Original/COCO/LayoutLM HF |
| ID ảnh–nhãn | Khớp cả hai biến thể ảnh và ba format nhãn |
| Split metadata | 3 CSV và `Strat2_Split.txt` |

Kiểm tra ảnh là header/dimensions và visual smoke một mẫu, không full pixel decoding/OCR tất cả 20.000 ảnh. Hash/CRC PASS xác nhận tải và giải nén đúng archive, không chứng minh nội dung annotation chính xác.

## 2. Cách hiểu bộ dữ liệu

Có **10.000 invoice instances, 50 templates × 200 instances**, mỗi instance có hai nền. Không tính chúng thành 20.000 hóa đơn độc lập. Đây là hóa đơn quốc tế tổng hợp, không là hóa đơn thuế Việt Nam thực tế. Không có PDF trong archive.

Visual smoke `images/Template1_Instance0.jpg`: ảnh đọc được, có buyer/date/table/totals và GSTIN. GSTIN không được map thẳng thành MST Việt Nam; ngày/totals phải coi là nội dung nguồn, không mặc định đúng nghiệp vụ/pháp lý.

## 3. Nhãn có gì và chưa có gì

| Original field có text | Instances |
|---|---:|
| DATE | 9.800 |
| NUMBER | 8.800 |
| BUYER | 6.200 |
| SELLER_NAME | 6.800 |
| TOTAL | 8.000 |
| SUB_TOTAL | 6.797 |
| TAX | 3.800 |
| GSTIN_SELLER | 1.000 |
| GSTIN_BUYER | 600 |

Đây là coverage theo key có text, không phải số field đã adjudicate/normalize hoặc đầy đủ toàn document. BUYER có thể là block nhiều thông tin, TAX có cả label/rate/amount. Không phải mọi ảnh có mọi field; thiếu annotation không được tự xem là extraction failure hay vi phạm.

LayoutLM HF dùng `path`, `words`, `ner_tags`, `bboxes`, không phải tên key CFR. COCO-like dùng `image_id`, `class_labels`, `boxes`, `orig_size`; không giả mọi JSON mang chữ COCO đều giống chuẩn COCO đầy đủ. Original dùng nhiều cấu trúc dict/list, TABLE cần parser riêng; chưa xác nhận có đủ cell/row semantics để đo line-item accuracy.

Audit phát hiện 10.000 occurrence bbox top-level có corner order đảo theo giả định `[min,min]→[max,max]`. Trên mẫu Template1_Instance0, field LOGO là `[[0,841],[90,751]]`; TABLE lồng trong list cũng có chiều y đảo. Đây là **cảnh báo quy ước tọa độ**, không tự kết luận annotation bị hỏng hoặc 10.000 document không dùng được. Diagnostic tự động trên Original chỉ kiểm dict bbox top-level, chưa duyệt mọi bbox lồng nhau. Original/native coordinate frame phải được đối chiếu ảnh với HF/COCO trước canonicalization; không sửa nguồn bằng thao tác đổi góc hàng loạt chưa kiểm chứng. Xem counts trong JSON và ví dụ cục bộ ở `data invoice/plan00_local/fatura_annotation_issue_examples.json`.

## 4. Split đi kèm chưa đáp ứng holdout theo template của project

- Strategy 1: train 7.500 / dev 1.250 / test 1.250; không trùng instance IDs, nhưng **cả ba tập đều có đủ 50 templates**. Dùng được cho phép đo seen-layout nếu công bố đúng; không được gọi unseen-template evaluation.
- Strategy 2: 40 train templates, 10 dev templates; `test_inds = dev_inds`, nên dev/test trùng cả 10 nhóm template. Chưa dùng trực tiếp cho calibration/test độc lập của project.
- White/colored cùng instance luôn chung document/duplicate family và split. Ba annotation formats cũng không được tính là ba samples độc lập.

Trước nhập bộ đánh giá mới cần chọn và lưu template-disjoint dev/calibration/test của project, giữ original split làm provenance. Chưa tạo hoặc thay source split trong lần kiểm tra download này.

## 5. Trạng thái PLAN_00 sau tải

Đã gỡ việc **chưa có archive invoice-layout để khảo sát**. Chưa gỡ các việc sau:

1. Mapping annotation/coordinate conventions sang schema v1 và kiểm cell/row coverage.
2. Nhãn độc lập/critical-field review, target accuracy và bộ chia template sạch.
3. Native/scan PDF và hóa đơn thuế Việt Nam thực tế vẫn chưa có.
4. Archive không có README/LICENSE; trang record render phần License không hiển thị điều khoản cụ thể, API/export không đọc được qua công cụ trong phiên. **Chưa xác nhận điều kiện dữ liệu**, không tự suy từ quyền tải hoặc license mirror. Ghi thiếu provenance quyền để hoàn thiện trước dùng cho training/evaluation phát hành.

Giữ PLAN_00 BLOCKED một phần; không gọi cả gate PASS chỉ vì checksum PASS. Có thể tiếp tục kiểm kỹ thuật/mapping trên bản đã tải trong phạm vi local, không train hay publish dataset ở bước này.

## 6. Tái hiện

Từ workspace root:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\check_fatura_download.py
```

Script chỉ đọc archive và extracted files, ghi [JSON report](fatura_download_check.json) cùng metadata diagnostics riêng. Không di chuyển/sửa dữ liệu gốc, không cài dependency, không gọi model/API. Báo cáo không chứa toàn văn nhãn hóa đơn.
