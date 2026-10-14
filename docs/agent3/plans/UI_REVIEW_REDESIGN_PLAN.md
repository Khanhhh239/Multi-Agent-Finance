# Kế hoạch thiết kế UI review chứng từ — 14/10/2026

## 1. Mục tiêu và phạm vi

Người nhập liệu/kế toán phải biết mình đang kiểm tra hóa đơn nào, trường nào cần xử lý, dữ liệu lấy từ đâu và thay đổi đã lưu hay chưa. Ưu tiên luồng tải chứng từ → theo dõi xử lý → đối chiếu → sửa/xác nhận → lưu → hoàn tất review.

Đây là kế hoạch thiết kế, chưa triển khai giao diện. Màn hình hiện tại là `/review`, dùng HTML/CSS/JavaScript và API PLAN_06. Giữ kiến trúc đó ở vòng đầu, không cần chuyển framework chỉ để đổi bố cục.

Không hiển thị trạng thái “hợp lệ về thuế”, “được khấu trừ”, “đúng 100%” hoặc confidence phần trăm khi hệ thống chưa có kết luận/calibration tương ứng. Hoàn tất review chỉ là hoàn tất nhập liệu có kiểm tra.

## 2. Vấn đề quan sát từ code hiện tại

- Kết nối, upload, danh sách và workspace nằm nối tiếp trên một trang dài; khó tập trung vào chứng từ đang mở.
- Danh sách chứng từ chủ yếu là record ID và revision; thiếu cách nhận diện thân thiện.
- Form xếp mọi trường và từng ô hàng hóa thành một danh sách dọc, khiến bảng nhiều dòng rất dài.
- Trạng thái `PRESENT`, `MISSING`, `AMBIGUOUS` xuất hiện trực tiếp; người dùng phải học thuật ngữ kỹ thuật.
- Nút xem nguồn nằm cạnh từng trường nhưng candidate lại ở vùng khác. Bấm candidate hiện vừa xem nguồn vừa điền giá trị, dễ gây thay đổi ngoài ý muốn.
- Người dùng phải nhập ngày ISO, tiền không phân nhóm và thuế suất dạng 0.08; dễ nhầm cách hiển thị với định dạng lưu.
- Lý do nhập bằng textarea, một số hành động dùng `prompt()`, lỗi chung đặt xa nơi thao tác.
- Khi correction trả 409, UI tải lại record và có thể làm mất phần đang nhập; cần thiết kế giữ và so sánh bản nháp.
- Upload chỉ xếp job; chưa có daemon tự chạy worker. Không thể giải quyết hoàn toàn bằng việc thêm spinner hay đổi chữ nút.
- Nút hoàn tất phụ thuộc job đang giữ trong phiên UI; cần xử lý rõ khi mở record từ danh sách hoặc tải lại trang.

## 3. Cấu trúc màn hình

### 3.1. Thanh đầu trang

- Tên ứng dụng: **Agent 3 · Kiểm tra chứng từ**.
- Đơn vị đang làm việc và trạng thái kết nối.
- Nút **Tải chứng từ**.
- Nút **Thiết lập kết nối** mở panel riêng; bản local vẫn nhập token/mã đơn vị/master revision tại đây, không giả lập đăng nhập production.
- Không lưu bearer token trong URL hoặc localStorage. Hết phiên phải kết nối lại và giữ nguyên quy tắc kiểm quyền phía server.

### 3.2. Danh sách chứng từ

Ưu tiên bảng gọn trên desktop, thẻ trên điện thoại. Các thông tin mong muốn: tên tệp, số hóa đơn, ngày lập, người bán, tổng tiền, trạng thái, lần cập nhật. Chỉ hiển thị cột khi API có dữ liệu; thiếu thì ghi “Chưa đọc được”, không lấy thông tin mẫu thay thế.

Giai đoạn đầu dùng danh sách record đã xử lý hiện có và trạng thái job của lượt upload đang mở. Danh sách mọi job đang chờ, lọc toàn hệ thống, tìm kiếm theo số hóa đơn và thống kê tổng cần API hỗ trợ; không tìm/lọc một trang dữ liệu rồi trình bày như toàn bộ kết quả.

