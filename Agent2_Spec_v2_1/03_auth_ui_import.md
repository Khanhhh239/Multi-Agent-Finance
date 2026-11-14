# Auth, UI và import dùng chung

**BẮT BUỘC:** RULE-TENANT-01, RULE-UI-01, RULE-IMPORT-01, RULE-HE-01. Các yêu cầu hành vi trong file là bắt buộc trừ đoạn ghi ĐỀ XUẤT/CHƯA CHỐT. Tên trạng thái/schema phải dùng 04; nếu nguồn thuật ngữ cũ khác, dùng bảng migration ở 04. Import làm R1; phân quyền backend phải có ngay ở R1; hai UI hoàn chỉnh ở R5.

### A.1 Nguyên tắc

App có một hệ thống đăng nhập và phân quyền chung, hai không gian sử dụng theo vai trò. Không xây hai pipeline chấm khác nhau cho hai giao diện. Cùng một vụ, dữ liệu và kết luận được trình bày ở mức chi tiết phù hợp.

- Vai trò MVP: accountant (kế toán) và director (giám đốc), gắn với membership của từng DN. Một người có thể mang vai trò khác nhau tại các DN khác nhau.
- Backend kiểm tra quyền trên mọi API và tác vụ nền. Ẩn nút/menu không phải cơ chế phân quyền.
- company_id trong request không tự tạo quyền; xác minh user có membership/quyền tương ứng trước truy vấn.
- Director chỉ có quyền trong DN được cấp. Không mặc định director được quản trị nền tảng, xem DN khác hoặc lấy khóa bí mật.
- Hệ thống có thể dùng nhiều route trong cùng web; UI đổi theo quyền, API và dữ liệu vẫn dùng chung hợp đồng.

### A.2 Giao diện kế toán — giấu phương pháp, giữ căn cứ

Mục tiêu: người dùng biết cần kiểm tra gì mà không phải hiểu thuật toán ML.

Các màn hình:

1. Tổng quan việc cần làm: vụ mới, đang xử lý, chờ chứng từ, quá hạn.
2. Danh sách vụ có bộ lọc theo thời gian, loại vấn đề và trạng thái.
3. Chi tiết vụ: giao dịch ứng viên, giao dịch bằng chứng, chứng từ gốc, số liệu so sánh và hành động cần làm.
4. Nhập dữ liệu/báo lỗi đầu vào nếu được cấp quyền import.
5. Ghi nhận phản hồi, bổ sung bằng chứng và xem lịch sử xử lý.

Ẩn tên ECOD/IF/AE/Logistic, trọng số, hyperparameters, ma trận benchmark và phần chỉnh policy. Dùng diễn đạt nghiệp vụ, ví dụ “Khoản chi cao hơn mức thường gặp của NCC” thay cho tên detector. Mức ưu tiên không được trình bày thành xác suất gian lận.

Áp RULE-UI-01. API kế toán trả DTO theo allowlist; không gửi toàn bộ thông tin quản trị xuống browser rồi chỉ ẩn bằng CSS.

Kế toán được ghi phản hồi theo quyền được cấp. ĐỀ XUẤT MVP: phản hồi là kết quả rà soát của người thao tác; chỉ trở thành nhãn train confirmed sau bước xác nhận của giám đốc/người được ủy quyền. Đây là kiểm soát chất lượng nhãn, không xóa phản hồi ban đầu. Lưu case_workflow_status và label_approval_status riêng.

### A.3 Giao diện giám đốc — quản lý và chỉnh cấu hình

Các màn hình:

1. Dashboard chất lượng theo DN: vụ đúng, báo nhầm, tỷ lệ có kết luận, tải và thời gian rà soát.
2. Dữ liệu: trạng thái import, lỗi, thiếu năng lực, snapshot và lịch sử thay thế.
3. Cấu hình: ngân sách, ngưỡng, cách gộp và bật/tắt phương pháp trong các profile được hỗ trợ.
4. Đánh giá phiên bản: so cấu hình hiện tại/ứng viên, shadow, duyệt active và rollback.
5. Người dùng và quyền trong DN; nhật ký thay đổi và kết luận.
6. Nhãn và huấn luyện: duyệt nhãn, yêu cầu fit lại, trạng thái model không nhãn/TH1/TH2.
7. TH2: chọn tham gia phiên, phạm vi dữ liệu và quyền mở model theo giao thức; khóa vẫn do thành phần quản lý khóa ở DN xử lý.

Giám đốc chỉnh **cấu hình có schema**, không nhập code Python/SQL/biểu thức tùy ý chạy trên server. Model/luật mới phải qua adapter và validation. Hiển thị các metric kỹ thuật nâng cao khi cần, đồng thời giải thích tác động nghiệp vụ.

Luồng chỉnh: draft → validation → shadow → approved → active; có trạng thái rejected/failed. Lưu người sửa, lý do, diff và phiên bản. Không sửa trực tiếp bundle active hoặc cảnh báo lịch sử. Quyền giám đốc không bỏ qua release gate; ứng viên chưa đủ dữ liệu vẫn ở shadow. Chỉ đổi phân công/vai trò nghiệp vụ theo quyền, không cần chạy lại benchmark model cho thao tác quản lý người dùng.

### A.4 Ma trận quyền MVP

| Hành động | Kế toán | Giám đốc |
|---|---|---|
| Xem vụ, chứng từ trong phạm vi được giao | Có | Có trong DN |
| Xem căn cứ và hướng dẫn kiểm tra | Có | Có |
| Xem tên thuật toán, trọng số và benchmark | Không | Có |
| Nhập dữ liệu | Theo permission data.import | Có nếu được cấp permission tương ứng |
| Ghi phản hồi/bổ sung bằng chứng | Có trong vụ được phép | Có |
| Xác nhận nhãn dùng train | Không theo mặc định MVP | Có, hoặc ủy quyền rõ |
| Sửa ngưỡng, budget, grouping, model profile | Không | Tạo draft, qua gate |
| Duyệt active/rollback | Không | Có khi đạt điều kiện |
| Quản lý thành viên DN | Không | Có; không tự cấp quyền nền tảng |
| Đọc secret key DN khác / dữ liệu DN khác | Không | Không |

