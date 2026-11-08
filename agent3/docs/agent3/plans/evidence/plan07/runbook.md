# PLAN_07 — hướng dẫn chạy Rule Planning

Cập nhật 14/10/2026. Đã triển khai phần kỹ thuật của PLAN_07 theo yêu cầu tiếp tục từ PLAN_06. OCR V2 và nghiệm thu dữ liệu thực ở PLAN_05–06 vẫn còn mở. [Gate và giới hạn](../gate_07.md).

## Chức năng hiện có

Planner nhận CFR revision, quality assessment đúng hash/revision, taxpayer master và các catalog được pin phiên bản. Kết quả là `RulePlan`: rule version được chọn, đơn vị RECORD/ITEM/VAT_GROUP, applicability, capability, eligibility, lý do và việc cần làm tiếp. `engine_calls=0`: không chạy ZEN và không trả kết luận thuế.

- Thiếu/ngày không đáng tin: không dùng latest; `rule_version=null`.
- Gap/overlap lịch luật: lỗi planning; không âm thầm chọn một version.
- Direction chưa xác định: UNKNOWN; không loại rule bằng NO_MATCH giả.
- Một hóa đơn dưới ngưỡng chưa đủ để loại nghĩa vụ non-cash. Cần bằng chứng đầy đủ tổng mua cùng nhà cung cấp/cùng ngày và đúng revision hóa đơn hiện tại.
- Taxonomy độc lập với VAT rate: 8% không sinh nhóm pháp lý. Mappings thực tế hiện để trống; kết quả cần phân loại vẫn bị chặn.
- OCR không thấy một trường không phải bằng chứng trường đó không được in. Profile OCR hiện không cho phép chứng minh vắng mặt.
- Catalog pháp lý hiện DRAFT: planner có thể chọn version và giải thích blockers, nhưng không đưa rule thực tế thành ELIGIBLE chỉ vì trường đã đủ.

## Kiểm chứng tái hiện

Từ `D:\financial`, dùng venv ứng dụng đã cài:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan07.py
```

Lệnh chạy bảy suite, ghi số test thực chạy, lỗi và hash implementation vào [validation_summary.json](validation_summary.json); xuất schema tại `agent3_tax_compliance/contracts/planning-v1/`. Hai artifact công khai dùng dữ liệu tổng hợp:

- [synthetic_rule_plan.json](synthetic_rule_plan.json): rule giả đã phê duyệt riêng cho test để kiểm tra đường ELIGIBLE. Không phải rule pháp luật Việt Nam.
- [draft_catalog_plan.json](draft_catalog_plan.json): cùng dữ liệu tổng hợp, dùng catalog luật dự thảo thực tế để thể hiện blockers.

Sửa code sẽ làm implementation hash thay đổi; chạy lại script nếu cần tạo evidence cho phiên bản mới. Replay dữ liệu cũ yêu cầu code và snapshot đúng phiên bản, không lấy kết quả mới để thay lịch sử.

## Chạy với CFR đã lưu

PLAN_07 chưa thêm nút compliance trên UI và chưa tự chạy sau upload. Mở UI như trước bằng `OPEN_AGENT3.cmd`; khởi động lại launcher/server để nạp routes mới. Trước khi nâng DB đang dùng, dừng server/worker và sao lưu DB bằng SQLite backup hoặc sao chép đầy đủ khi đã đóng kết nối. Khởi tạo repository sẽ nâng schema lên 7; không sửa các revision CFR cũ.

CLI chạy từ thư mục `agent3_tax_compliance`; thay các giá trị bằng ID và đường dẫn DB đang có:

```powershell
.\.venv\Scripts\python.exe -m src.planning.cli --database "PATH_TO_EXISTING_DB.sqlite3" --tenant-id YOUR_TENANT --taxpayer-id YOUR_PAYER --actor-id YOUR_ACTOR --record-id YOUR_RECORD --revision 1
```

CLI là công cụ local cho chủ workspace, tự tạo access context theo scope được truyền. Không cung cấp CLI này cho người dùng không tin cậy như một cơ chế xác thực.

API dùng bearer token hiện có, kiểm quyền tenant/taxpayer:

```http
POST /v1/records/{record_id}/rule-plans?taxpayer_id={taxpayer_id}&revision=1
Authorization: Bearer YOUR_TOKEN

GET /v1/rule-plans/{evaluation_id}?taxpayer_id={taxpayer_id}
Authorization: Bearer YOUR_TOKEN
```

POST cần WRITE; GET cần READ. Cùng input/snapshot/code trả cùng evaluation ID, không tạo audit trùng. Artifact và snapshot lưu bất biến trong `rule_plans`, audit commit cùng transaction. API chưa nhận bằng chứng ledger, classification hoặc absence từ JSON do người gọi tự khai; ngữ cảnh mặc định để trống. Pure service hỗ trợ sidecar có scope và proof cho tích hợp tin cậy ở chặng sau.

## Nguồn pháp lý và catalog

[Bảng đối chiếu nguồn](legal_source_review.md). Muốn tải lại nguồn chính thức vào thư mục local bị gitignore:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\collect_plan07_legal.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\build_plan07_catalog.py
```

Collector ghi URL/hash/trạng thái tải, không xác minh chữ ký số. Builder chỉ tạo metadata DRAFT; không tự duyệt luật. Sau khi nguồn thay đổi phải đối chiếu PDF và chạy lại kiểm chứng; không chỉ đổi ngày snapshot. Phạm vi support catalog hiện kết thúc tại 15/10/2026 (exclusive), ngoài phạm vi trả lý do unsupported history.

## Bàn giao và phần còn mở

PLAN_08 có thể bắt đầu thử ZEN/Decimal/trace bằng rule tổng hợp và RulePlan đã pin; chưa bật rule thuế thực tế. Cần hoàn tất rà sửa đổi/chuyển tiếp, xác nhận từng rule và mapping hàng hóa/dịch vụ trước publish. Profile XML/bank chỉ là metadata chuẩn bị cho PLAN_10–11; không chứng nhận adapter đã được triển khai.