Chọn chứng từ để vào workspace. Desktop có thể thu gọn danh sách thành thanh bên; mobile chuyển màn hình. Khi có thay đổi chưa lưu, cảnh báo trước khi đổi chứng từ, đơn vị hoặc rời trang.

### 3.3. Workspace đối chiếu

```text
Đơn vị: ...  /  Số hóa đơn: ...              [Lịch sử] [Xuất dữ liệu]
Trạng thái: Cần kiểm tra · Bản 2 · Có thay đổi chưa lưu
───────────────────────────────────────────────────────────────────
 HÓA ĐƠN GỐC — khoảng 55%         DỮ LIỆU — khoảng 45%
 [Trang 1/2] [−] [+] [Vừa trang]   [Tất cả] [Cần kiểm tra] [Đã xác nhận]
                                  Thông tin hóa đơn
                                  Người bán / Người mua
  Trang hóa đơn                    Dòng hàng
  + vùng nguồn đang chọn           Tổng tiền
                                  Chi tiết trường đang chọn
───────────────────────────────────────────────────────────────────
 3 trường đã thay đổi              [Lưu thay đổi] [Hoàn tất kiểm tra]
```

Tỷ lệ là điểm khởi đầu; cho kéo đường phân cách trên desktop. Trên màn hình vừa dùng hai cột khi đủ rộng; màn hình hẹp dùng hai tab **Dữ liệu / Hóa đơn gốc**, giữ trường và trang đang chọn khi chuyển tab.

Nguồn và form có vùng cuộn phù hợp chiều cao cửa sổ. Phải kiểm tra cuộn bàn phím, focus và zoom trình duyệt để tránh nhốt người dùng trong vùng cuộn. Thanh hành động không che trường cuối.

## 4. Tương tác chi tiết

### 4.1. Xem nguồn và candidate

1. Chọn một trường: highlight hàng dữ liệu và vùng nguồn tương ứng.
2. Tự chuyển đúng trang; cuộn vùng nguồn vào khung nhìn và giữ mức zoom hữu ích.
3. Panel ngay dưới trường hiển thị **Chữ đọc từ nguồn**, **Giá trị chuẩn hóa**, nguồn PDF/OCR khi có metadata và các candidate cạnh tranh.
4. **Xem vị trí** chỉ điều hướng; **Dùng giá trị này** mới thay đổi input. Không đánh dấu đã xác nhận chỉ vì người dùng mở bằng chứng.
5. Với trường thiếu bằng chứng, thông báo rõ “Chưa tìm thấy vùng nguồn; hãy đối chiếu toàn trang”. Không highlight ngẫu nhiên một vùng.

Chỉ tự chuyển nguồn khi người dùng chọn trường/candidate, không nhảy ảnh liên tục theo từng ký tự họ đang nhập. Có thể cache ảnh trong phiên, đúng tenant/record, làm mới evidence grant hết hạn và không đưa token vào URL.

### 4.2. Ngôn ngữ trạng thái

| Dữ liệu backend | Nhãn UI | Cách dùng |
|---|---|---|
| PRESENT, chưa có human proof | Đã đọc được · Chưa xác nhận | Màu trung tính; có giá trị không đồng nghĩa đúng |
| MISSING | Chưa đọc được | Nhắc bổ sung sau khi xem nguồn |
| AMBIGUOUS | Cần chọn hoặc đối chiếu | Cho xem từng cách hiểu, không tự điền candidate đầu tiên |
| NOT_APPLICABLE | Không áp dụng | Hiển thị nguyên nhân nếu có, không coi là thiếu dữ liệu |
| HUMAN_CONFIRMED | Đã xác nhận | Dựa trên proof server trả về, không dựa vào checkbox chưa lưu |
| Đã sửa nhưng chưa lưu | Có thay đổi chưa lưu | Trạng thái cục bộ, phân biệt với đã xác nhận |

Luôn có chữ/icon ngoài màu. Mã kỹ thuật nằm trong panel chi tiết dành cho debug, không chiếm vị trí chính. Không chuyển detection score thành “độ chính xác OCR”.

### 4.3. Form thông tin

