# Runbook OCR/extraction V2 — vẫn thuộc PLAN_06

Ngày: 14/10/2026. Trạng thái: IN_PROGRESS_TECHNICAL_SELF_CHECK. [Kết quả máy đọc được](validation.json) · [Quyết định nhánh](decision_record.md) · [Dữ liệu và người thực hiện](data_workplan.md).

Cập nhật vòng 2: đã sửa nhãn dịch dính chữ, binding tên bên bán khi MST đọc lỗi và ngày có dấu đóng ngoặc dư. OCR default tăng 21→23/31 field đúng; OCR split tăng 23→26/31, còn 3 thiếu/2 điền sai. [Báo cáo và giới hạn vòng 2](missing_fields_round_02.md). Các số trong phần dưới là snapshot vòng đầu, không sửa đè. Theo yêu cầu người dùng, sau mỗi đợt sửa code và kiểm thử hoàn chỉnh sẽ commit/push GitHub một lần.

## Đã thực hiện

- Chạy baseline OCR thật, đóng băng cấu hình/runtime/source/input/label hash; xuất normalized blocks, candidates/issues, ảnh overlay và crop về thư mục local bị Git ignore.
- Đánh giá 9 case native (8 public pilot + 1 tài liệu đào tạo báo riêng), 3 scan và 3 hybrid. Ba scan là raster của PDF đã có; nhãn chọn lọc được tự đối chiếu, không phải nhãn độc lập.
- Thử 3 giới hạn width trên cùng crop tên VNPT, sau đó thử tách theo khoảng trắng. Width lớn hơn tệ hơn; split giảm 15 xuống 1 ký tự sai trên crop, nhưng chưa đúng hoàn toàn (còn chữ hoa/thường).
- Thêm helper crop/rectification và profile `ppocrv6_vietocr_v2_split` dùng cùng weights VietOCR, chỉ bật tách dòng dài. Rectification chưa bật trong profile, chưa có kết quả ablation để promote.
- Chạy worker thật cho profile split trên cùng 3 trang. Giữ nguồn native và OCR riêng, không bỏ xung đột hoặc đổi nhãn để tăng điểm.
- Kiểm tra dictionary + decoder thực tế của PP-OCRv6 recognizer local: thiếu **88 ký tự trong tập kiểm tra**, phần thiếu là dấu tiếng Việt. Candidate này không đạt preflight; giữ PP-OCRv6 detector + VietOCR. Không sửa dictionary/weights tại chỗ.
- Sửa binding tổng tiền bị lệch baseline, giữ đúng block/evidence; kiểm tra không lấy số từ hàng xa và giữ AMBIGUOUS nếu có hai ứng viên. Sửa này đã ở extractor đang dùng.
- Tải được một PDF hồ sơ public mới làm holdout candidate chưa mở. Hai URL Bkav chưa tải được; chưa có 2–3 họ template mới được xác nhận.

## Kết quả trên nhãn pilot đã dùng phát triển

| So sánh | Trước | Sau | Phạm vi |
|---|---|---|---|
| Sửa binding, cùng normalized input | 79 đúng, 1 thiếu | 80 đúng | 80 field chọn lọc, 8 native public; không gồm địa chỉ/toàn bộ ô bảng |
| OCR split, giữ extractor trước sửa binding | 21 đúng, 6 thiếu, 4 điền sai | 23 đúng, 6 thiếu, 2 điền sai | 31 field chọn lọc, 3 trang scan raster |
| Hybrid split | 27 đúng, 4 ambiguous | 29 đúng, 2 ambiguous | Cùng 31 field/3 chứng từ |
| Nguồn đào tạo native | 10 đúng | 10 đúng | Báo riêng, chưa xác minh giao dịch thực |

Sửa binding chỉ làm thay đổi một field từ MISSING sang CORRECT khi replay cùng frozen inputs. Scan split tăng 2 field đúng, **vẫn còn 2 WRONG_PRESENT và 6 MISSING**. Không đạt điều kiện chất lượng cuối và chưa bật split mặc định. Không cộng các mode thành hóa đơn độc lập hoặc coi 80/80 pilot là accuracy thực tế 100%.

