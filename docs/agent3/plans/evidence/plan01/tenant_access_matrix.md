# Tenant/taxpayer access — v1

Ngày: 11/10/2026. Input: scope kỹ thuật và contracts `capture-foundation-v1`.

`AccessContext` phải do lớp authentication/authorization tin cậy tạo; không lấy actor/tenant/permissions trực tiếp từ JSON người dùng. Chưa có data endpoint trong app nền móng; PLAN_02/06 phải nối principal đã xác thực vào context trước khi mở dữ liệu.

| Quyền trong context | Đọc source/master/record/artifact/job/events | Ghi source/record/revision/artifact/job | Đăng ký taxpayer master |
|---|---|---|---|
| READ | Có, trong tenant và tập taxpayer được cấp | Không | Không |
| WRITE | Cần thêm READ nếu muốn đọc | Có, trong tenant và tập taxpayer được cấp | Không |
| ADMIN | Có | Có | Có |
| Khác tenant hoặc taxpayer không được cấp | Không | Không | Không |

Một context chỉ thuộc một tenant nhưng chứa nhiều taxpayer IDs. Mọi SELECT/INSERT/UPDATE của repository dùng tenant + taxpayer; composite keys/FKs không cho tham chiếu source hoặc revision của taxpayer khác. ADMIN vẫn chịu giới hạn tenant/taxpayer, không là quyền toàn hệ thống.

Source pin `taxpayer_master_revision`; record mới phải dùng đúng pin của source, các revision tiếp theo giữ nguyên pin. Master và raw append-only. Đổi master đang pin cần workflow có version/migration riêng, không âm thầm lấy latest.

`identity_match` trả MATCH/NO_MATCH/UNKNOWN theo ngày hiệu lực. Không cắt MST 13 số thành 10 số. Prefix giống nhưng không có BranchRelation có evidence đúng tenant/ngày → UNKNOWN; missing date/master ngoài hiệu lực → UNKNOWN. BranchRelation là hợp đồng để resolver dùng, chưa có API quản trị hoặc repository relation trong chặng này; production phải chỉ nạp relation đã phê duyệt. Tax code format không chứng minh MST tồn tại.

Tests kiểm khác tenant, khác taxpayer trong cùng tenant, viewer không được ghi, nhiều taxpayer/master revision, branch interval và missing-date behavior. Không suy ra đã có authentication service từ việc repository vượt tests.