- Nhóm **Thông tin hóa đơn**, **Người bán**, **Người mua**, **Tổng tiền**. Cho thu gọn nhưng luôn hiện số vấn đề còn lại của nhóm nếu có count đầy đủ.
- Tên/địa chỉ dài dùng input hoặc textarea đủ chỗ, có thể mở rộng; không cắt mất phần cần đối chiếu.
- MST là chuỗi, giữ số 0 đầu; có hướng dẫn dạng 10/13 số và lỗi ngay cạnh trường.
- Ngày hiển thị dễ đọc, chuyển sang ISO khi gửi API sau validation; không parse ngày bằng suy đoán locale của trình duyệt.
- Tiền hiển thị phân nhóm khi không sửa, giữ giá trị Decimal dạng chuỗi. Khi sửa, có quy ước định dạng rõ ràng và bản xem trước giá trị sẽ lưu; không dùng float JavaScript để tính/lưu tiền.
- Thuế suất có thể hiện 8% thay cho 0.08, chuyển đổi bằng thao tác chuỗi/chính xác. KCT và KKKNT là lựa chọn riêng, không chuyển thành 0%.
- Checkbox nếu giữ lại phải ghi “Đưa vào lần lưu này”, tránh bị hiểu là server đã xác nhận. Người dùng sửa input thì tự thêm vào bản nháp; muốn xác nhận một giá trị không sửa phải có hành động tường minh.

### 4.4. Dòng hàng

Desktop dùng bảng: STT, tên hàng, số lượng, đơn giá, tiền trước thuế, nhóm thuế, thuế suất, trạng thái. Giữ ID bất biến phía sau, không dùng số thứ tự làm khóa cập nhật.

- Chọn ô để sửa và xem nguồn; tên hàng xuống dòng được mở rộng.
- Vấn đề cụ thể đặt ở ô tương ứng, không chỉ báo chung cả bảng.
- Nhiều dòng: pagination hoặc virtual rendering sau khi đo, không tải/xác nhận ngầm những dòng chưa xem.
- Mobile dùng một thẻ cho mỗi dòng hoặc bảng cuộn có hướng dẫn; nút lưu không bị cuộn khỏi vùng thao tác.
- Chưa có backend thêm/tách/gộp dòng: hiển thị **Báo thiếu/sai dòng** dẫn đến yêu cầu dữ liệu/xử lý riêng, không vẽ nút thao tác như thể đã hỗ trợ.
- Xác nhận đủ hàng phải là bước riêng sau khi xem toàn bộ trang và đối chiếu số dòng; không tự bật khi sửa một ô.

### 4.5. Upload và tiến độ

Luồng thể hiện: **Đã nhận tệp → Đang chờ → Đang xử lý tài liệu/OCR → Đang đánh giá → Cần kiểm tra**. Bám đúng state server; không khẳng định OCR đang chạy khi mới QUEUED và không vẽ phần trăm giả.

- Giới hạn loại tệp/dung lượng lấy từ cấu hình đã xác định; backend vẫn kiểm tra lại.
- Có tên tệp và thời điểm tải lên; không hiển thị dữ liệu nhạy cảm trong log/toast không cần thiết.
- QUEUED lâu: ghi “Đang chờ tiến trình xử lý”. Với bản local, có mục hướng dẫn kỹ thuật thu gọn để copy lệnh worker cho job hiện tại. Chỉ bỏ bước terminal sau khi thực sự có worker daemon và cơ chế vận hành.
- PROCESSING_ERROR: giải thích lỗi dễ hiểu, các hành động retry/yêu cầu nguồn mới chỉ xuất hiện khi server cho phép; retry không đồng nghĩa đang chạy ngay.
- Tài liệu nhiều hóa đơn: màn hình xử lý riêng, không mở một form CFR trống như kết quả thành công.
- Lựa chọn quy ước số VI/EN/AUTO trên UI chỉ được bật khi API/job lưu và truyền profile đến worker; thay dropdown frontend đơn thuần không giải quyết chuyện này.

### 4.6. Lưu, xung đột và hoàn tất