Timing fresh worker theo thứ tự VNPT/Cyber/FAST: V1 **168,57 / 118,58 / 161,08 giây**; split **115,10 / 109,87 / 180,36 giây**. Mỗi page là một process mới; đây là 3 điểm quan sát mỗi cấu hình, không đủ để công bố cải thiện p95. FAST chậm hơn sau split. Model load khoảng 14–20 giây, RAM đỉnh khoảng 1,4 GiB. Warm/batch latency và fallback/retry theo workload đại diện còn phải đo; không lấy thời gian từ cache làm end-to-end mới.

## Tái hiện

Cwd `D:\financial`. Mỗi lần phải dùng run-id mới; script từ chối ghi đè thư mục đã có. Các lệnh OCR thật mất vài phút trên CPU, giữ giới hạn timeout/RAM hiện tại.

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/diagnose_ocr_v2.py --run-id my_v2_baseline --fresh-ocr
agent3_tax_compliance/.venv/Scripts/python.exe scripts/diagnose_ocr_v2.py --run-id my_v2_split --fresh-ocr --model-id ppocrv6_vietocr_v2_split
& 'data invoice/ocr_e2e_workflow/envs/ppocrv6_vietocr/Scripts/python.exe' scripts/audit_vietnamese_charset_v2.py --run-id my_charset_check
agent3_tax_compliance/.venv/Scripts/python.exe scripts/collect_v2_holdout.py --run-id my_holdout_collection
```

Raw artifacts: `data invoice/ocr_extraction_v2/plan06_v20_frozen_01`, `plan06_v21_split_full_01`, `plan06_v23_binding_replay_01`. Cache audit có timing_source riêng, không phải fresh baseline. `charset_preflight_01` là lần kiểm dictionary đơn thuần (space chưa tính decoder); `charset_preflight_decoder_02` lỗi gọi constructor; kết luận dùng **charset_preflight_decoder_03** đã kiểm decoder thực và loại sai lệch về space. Các lần này được giữ nguyên, không sửa bằng chứng thất bại thành pass.

`scripts/report_ocr_v2.py` tạo replay cùng baseline input và tổng hợp báo cáo, không chạy OCR. Script này đóng băng tên replay của đợt đầu; muốn chạy đợt khác phải tạo phiên bản/run path mới, không ghi đè đợt cũ. Metadata mapping segment được bổ sung sau phép đo split; số đo trong validation vẫn gắn hash bản adapter đã chạy, không giả vờ đã chạy lại OCR bản metadata mới.

UI vẫn mở bằng `OPEN_AGENT3.cmd`. Sửa extractor chỉ tác động lượt capture mới; artifact/job đã hoàn thành được giữ nguyên, upload trùng có thể trả job cũ. Muốn tự kiểm tra lại cùng PDF mà giữ dữ liệu cũ, dùng database demo riêng:

```powershell
cd agent3_tax_compliance
./.venv/Scripts/python.exe -m src.local_web --database data/local_web/v2_selfcheck.sqlite3
```

Launcher mở port còn trống và trình duyệt, chép mã truy cập vào clipboard. Cấu hình OCR mặc định vẫn V1; profile split hiện chỉ dùng qua benchmark, chưa đưa vào UI mặc định. Người code/user tự xem nguồn và đối chiếu trường đúng/sai; không ghi tự test thành independent adjudication.

## Việc còn lại trong PLAN_06

V2-0 đã có baseline/inventory/decision record và một read oracle cắt tay; **chưa hoàn tất đầy đủ** bộ oracle 10–20 lỗi, oracle layout, warm/batch latency và holdout có nhãn. Số `FIELD_UNBOUND` từ script chỉ là giả thuyết substring, phải xem thêm chữ thừa/parser để kết luận. Normalizer probes canonical label là sanity check, không thay oracle raw value.

Ưu tiên tiếp: mở rộng crop oracle cho 2 tên còn sai, MST có chữ thừa và ngày; đo khoảng trắng/crop ở scan; xử lý binding khi đã có text; làm nhãn/test theo scope tự đối chiếu đã được user chấp nhận. V2-4 recovery/VLM và V2-5 calibration/shadow/UI acceptance chưa triển khai đầy đủ. Chưa chuyển PLAN_07, chưa có tax verdict hoặc auto-accept.
