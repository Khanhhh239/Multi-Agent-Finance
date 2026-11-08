# Nguồn dữ liệu và hướng dẫn tải — kiểm tra ngày 11/10/2026

Người dùng xác nhận hiện chưa có bộ hóa đơn thuế thực tế/người đối chiếu và yêu cầu tìm link để tự tải. Không tải archive lớn hay đăng ký tài khoản thay người dùng trong phiên này.

**Cập nhật:** người dùng đã tải FATURA2.zip và giải nén vào incoming. [Đã kiểm toàn vẹn thành công](fatura_download_check.md); hướng dẫn dưới đây giữ làm provenance, không cần tải lại FATURA. Import/mapping chưa thực hiện.

**Tiến độ mới nhất:** [mapping/split/pilot FATURA đã thực hiện](fatura_preparation_report.md) ở dataset cục bộ riêng. Các hướng dẫn importer “chưa viết” bên dưới là trạng thái trước bước này; hiện có `scripts/prepare_fatura_dataset.py` cho FATURA, DocILE/CORD vẫn chưa có importer.

## 1. Lựa chọn đề nghị

| Ưu tiên | Nguồn chính thức | Có gì | Phù hợp / giới hạn | Điều kiện truy cập |
|---|---|---|---|---|
| 1, invoice/PDF/items | [DocILE](https://docile.rossum.ai/), [repository](https://github.com/rossumai/docile) | Business documents, PDF/OCR, KILE và line-item labels | Tốt để thử invoice layout/items; không xác nhận luật/VAT/MST Việt Nam | Form research access; nhận token rồi tải annotated-trainval theo hướng dẫn |
| 2, invoice layout tải trực tiếp | [FATURA v2 trên Zenodo](https://zenodo.org/records/10371464) | Invoice images sinh từ 50 templates, bbox/text/classes, backgrounds trắng/màu | Có annotation, tách template được; đây là generated images và không có native PDF | Record public; license cụ thể chưa đọc được qua trang trích xuất, cần kiểm license/README trước dùng |
| 3, receipt/menu | [CORD v2 của NAVER CLOVA](https://huggingface.co/datasets/naver-clova-ix/cord-v2), [repo tác giả](https://github.com/clovaai/cord) | Receipt Indonesia, ảnh và nhãn semantic/menu; 800 train/100 dev/100 test | Tốt cho line grouping receipt; không thay hóa đơn thuế Việt Nam hay buyer/MST | Dataset card ghi CC BY 4.0; giữ attribution/license |
| Đã có local, tiếng Việt | [MC-OCR](https://www.rivf2021-mc-ocr.vietnlp.com/dataset) | Vietnamese receipts/text/4 field labels | Dùng baseline OCR tiếng Việt; thiếu invoice semantics | Nguồn nêu research only và cần đăng ký user agreement; kiểm bản local đã có quyền trước dùng |

Không tìm được qua lần tra cứu này một nguồn chính thức được xác minh đủ cả **hóa đơn thuế Việt Nam thực tế + native/scan PDF + nhãn seller/buyer MST/VAT/items + quyền sử dụng rõ**. Đây là giới hạn kết quả tìm kiếm, không phải khẳng định không tồn tại bộ đó.

## 2. Tải thế nào

**DocILE:** vào trang chính thức, chọn “Form to get access to the dataset”, đăng ký theo mục đích nghiên cứu. Sau khi có quyền/token, làm theo README repo; chỉ lấy `annotated-trainval` trước, chưa cần gói unlabeled/synthetic lớn. README có tùy chọn in URLs để tải bằng công cụ khác. Script `.sh` không chạy trực tiếp trong PowerShell thuần; nếu dùng script cần Git Bash/WSL theo môi trường bạn có. Token là secret, không đưa vào file kế hoạch hoặc chat/log công khai. MIT license của code không tự là license dữ liệu.

**FATURA:** mở record v2 rồi chọn `FATURA2.zip` ở Files. Trang tác giả ghi ~690,7 MB, MD5 `4c9404462f22c5241eb1a290a02eb2a2`. [Link archive từ record](https://zenodo.org/records/10371464/files/FATURA2.zip?download=1). Giữ nguyên version/source README; white/colored variants của cùng instance phải cùng duplicate family/split. Chưa xác minh license thì giữ ở incoming, không nhập bộ nghiệm thu.

**CORD:** mở tab “Files and versions” trên Hugging Face, tải các shard + README, hoặc dùng công cụ Hugging Face khi đã sẵn môi trường. Dữ liệu phát hành dạng Parquet có ảnh/ground_truth, không phải thư mục PDF/PNG sẵn dùng; sau tải cần importer riêng. Không chỉ tải README rồi coi đã có dataset.

## 3. Bỏ vào đâu

Đã chuẩn bị `data invoice/plan00_incoming/`. Đặt archive hoặc thư mục nguyên bản cùng README/LICENSE ở:

```text
data invoice/plan00_incoming/
  docile/    # annotated-trainval + terms, không lưu access token
  fatura/    # FATURA2.zip hoặc bản giải nén + README/LICENSE
  cord/      # Parquet shards + README/LICENSE
```

Không bỏ vào `tests/fixtures/ocr/`: thư mục đó chỉ cho mẫu tổng hợp CI. Không đổi dataset receipt cũ hoặc trộn các bản derivative vào split mới.

Khi đặt xong, cung cấp tên thư mục; bước kế tiếp sẽ inventory/hash, kiểm archive và quyền sử dụng, map annotation rồi cập nhật coverage/splits. Các importer DocILE/FATURA/CORD **chưa được viết**; script PLAN_00 hiện chỉ kiểm bộ local đã có và sinh fixture tổng hợp.

## 4. Phần nào vẫn cần bổ sung

DocILE/FATURA/CORD giúp kiểm pipeline và các bố cục khác; không giải quyết trực tiếp việc đo MST/VAT/buyer trên invoice Việt Nam thực tế. Muốn kết luận accuracy cho nhóm đó vẫn cần tập Việt Nam có quyền, nhãn đúng semantic và người đối chiếu độc lập. Trong thời gian chờ, fixture tiếng Việt tổng hợp dùng cho chức năng/geometry và manual review, không cho claim production accuracy.