- Thanh cuối hiển thị số trường có thay đổi, trạng thái lưu và hành động chính **Lưu thay đổi**.
- Dialog/panel tóm tắt trước/sau và lý do. Có lý do gợi ý như “Đối chiếu hóa đơn gốc”, vẫn yêu cầu người dùng lựa chọn; không tự sinh bằng chứng xác minh.
- Giữ task_id và expected_revision đúng hợp đồng; không tự chọn task bất kỳ chỉ để gửi correction thành công.
- Một correction tối đa 32 trường. Hiển thị giới hạn ở UI; nếu chia lô phải cập nhật revision và giải thích khả năng lưu một phần khi lô sau thất bại. MVP ưu tiên ngăn gửi quá giới hạn thay vì giả lập transaction nguyên tử nhiều lô.
- Gửi lỗi: giữ bản nháp, đánh dấu trường lỗi; không xóa mọi giá trị người dùng vừa nhập.
- 409: giữ bản nháp tạm trong bộ nhớ, tải revision mới để so sánh, cho người dùng chọn áp lại từng thay đổi. Không tự ghi đè bản mới của người khác.
- **Hoàn tất kiểm tra** dựa trên kiểm tra server và trạng thái hiện hành. Nếu còn chặn, hiện danh sách và link tới việc cần làm. Không chỉ dựa vào count của task đã tải một trang.
- Nếu chưa thể xác định job của record được mở lại, giải thích giới hạn; cần bổ sung API mapping trước khi thiết kế nút hoàn tất hoạt động cho mọi record.
- Xuất JSON được ghi rõ là bản dữ liệu tại revision nào, có thể còn vấn đề chưa giải quyết. Lịch sử trình bày actor/thời điểm/lý do/trường thay đổi trong phạm vi dữ liệu API cho phép; JSON kỹ thuật ở mục mở rộng.

## 5. Thiết kế thị giác và khả năng tiếp cận

Giữ nền sáng, chữ đậm dễ đọc và màu xanh teal của UI hiện tại. Giảm header lớn và thông báo dài trong workspace. Hạn chế liên quan chứng từ đặt gần hành động tương ứng; vẫn có ghi chú ngắn về giới hạn của bản MVP.

- Font hệ thống hỗ trợ tiếng Việt, nội dung chính khoảng 14–16 px, không thu bé để nhét nhiều dữ liệu.
- Khoảng cách nhất quán theo bội số 4/8 px; đường viền nhẹ để phân nhóm.
- Màu trung tính cho đã đọc, cam cho cần đối chiếu, đỏ cho lỗi chặn, xanh cho đã xác nhận; mỗi trạng thái kèm nhãn.
- Focus rõ, dùng bàn phím đến được mọi input/candidate/action. Không dùng phím tắt toàn cục ghi đè hành vi nhập liệu; phím chuyển trường/vấn đề cần được công bố và thử nghiệm.
- Nhãn input liên kết đúng; thông báo lỗi gắn aria-describedby và trạng thái tải/lưu có live region phù hợp.
- Zoom 200%, màn hình 1366×768, 1920×1080, tablet và mobile phải không che nút hoặc mất dữ liệu. Bảng có cuộn ngang được giới hạn trong vùng bảng.

## 6. Thứ tự triển khai và điều kiện nghiệm thu

Ước lượng cho một developer quen code, chưa tính chờ người dùng nghiệm thu. Không phải cam kết lịch; chốt lại sau prototype.

| Đợt | Công việc | Ước lượng | Điều kiện hoàn thành |
|---|---|---|---|
| UI-01 | Wireframe + mapping state/API + bộ nhãn tiếng Việt | 0.5–1 ngày | Thống nhất luồng, ghi rõ tính năng thiếu API, không đổi backend |
| UI-02 | Workspace hai cột, nhóm trường, thanh hành động, responsive | 1–2 ngày | Thử được trên desktop/mobile, không mất field/action hiện có |
| UI-03 | Zoom/pan, chọn trường highlight nguồn, candidate tách xem/dùng | 1–2 ngày | Đổi trang chính xác, crop/evidence đúng, xem không gây sửa |
| UI-04 | Bảng hàng, nhập ngày/tiền/thuế thân thiện, bản nháp và lỗi cạnh trường | 2–3 ngày | Giữ Decimal/ID, KCT/KKKNT đúng, không mất sửa khi lỗi |
| UI-05 | Tiến độ upload, review task, save/409/complete và lịch sử dễ đọc | 1–2 ngày | Không giả trạng thái, không hoàn tất khi server còn chặn |
| UI-06 | Browser acceptance, bàn phím, zoom/mobile và người dùng thử | 1–2 ngày | Bằng chứng kiểm tra theo checklist bên dưới và lỗi lớn đã xử lý |