Schema bổ sung: User, CompanyMembership(user_id, company_id, role, status), Permission/RolePermission hoặc cơ chế tương đương, ConfigRevision, ReviewApproval và AuditEvent. Backend thực thi quyền trên upload, preview, commit, export, download, case detail, config, jobs và file bằng chứng.

### B.1 Kết luận kiến trúc

Có thể dùng chung màn nhập liệu, đăng nhập, mapping và thư viện/backend validation. Chưa kiểm tra web hiện tại nên chưa kết luận tái sử dụng được nguyên trạng; cần kiểm kê contract/API và vị trí xử lý dữ liệu.

Dùng một luồng: màn nhập chung → kiểm tra quyền/DN → kiểm tra nền tảng → kiểm tra profile Agent2 → preview lỗi/năng lực → commit snapshot hợp lệ → Agent2 tạo đặc trưng.

Không dựng một bộ validator riêng ở frontend Agent2 khác backend chung. Frontend có thể kiểm tra nhanh để phản hồi sớm; backend mới là nơi quyết định nhận dữ liệu. Nếu Agent khác có hợp đồng khác, gọi core validator + profile riêng, không bắt mọi dữ liệu phải thỏa toàn bộ Agent2.

### B.2 Ba lớp kiểm tra

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Shared core | Kiểu file/schema, parse số/ngày, trường chung, trùng ID, tenant | amount_vnd phải đúng kiểu và đơn vị; ID duy nhất trong DN |
| Agent2 profile | Năng lực phân tích, liên kết hóa đơn/chi trả, thời điểm quan sát, cột cho detector | Thiếu bank history chỉ tắt năng lực tương ứng |
| Training profile | Nhãn, split và feature contract/phiên mã hóa | Áp RULE-LABEL-01 |

Kiểm tra đầu vào không đồng nghĩa phát hiện rủi ro. Một giao dịch trùng thanh toán có thể là dòng nhập hoàn toàn hợp lệ về schema và phải chuyển sang Agent2 để phân tích; không chặn nó chỉ vì đáng ngờ.

### B.3 ValidationReport và import an toàn khi chạy lại

Report có import_id, company_id, source_hash, schema_version, validator_version, profile_version, parsed_snapshot_hash, status, counts, errors, warnings và capabilities. Mỗi lỗi gồm row/field nếu có, code, severity, message nghiệp vụ và cách sửa.

- Status: rejected / accepted_with_warnings / accepted.
- Lỗi phá hợp đồng quan trọng phải reject hoặc quarantine theo policy, không âm thầm bỏ dòng.
- Thiếu lịch sử/chứng từ bổ sung thường tạo warning và unavailable capability, không tự chặn mọi phương pháp.
- Preview và commit cùng import_id và cùng phiên bản dữ liệu đã kiểm; file/mapping thay đổi phải validate lại. Commit chỉ nhận báo cáo hợp lệ từ backend, không tin report do browser tự gửi.
- Chống nhập lặp bằng idempotency theo DN/import; commit transaction để không nửa chừng.
- File/snapshot đã dùng để chấm không bị ghi đè. Sửa dữ liệu tạo revision và quyết định chấm lại có audit.
- Cache kết quả theo hash dữ liệu, DN, mapping, contract/profile version và context liên quan; không dùng report của DN khác.
- Ghi nhãn riêng; không ép mọi dòng import phải có nhãn. Áp RULE-LABEL-01 cho nhãn.

API logic đề xuất, điều chỉnh theo web thật:

| API | Chức năng |
|---|---|
| POST /imports/preview | Upload/map, validate theo profile được phép; trả import_id và report |
| POST /imports/{id}/commit | Kiểm tra quyền và report chưa lỗi thời; tạo snapshot |
| GET /imports/{id}/report | Trả lỗi/cảnh báo và năng lực được phép xem |
| POST /agent2/runs | Nhận snapshot_id + as_of; backend chốt bundle theo quyền |
| POST /agent2/configs | Director tạo draft cấu hình; không đổi active ngay |

### B.4 Web chung không đồng nghĩa gom dữ liệu rõ lên cloud

Phân biệt dùng chung giao diện/module với dùng chung nơi lưu và chạy dữ liệu:

- Nếu web tổng chạy trong môi trường DN được phép xử lý sổ rõ: dùng chung API validation tại DN.
- Nếu web tổng là SaaS nhưng yêu cầu TH2 là cloud chỉ nhận ciphertext: file rõ phải được validation/feature/encrypt tại DN node trước upload; dùng chung thư viện validation triển khai tại DN. Không upload file rõ lên SaaS chỉ để kiểm tra rồi nói dữ liệu chưa rời DN.
- Cloud TH2 chỉ kiểm tra metadata, hash schema/context, manifest và các điều kiện ciphertext mà backend hỗ trợ. Không tuyên bố kiểm tra được nội dung nghiệp vụ của ciphertext như dữ liệu rõ.
- Kiểm tra client/browser đơn thuần không chứng minh dữ liệu thật hoặc nhãn đúng với cloud. Nếu cần chống client gian lận, thiết kế attestation/proof/giao thức riêng theo threat model.
- Hai giao diện kế toán/giám đốc đều dùng cùng import report đã phân quyền; không tạo hai bản dữ liệu hoặc hai chuẩn kiểm tra khác nhau.
