# Nối B5/E4 vào pipeline snapshot tại doanh nghiệp

14/11/2026 · CR-048 · kiểm chứng kỹ thuật trên nguồn mô phỏng.

Pipeline `score_snapshot` đã nối **B5/E4** khi đủ nguồn NCC. Cùng với **P1/E3**
hiện có, backend snapshot có bốn mã luật được hỗ trợ. Các luật khác vẫn trả
`unavailable` theo nguồn/evaluator; bộ native 35 luật không tự trở thành 35
luật trên snapshot hoặc HE.

## Những gì đã nối

Luồng JSON → kiểm tra → xác nhận lưu snapshot bất biến → resolve nguồn theo
hai đồng hồ → evaluator → RuleResult. API phân tích có xác thực gọi luồng này;
view quản lý có đầy đủ trạng thái, điểm, gaps và căn cứ trong
`rows[].rule_coverage.rules[]`. View người rà giữ giới hạn dữ liệu theo vai trò.

B5/E4 dùng thông tin master để tìm trùng tài khoản, điện thoại hoặc địa chỉ.
Trùng bank token/điện thoại có 3 điểm nội tại; chỉ địa chỉ là 1. Điểm đóng góp
giao dịch vẫn **0** theo policy master-quality của engine cũ. E4 là alias của
B5, cùng mã bằng chứng; không cộng hai lần hoặc đưa vào hàng đợi giao dịch.
Đối chiếu tài khoản này giữ cách so token của engine, chưa xác minh ngân hàng
và không thay B1.

## Nguồn cần cung cấp

Dùng JSON khai `contract_version: "1.2.0"`. Phiên bản opt-in mới chỉ thêm:

| Trường NCC | Ý nghĩa |
|---|---|
| `phone` | Số điện thoại dạng chuỗi, giữ số 0 đầu |
| `related_party_disclosed_at` | Thời điểm đã khai báo quan hệ liên quan |

Cần đủ `bank_account`, `phone`, `address`, `related_party_disclosed_at` cho
NCC đang xét và các NCC nhìn thấy trong tập so sánh. Không tự bỏ NCC thiếu
trường để tạo kết luận “không trùng”. Thiếu trường/null hoặc `missing_fields`
giữ hai luật chưa khả dụng. Chuỗi rỗng **do nguồn khai rõ** ở hai trường mới
nghĩa là không có điện thoại/khai báo trong master đã xuất; adapter không điền
chuỗi rỗng thay giá trị chưa biết. Contact dạng `UNKNOWN` không là đối chứng âm.

Mặc định schema vẫn 1.1.0; hai schema 1.0/1.1 và snapshot cũ không đổi. Không
chỉ sửa số phiên bản của dữ liệu cũ rồi tự thêm giá trị giả. Muốn có trường
mới cần xuất lại nguồn thực và tạo snapshot mới. Không tự migrate agent khác.

## Thử lại bằng bộ có sẵn

[Các JSON mẫu](../examples/vendor_identity_snapshots/README.md) có 10 gói,
hai DN × năm tình huống: trùng tài khoản/điện thoại, đối chứng, chỉ điện thoại,
chỉ địa chỉ và đã khai báo quan hệ. Nguồn/phê duyệt đều mô phỏng. Bộ này dành
cho B5/E4, không có hóa đơn/phân bổ nên P1 còn thiếu nguồn là đúng.

Từ `D:\agent22`:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_vendor_identity_snapshot.py --output-dir .runtime/vendor-snapshot-recheck-01
```

Chọn thư mục mới mỗi lần. Công cụ tự sinh nguồn, kiểm tra/lưu snapshot trong
kho thử tạm riêng, chạy pipeline snapshot rồi gọi độc lập engine cũ trên cùng
nguồn và thời điểm giao dịch. Mở `REPORT.md`/`report.json` trong thư mục kết quả.
Không cần khởi động hoặc đăng nhập Portal.

## Tính đúng thời điểm và giới hạn

Resolver chọn revision sau khi lọc cả `effective_at` và `observed_at` theo mốc
từng giao dịch; không dùng master mới nhất toàn bộ tệp. Revision/NCC tương lai
không thay kết quả quá khứ. Reference phải đúng revision/company/tenant;
checksum/source refs phải khớp. Ngày khai báo quan hệ không sau `observed_at`.

Để giữ parity với engine native, master chỉ được biết sau thời điểm giao
dịch làm B5/E4 `unavailable` với gap `native_master_not_known_at_event`; không
dời timestamp để ép chạy. Khai báo được nguồn cung cấp không phải xác minh
độc lập tính đầy đủ master hoặc quan hệ bên ngoài.

Không đổi 33 feature, kernel luật, ngưỡng, fit/active model hoặc trọng số.
Chấm vẫn trả mọi dòng và không tự fit. Đây là nối local/backend; chưa mở rộng
HE, cập nhật Portal live, đổi hàng đợi hoặc bằng chứng độ chính xác gian lận.

Xem [kết quả đối chiếu](../../Agent2_Spec_v2_1/evidence/R2/vendor_identity_snapshot_20261114/REPORT.md).