Tổng vòng frontend đầu khoảng **7–12 ngày làm việc**. API bổ sung/worker daemon là phạm vi riêng, chưa cộng vào ước lượng.

Ưu tiên UI-02/UI-03 trước: cải thiện việc đối chiếu mà không chờ nâng cấp OCR. Chưa làm dashboard biểu đồ lớn, quản lý vai trò/SSO hoặc thiết kế màn hình kết luận thuế ở vòng này.

## 7. Phần cần API/backend hỗ trợ, không giả lập ở frontend

| Nhu cầu | Hiện trạng cần xử lý trước khi bật |
|---|---|
| Tên tệp/số hóa đơn/tổng tiền trong danh sách, tìm kiếm toàn bộ | Rà payload list; bổ sung summary/query với tenant filter và pagination nếu thiếu |
| Dropdown chọn đơn vị thay cho nhập taxpayer ID | Cần nguồn danh sách đơn vị được cấp quyền và master revisions; không hardcode đơn vị thật |
| Danh sách mọi job, khôi phục theo dõi sau reload | Cần API list/mapping job và record phù hợp quyền |
| Số vấn đề/tổng tiến độ đầy đủ | Dùng assessment/server count đầy đủ, hoặc bổ sung aggregate; không lấy length của một trang task |
| Chọn VI/EN/AUTO khi upload | Lưu profile vào job, truyền đến extraction và giữ audit/idempotency nhất quán |
| Upload rồi tự xử lý | Cần daemon/queue worker thực, lease/retry/recovery hiện có; không chạy tác vụ dài trong HTTP handler |
| Xem before/after trong lịch sử | Chỉ hiển thị chi tiết được API và quyền cho phép, không mở rộng payload audit nhạy cảm tùy tiện |

## 8. Kịch bản nghiệm thu

Thử trước với VNPT, CyberBill, FAST/KCT và MISA đã tải local. Có thể thêm trang học kế toán để thử đa thuế suất nhưng không coi đó là kiểm chứng độc lập trên giao dịch thực.

1. Người mới kết nối, upload và hiểu đang chờ worker hay đang xử lý; không nhầm đã upload là đã đọc xong.
2. Chọn MST người bán → mở đúng trang/vùng nguồn → sửa hoặc xác nhận → lưu → mở lại vẫn thấy revision đúng.
3. Chọn AMBIGUOUS → thấy các cách hiểu và nguồn; chỉ xem một candidate không làm thay đổi dữ liệu.
4. Nhập số tiền/ngày sai định dạng → báo cạnh ô, giữ nguyên các sửa khác; không làm mất số 0 đầu MST.
5. Bảng dài, mô tả nhiều dòng, KCT/KKKNT và nhóm đa thuế suất hiển thị rõ; không tự xác nhận đủ hàng.
6. Hai phiên sửa cùng record → phiên sau nhận xung đột và vẫn giữ được bản nháp để đối chiếu.
7. Token hết hiệu lực, tải ảnh lỗi, job lỗi, quá giới hạn correction và tài liệu cần tách đều có hướng xử lý rõ.
8. Record mở từ danh sách/reload không hiển thị nút hoàn tất như thể đã có job mapping nếu chưa hỗ trợ.
9. Dùng bàn phím, zoom 200% và mobile không mất action hoặc focus.
10. Xác nhận hoàn tất không biến thành kết luận thuế; export phản ánh đúng revision và vấn đề còn lại.

Chỉ số usability cần đo: thời gian tìm đúng nguồn, thời gian review một hóa đơn, số thao tác, lỗi nhập và số lần cần hỏi người hướng dẫn. Đặt mục tiêu giảm thời gian review khoảng 30% so với UI hiện tại sau khi đo baseline trên cùng tập tác vụ và người dùng; đây là mục tiêu thử nghiệm, chưa phải kết quả đạt được.
