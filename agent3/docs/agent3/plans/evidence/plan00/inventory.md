# Kiểm kê tài sản — 11/10/2026

Không chạy model/inference trong PLAN_00. “Tồn tại” và “đã có báo cáo” không đồng nghĩa runtime hiện tại đã smoke lại thành công.

**Cập nhật FATURA:** download audit đã PASS, sau đó [chuẩn hóa toàn bộ và chia tập](fatura_preparation_report.md). Dataset cục bộ bổ sung 20.000 image variants/annotations; các số receipt bên dưới là inventory cũ được giữ riêng. Chưa có PDF/invoice Việt Nam thực tế hoặc training run.

## Code, runtime và dữ liệu

| Tài sản | Vị trí tương đối workspace | Kết quả kiểm tra | Cách dùng |
|---|---|---|---|
| Backend prototype | `agent3_tax_compliance/src/` | Có API/extraction/database/rules cũ; amount float/REAL và hardcoded paths | Reference, không lấy làm CFR contract mới |
| Runtime prototype | `agent3_tax_compliance/venv/` | Đã probe import metadata: Python 3.10.5; PyMuPDF 1.28.2, Pillow 12.3.0, Pydantic 2.13.4, FastAPI 0.139.2, ZEN 0.53.0 | Sinh/kiểm fixture, không nâng cấp env |
| OCR benchmark | `data invoice/ocr_e2e_workflow/` | Có source/config/reports/envs, OCRResult 1.1 | Tái dùng bằng worker bridge sau PLAN_02 |
| Existing source inventory | `.../data/manifests/source_inventory.json` | Snapshot cũ 22/09/2026, không là bằng chứng current file counts | Đối chiếu hash với kiểm kê mới |
| Full-image manifests | `.../data/manifests/full_image_dev.jsonl`, `full_image_test.jsonl` | 922 dev + 231 test = 1.153 ảnh có GT liên kết | Local inventory, QUARANTINE trong pipeline mới |
| Ground truth fields | `.../data/ground_truth/fields/all.jsonl` | 1.153 records, 4 semantic labels receipt | Không map tự động sang invoice tax roles |
| Raw full-image directory | `data invoice/train_images/train_images/` | Đếm lại 1.155 ảnh, manifest 1.153, 2 ảnh ngoài manifest, không thiếu file được tham chiếu | Không cộng crops/rotations thành tài liệu độc lập; 2 ảnh chưa import |
| Các bản crop/rotation | `data invoice/text_recognition_mcocr_data/`, `data0.7/`, `data0_or_180/`, ... | Scan cây dữ liệu có 54.402 JPG + 4 PNG; đây là số file kể cả derivatives, không số hóa đơn | Giữ nguyên, không tự chia độc lập train/test |
| PDF hóa đơn thực tế | Trong cây dữ liệu đã quét, loại env/model/tools | Không tìm thấy PDF invoice; PDF backend duy nhất được thấy là luật TNDN | Không dùng PDF luật như invoice |
| Legal references | `docs/references/legal/` | Có PDF/căn cứ từ thiết kế trước | PLAN_07, không dataset OCR invoice |
| Retrieval benchmark | `vilegalbert_test/results/retrieval_decision_report.md` | Có báo cáo trên tập nhỏ | Optional PLAN_12, chưa tác động OCR gate |

## Adapter và model

`reports/IMPLEMENTATION_STATUS.md` ghi EasyOCR, PPOCRv6 medium, PPOCRv6+VietOCR, Tesseract đã có env/smoke lịch sử; VLM còn thiếu env. Snapshot cũ ghi không phát hiện NVIDIA runtime và llama-server. Lần này không kiểm GPU inference hoặc model load. Khi PLAN_03 bắt đầu phải probe runtime/model hashes lại.

Model artifacts/envs chỉ kiểm tồn tại qua inventory; không copy, tải hoặc cài mới. Việc version một gói đã cài không chứng minh checkpoint sẵn sàng suy luận.

## Coverage ground truth đã đếm lại

| Split legacy | Documents | SELLER | ADDRESS | TIMESTAMP | TOTAL_COST | Có đủ 4 label |
|---|---:|---:|---:|---:|---:|---:|
| dev | 922 | 857 | 858 | 872 | 863 | 760 |
| test | 231 | 214 | 219 | 216 | 219 | 188 |

Các số cột label là số document có label, không đảm bảo role invoice hoặc normalized value luôn parse được. Không có ground truth buyer/MST/VAT/invoice number/item rows trong tập field này. Có file detection/transcripts riêng không tự đồng nghĩa đã có nhãn item semantics.

## Vì sao all_four_fields_accuracy = 0.0?

Đối chiếu `src/metrics/fields.py` và `runs/dev100_all_tesseract/metrics/fields.json`:

- Trong 100 mẫu, address exact = 0/91; seller exact = 8/91; date = 51/82; total = 35/88. Vì không có address exact đúng, toàn bộ 4 field đúng đồng thời chắc chắn là 0 ở run này.
- Metric hiện tính all-four trên **mọi document trong split**, kể cả khi expected một field là null; logic đó đặt field correct=false khi expected null. Vì vậy tài liệu thiếu nhãn cũng không thể đạt all-four, làm mẫu số không phù hợp cho phép đo all-required-on-completely-labeled-documents mới.
- Đây là hai vấn đề cùng tồn tại: extraction/address yếu và quy tắc mẫu số. Không sửa report/code benchmark lịch sử trong PLAN_00; dùng metric mới với đủ label cho lần đánh giá tiếp theo, báo hai chỉ số song song nếu cần so cũ.
- Legacy test đã xuất hiện trong smoke report 1–2 ảnh. Không tuyên bố toàn bộ legacy test là holdout chưa từng nhìn. Calibration chưa được tách độc lập theo template.

## Duplicate và quyền dữ liệu

Script mới hash lại 1.153 source: tất cả khớp hash cũ. Phát hiện 31 nhóm exact duplicate (33 file dư so với unique hashes), trong đó **8 nhóm xuất hiện ở cả legacy dev và test**. Có 244 cặp dHash candidate gần trùng chưa review. Hai fixture resize/rotate đã biết đều được phát hiện ở distance 0. Candidate gần trùng chỉ là ứng viên, cần người rà; không phải chứng minh template-disjoint. Chi tiết IDs ở ignored local report, số tổng ở `build_summary.json`.

Legacy dev/test không đạt yêu cầu độc lập ngay cả ở exact-file level. Không sửa manifests cũ trong PLAN_00; giữ chúng làm historical provenance và không đưa chúng vào test accuracy mới trước khi gom nhóm/chia lại từ nguồn được phép dùng. Các model đã từng đánh giá/tune trên tập cũ không được coi bộ chia lại từ cùng nguồn là holdout hoàn toàn mới.

[Trang MC-OCR chính thức](https://www.rivf2021-mc-ocr.vietnlp.com/dataset) nêu mục đích nghiên cứu và yêu cầu đăng ký thỏa thuận trước sử dụng. Lần này chưa thấy bằng chứng đăng ký của bản local, nên chỉ kiểm kê/hash và giữ QUARANTINE cho bộ mới; không tải lại hoặc đưa ảnh/nhãn thật vào CI. Không suy luận rằng người dùng vi phạm, cũng không xóa/chỉnh bộ cũ.
