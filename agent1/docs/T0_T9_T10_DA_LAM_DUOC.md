# T0, T9 và T10: phần đã triển khai và cách demo

**Cập nhật:** 11/11/2026.

**Phạm vi:** Agent 1 trong workspace hiện tại, gồm cả các thay đổi chưa commit.

Tôi đã triển khai được luồng từ nhập chứng từ, kiểm tra dữ liệu, đối soát khoản thu đến giải thích kết quả dự báo. T0 tạo dữ liệu đầu vào có kiểm tra và lịch sử; T9 nối khoản tiền đã nhận với hóa đơn sau khi được duyệt; T10 giúp người dùng hiểu dự báo, thứ tự ưu tiên thu nợ và ảnh hưởng của các giả định thu chi.

| Phần | Kết quả đã có | Nơi có thể trình diễn |
| --- | --- | --- |
| **T0 — Nhập và kiểm tra dữ liệu** | Đọc file, ghép cột, kiểm tra tiền/ngày/tham chiếu, xử lý vòng đời hóa đơn, lưu phiên bản và tra cứu nguồn | Dữ liệu, Sổ dữ liệu |
| **T9 — Đối soát khoản thu** | Tạo đề xuất, xem ứng viên, duyệt hoặc từ chối, phân bổ thủ công có bằng chứng, đảo quyết định và cập nhật công nợ | Dữ liệu → Đối soát khoản thu · T9 |
| **T10 — Giải thích và hỗ trợ quyết định** | Giải thích xác suất tất toán, giải thích ưu tiên, phân rã dòng tiền, so sánh kịch bản và xuất Excel | Dự báo |

Các kết quả dưới đây chứng minh chức năng phần mềm và tính nhất quán trên các ca kiểm thử. Chúng chưa phải kết luận về độ chính xác hoặc hiệu quả tài chính trên doanh nghiệp thật.

## 1. T0 — Nhập, chuẩn hóa và kiểm tra dữ liệu

### Những việc đã làm được

1. **Nạp dữ liệu từ CSV, Excel và XML hóa đơn điện tử.** Workspace cho chọn bảng, sheet, ghép cột Việt/Anh và định dạng ngày/số tiền. XML dùng bộ đọc chứng từ riêng. Bản xem trước báo lỗi trước khi người dùng xác nhận ghi.
2. **Kiểm tra dữ liệu kế toán.** Kiểm tra mã, khách hàng, ngày lập, hạn trả, tiền tệ và số tiền. Chứng từ kế toán đầy đủ được kiểm MST, ký hiệu/số hóa đơn và quan hệ tiền trước thuế + VAT = tổng thanh toán. Bảng hóa đơn đơn giản được cảnh báo về phạm vi kiểm tra còn thiếu.
3. **Giữ số tiền chính xác.** Workspace xử lý VND nguyên đồng, chặn phần lẻ và giá trị không hợp lệ; số lớn được giữ chính xác qua nhập liệu, phân bổ và xuất báo cáo. Luồng ingest đầy đủ có tiền theo đơn vị nhỏ nhất của từng loại tiền tệ; mô hình Workspace hiện dùng VND.
4. **Kiểm soát trùng và sửa dữ liệu.** Retry cùng mã/nội dung không cộng thêm dữ liệu. Sửa nội dung cần tuân thủ phiên bản và ngày biết thông tin. XML và ERP của cùng chứng từ được đối chiếu để hợp nhất nguồn, tránh tạo hai khoản nợ.
5. **Xử lý vòng đời hóa đơn.** Có hóa đơn gốc, thay thế, điều chỉnh tăng/giảm và sự kiện hủy. Công nợ được tính theo chứng từ có hiệu lực; khoản thu đi theo chuỗi thay thế. Điều chỉnh và hủy không được biến thành tiền đã vào ngân hàng.
6. **Kiểm tra sao kê.** Đối chiếu kỳ, chiều thu/chi và phương trình số dư. Khi có danh mục tài khoản được duyệt, kiểm tra phạm vi tài khoản và bằng chứng đi kèm. Không coi một kỳ hoặc tài khoản chưa có dữ liệu là đã được đối chiếu đầy đủ.
7. **Lưu lịch sử theo thời điểm thông tin được biết.** Phân biệt ngày nghiệp vụ với `known_at`/`available_on`. Snapshot lịch sử không tự nhìn thấy bản sửa đến muộn. Luồng sửa nguồn trên Workspace còn giữ thời điểm sửa để xử lý nhiều thay đổi trong cùng ngày.
8. **Tra cứu và kiểm toán.** Sổ dữ liệu có tìm kiếm, lọc, phân trang, chi tiết bản ghi, phiên bản cũ và liên kết hóa đơn → thanh toán → sao kê → quyết định T9. Lịch sử nhập lưu số dòng mới/sửa/trùng/lỗi và biến động công nợ.

**Giá trị sử dụng:** người dùng kiểm tra được dữ liệu trước khi đưa vào công nợ và dự báo; khi có sai sót vẫn truy lại được bản cũ và phạm vi bị ảnh hưởng.

### Giới hạn cần trình bày đúng

- Kiểm tra cấu trúc và số liệu XML chưa chứng minh chữ ký số hay tính xác thực của hóa đơn ngoài đời thực.
- Danh mục tài khoản có bằng chứng giúp kiểm soát phạm vi đã khai báo; phần mềm chưa tự chứng minh doanh nghiệp đã khai đủ mọi tài khoản.
- Không tự quy đổi ngoại tệ để đưa vào dự báo VND. Không suy dữ liệu thiếu thành hóa đơn chưa trả hoặc sao kê không phát sinh.

## 2. T9 — Đối soát tiền ngân hàng với công nợ

### Những việc đã làm được

1. **Tích hợp lõi đối soát vào Workspace.** Adapter sử dụng bộ chấm điểm, phân bổ có ràng buộc và sổ quyết định đã có, kết nối chúng với dataset của từng doanh nghiệp và API `/v1/`.
2. **Tạo đề xuất từ dữ liệu quan sát được.** Dùng số tiền, khách hàng/người chuyển, nội dung chuyển khoản và tham chiếu hóa đơn; kiểm tra ngày và phần dư nợ còn mở trước khi ghép.
3. **Xử lý nhiều kiểu thanh toán.** Có một khoản tiền trả nhiều hóa đơn, một hóa đơn trả nhiều lần, thanh toán một phần và khoản còn dư chưa phân bổ. Khoản đã nhập trước đó được tính vào giới hạn, tránh thu trùng.
4. **Giữ ca mơ hồ để kiểm tra.** Khi có nhiều nhóm hóa đơn cùng phù hợp, thiếu khách hoặc xung đột tham chiếu, hệ thống đưa vào hàng chờ. Điểm gợi ý được trình bày như bằng chứng hỗ trợ, không gọi là xác suất ghép đúng.
5. **Có quy trình duyệt rõ ràng.** Người dùng xem đề xuất, nhập người xử lý rồi duyệt từng giao dịch; có thể từ chối kèm lý do hoặc phân bổ thủ công với bằng chứng. Đề xuất và từ chối chưa làm giảm công nợ.
6. **Kiểm soát giới hạn phân bổ.** Không vượt tiền sao kê, dư nợ hóa đơn hoặc chuyển tiền sang sai khách. Khoản vay, bán thu ngay và tiền ra không được tự ghép thành thu công nợ khách hàng.
7. **Ghi quyết định và dữ liệu cùng giao dịch.** Sau khi duyệt, payment và dataset dự báo được cập nhật cùng sổ quyết định. Retry không tạo phân bổ lần hai; lỗi ghi dữ liệu không để lại quyết định đã ghi dở.
8. **Đảo quyết định và sửa nguồn có lịch sử.** Đảo phân bổ mở lại công nợ nhưng giữ giao dịch ngân hàng và quyết định cũ. Sửa chứng từ nguồn có bước xem trước, đảo quyết định bị ảnh hưởng và kiểm tra lại số dư; đề xuất cũ phải được tạo lại.

**Giá trị sử dụng:** tiền đã vào ngân hàng được nối với đúng công nợ, có người duyệt và đường truy vết. Hệ thống giữ riêng số tiền đã nhận, số tiền đã phân bổ và phần còn chờ xác minh.

### Giới hạn cần trình bày đúng

- Trạng thái đề xuất `auto` nghĩa là có phương án đủ điều kiện đề xuất; trên Workspace vẫn cần thao tác duyệt.
- Thiếu vài nghìn đồng chưa được tự coi là phí ngân hàng hoặc tự xóa nợ.
- Khả năng chạy đúng các ca chức năng chưa chứng minh tỷ lệ đối soát đạt yêu cầu trên mọi doanh nghiệp. Các kết quả nghiên cứu T9 cũ không tự trở thành kết quả của adapter Workspace hiện tại.

## 3. T10 — Giải thích dự báo và hỗ trợ người sử dụng

### Những việc đã làm được

**Giải thích xác suất tất toán hóa đơn.** Trong Khoản cần chú ý, mỗi hóa đơn có thể mở kết quả giải thích xác suất tất toán trong **4 tuần**. Lõi dùng Shapley trên đủ 64 tổ hợp của sáu nhóm đầu vào: giá trị hóa đơn, kỳ hạn, lịch sử trễ của khách, lịch sử trễ doanh nghiệp, lượng lịch sử của khách và tuổi hóa đơn. Kết quả được kiểm tra cộng khớp với đúng xác suất đang hiển thị, kể cả khi phối hợp nhiều mô hình.

**Lọc lý do trước khi đưa lên giao diện.** Có kiểm tra độ nhạy theo mẫu nền, mức hỗ trợ dữ liệu và bằng chứng lịch sử. Giao diện chỉ chọn tối đa ba yếu tố đủ điều kiện; không đủ bằng chứng thì nói rõ chưa đủ cơ sở. Kỳ hạn và số lượng lịch sử được giữ làm thông tin đầu vào, không tự suy thành lý do khách trả tốt hoặc xấu. Hệ số ngưỡng hiện tại là quy tắc lọc sản phẩm, chưa phải chứng nhận thống kê.

**Giải thích thứ tự ưu tiên thu nợ.** Nút Vì sao ưu tiên? cho biết chính sách, công thức, điểm, khoản được so sánh và cách xử lý bằng điểm. Các chính sách hiện có là dư nợ, nguy cơ chưa tất toán, hoặc dư nợ × nguy cơ. Xác suất dùng để xếp hạng có nguồn riêng và không bị đánh đồng với xác suất dự báo đã áp kịch bản. Tranh chấp, lời hứa và quá hạn là thông tin xử lý, không tự được cộng điểm ngoài công thức.

**Phân rã dòng tiền.** Xem dự thu theo từng hóa đơn, khách hàng và tuần; lịch chi và phần thu/chi hoạt động được ghi riêng. Bảng đối chiếu giữ đúng:

```text
Số dư cuối tuần = Số dư đầu tuần + Dự thu trong tuần − Dự chi trong tuần
```

Phân rã dùng toàn bộ công nợ thuộc phạm vi dự báo, kể cả hóa đơn đang tạm hoãn liên hệ; không chỉ dùng các khoản đứng đầu danh sách ưu tiên. Cảnh báo chỉ ra tuần cần chú ý, khách hàng còn phụ thuộc và các khoản chi lớn.

**So sánh kịch bản.** Người dùng có thể tạo kế hoạch với giả định thu chậm, thay đổi chi và rủi ro chung theo khách. Phần phân rã còn có so sánh thu sớm/chậm 2 tuần từ kế hoạch đang xem, chỉ dịch phần dự thu trong kỳ và ghi riêng phần bị đẩy ra ngoài kỳ.

**Lưu và xuất kết quả.** Kế hoạch giữ ngày chốt, phiên bản mô hình, hash dữ liệu, giả định và kết quả giải thích. Excel có các bảng kế hoạch/ưu tiên cùng sáu sheet phân rã: Phân rã từng tuần, Thu theo hóa đơn, Thu theo khách, Lịch chi đã biết, So sánh thời điểm và Kịch bản từng tuần.

Trong mã nghiên cứu `models/t10.py` còn có đóng góp mô hình, mô phỏng thu sớm một hóa đơn, dời chi và thư viện kịch bản. Báo cáo này phân biệt phần mã nghiên cứu đó với các thao tác đã có trên Workspace nêu trên.

### Giới hạn cần trình bày đúng

- Giải thích SHAP mô tả ảnh hưởng lên dự báo, không chứng minh nguyên nhân kinh doanh hoặc hiệu quả của việc gọi điện thu nợ.
- Xác suất tất toán trong 4 tuần khác với tỷ lệ tiền dự kiến thu trong toàn kỳ; không lấy một xác suất rồi nhân lại toàn bộ dư nợ để giải thích mọi dòng tiền.
- So sánh sớm/chậm 2 tuần trong bảng phân rã là độ nhạy số dư kỳ vọng, chưa mô phỏng lại P10/P90 hoặc xác suất thiếu tiền. Phần phân rã số dư chưa phải SHAP của rủi ro thiếu tiền.
- Kế hoạch cũ thiếu các trường giải thích mới cần được tạo lại để có đầy đủ chi tiết; không tự suy thêm lý do cho kết quả cũ.

## 4. Chuẩn bị demo cả ba phần

Nên chia thành hai màn: bộ core nhỏ để trình bày T0/T9 có đáp án rõ, rồi bộ Đại Phát có lịch sử dài hơn để trình bày T10. Cả hai đều là dữ liệu mô phỏng và dùng kho riêng. Bộ core không cần huấn luyện; không dùng bộ này để hứa hẹn một bản mô hình học hoặc đầy đủ lý do nghiệp vụ.

| Màn demo | Bộ dữ liệu | Địa chỉ | Thời lượng trình bày gợi ý |
| --- | --- | --- | --- |
| T0 + T9 | `pilot/t0_t9_uat_20261110/01_core` | `http://127.0.0.1:8021/workspace#data` | 8–10 phút |
| T10 | `pilot/demo_dai_phat` | `http://127.0.0.1:8022/workspace` | 5–8 phút |

Chuẩn bị và nạp dữ liệu trước buổi trình bày. Nếu muốn trình bày phiên bản đã học, hoàn tất kiểm định và chọn phiên bản trước; dự báo theo mốc lịch sử vẫn dùng được khi chưa chọn mô hình. Khi không đủ cơ sở giải thích, giữ nguyên thông báo đó.

### 4.1. Khởi động kho T0/T9

Từ **thư mục gốc repository**, mở PowerShell và chạy:

```powershell
.\agent1\pilot\t0_t9_uat_20261110\Start-Uat.ps1 -Suite core -RunId demo1111 -Port 8021
```

Mở `http://127.0.0.1:8021/workspace#data`, bấm Kết nối rồi lấy khóa từ đường dẫn script in ra. Với lệnh này, kho nằm ở `agent1/.state-uat-core-demo1111`, khóa nằm ở thư mục bên cạnh có hậu tố `-keys`. Dừng bằng Ctrl+C. Muốn một lần demo sạch khác, đổi `RunId`; giữ tên cũ sẽ mở lại dữ liệu đã lưu.

### 4.2. Khởi động kho T10

Môi trường hiện tại có Python ở `.venv` tại gốc repository. Trong **một cửa sổ PowerShell mới**, cũng đứng tại gốc repository, chạy:

```powershell
$demoRepo = (Get-Location).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $demoRepo 'agent1'
$env:AGENT1_STATE_DIR = Join-Path $demoRepo 'agent1/.state-business-firm-DEMO_T10_1111-data'
$env:AGENT1_KEY_DIR = $env:AGENT1_STATE_DIR + '-keys'
$env:AGENT1_FIRM_ID = 'DEMO_T10_1111'
$env:AGENT1_RESEARCH_MODE = '0'
$env:AGENT1_DEMO_TRAINING = '1'
$env:AGENT1_THREADS = '4'
$env:OMP_NUM_THREADS = '4'
.\.venv\Scripts\python.exe -m uvicorn agent1_service.main:app --app-dir agent1 --host 127.0.0.1 --port 8022
```

Mở `http://127.0.0.1:8022/workspace#data`; khóa ở `agent1/.state-business-firm-DEMO_T10_1111-data-keys/api-token.txt`. Nếu đã có kho cùng tên thì đây là dữ liệu cũ của lần demo trước; muốn kho mới, đổi đồng thời mã `DEMO_T10_1111` trong tên thư mục và `AGENT1_FIRM_ID`.

Đây là lệnh khởi động và hướng dẫn để người trình bày thực hiện; lần soạn báo cáo này không khởi động thêm dịch vụ hoặc ghi dữ liệu vào các kho demo đó.

## 5. Kịch bản demo T0

Tại cổng **8021**, vào Dữ liệu. Chọn ngày **ISO / yyyy-mm-dd** và số tiền **plain / không dấu phân nhóm**. Nạp lần lượt các file trong `agent1/pilot/t0_t9_uat_20261110/01_core/`:

| Thứ tự | File | Loại bảng |
| --- | --- | --- |
| 1 | `01_invoices.csv` | Hóa đơn |
| 2 | `02_bank.csv` | Sao kê ngân hàng |
| 3 | `03_payments.csv` | Tiền khách trả / thanh toán |
| 4 | `04_statements.csv` | Kỳ sao kê / số dư |

Với từng file: kiểm tra ghép cột → Xem trước → đọc lỗi/cảnh báo → Xác nhận lưu. Sau đó mở Sổ dữ liệu, tìm `I_EXACT` hoặc `B_EXACT` để chỉ ra bản ghi, nguồn và các liên kết.

Demo thêm ba ca chặn lỗi từ thư mục `negative/`, chỉ xem trước và **không xác nhận ghi**:

| File | Điều cần cho người xem thấy |
| --- | --- |
| `N04_fractional_vnd__invoices.csv` | Số tiền VND có phần lẻ bị từ chối |
| `N06_orphan_payment__payments.csv` | Thanh toán không có hóa đơn hợp lệ bị chặn |
| `N14_bad_net_vat__invoices.csv` | Tiền trước thuế + VAT không khớp tổng bị báo lỗi |

**Câu trình bày:** “Ở T0, tôi kiểm tra file và quan hệ dữ liệu trước khi ghi. Người dùng biết dòng nào sai và dữ liệu hợp lệ vẫn có nguồn, phiên bản và thời điểm được biết để truy lại.”

Muốn minh họa nâng cao, dùng kho riêng với `-Suite lifecycle` để thử thay thế/điều chỉnh/hủy, hoặc `-Suite large` để cho thấy sau phân bổ vẫn giữ đúng dư nợ 1 VND. Các bước và đáp án nằm trong [hướng dẫn bộ UAT](../pilot/t0_t9_uat_20261110/README.md).

## 6. Kịch bản demo T9

Vẫn tại cổng **8021**, mở Dữ liệu → Đối soát khoản thu · T9, bấm **Tìm đề xuất đối soát**. Thực hiện các ca dưới đây theo thứ tự. Sau mỗi lần duyệt, chạy tìm đề xuất lại trước khi duyệt giao dịch tiếp theo.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Xem rồi duyệt `B_EXACT`, nhập tên người xử lý | Phân bổ **10.000.000 VND** vào `I_EXACT`; hóa đơn hết dư nợ |
| 2 | Duyệt `B_PART` bằng đề xuất mới | Ghi **8.000.000 VND**; `I_PART` còn **12.000.000 VND** |
| 3 | Duyệt `B_GROUP` | Tách **3.000.000** vào `I_GROUP1` và **7.000.000** vào `I_GROUP2` |
| 4 | Mở `B_AMB` và danh sách ứng viên | Có hai hóa đơn cùng phù hợp; hệ thống yêu cầu kiểm tra thay vì tự chọn |
| 5 | Phân bổ thủ công `B_AMB` vào `I_AMB2`, nhập tên và bằng chứng mô phỏng | `I_AMB2` hết dư nợ; `I_AMB1` vẫn còn **6.000.000 VND** |
| 6 | Từ chối `B_UNKNOWN`, ghi lý do chưa xác minh được người chuyển | Lưu người xử lý/lý do; không giảm công nợ |
| 7 | Mở lịch sử, đảo quyết định của `B_EXACT` kèm lý do | `I_EXACT` mở lại **10.000.000 VND**; giao dịch ngân hàng và lịch sử quyết định vẫn còn |

Ở bước phân bổ thủ công, thử để trống bằng chứng trước để cho thấy kiểm tra bắt buộc. Có thể mở lại đề xuất cũ hoặc thử vượt tiền sao kê để minh họa cơ chế chặn, rồi quay về dữ liệu hợp lệ.

**Câu trình bày:** “T9 đề xuất cách ghép tiền với hóa đơn. Chỉ sau khi được duyệt thì công nợ mới đổi. Khi ghép sai, tôi đảo quyết định có lý do; tiền ngân hàng và lịch sử không bị xóa.”

Ca nâng cao: xem quy trình sửa đồng thời `B_EXACT` và số dư kỳ sao kê trong hướng dẫn UAT. Bản xem trước phải nêu các quyết định bị ảnh hưởng; không sửa riêng số tiền bank mà bỏ qua cân đối sao kê.

## 7. Kịch bản demo T10

### Nạp dữ liệu và chuẩn bị kế hoạch

Tại cổng **8022**, nạp sáu file trong `agent1/pilot/demo_dai_phat/`, theo thứ tự:

`01_invoices.csv` → `02_bank.csv` → `03_payments.csv` → `04_statements.csv` → `05_outflows.csv` → `06_actions.csv`.

Chọn đúng bảng tương ứng, ngày **ISO**, tiền **plain** và xác nhận từng lần nạp. Nếu trình bày mô hình đã học, vào Phiên bản & kiểm định, chạy với ngày chốt `31-10-26`, đọc kết quả và chủ động chọn phiên bản. Không coi dữ liệu mô phỏng hoặc việc train xong là bằng chứng mô hình đã đạt trên doanh nghiệp thật.

Trong Dự báo, xác nhận phạm vi thanh toán đến ngày chốt và nhập:

| Trường | Giá trị demo |
| --- | --- |
| Ngày chốt | `31-10-26` — tương ứng `2026-10-31` |
| Số dư đầu kỳ | `425000000` VND |
| Ngưỡng cảnh báo | `200000000` VND |
| Kỳ dự báo | **13 tuần** |
| Kịch bản đầu tiên | **Kế hoạch gốc** |

### Sáu thao tác trình bày

1. **Tạo dự báo mới.** Chỉ ra ngày chốt, kỳ kế hoạch, phạm vi chi và phiên bản được dùng. Tạo mới để nhận đầy đủ các trường giải thích hiện tại.
2. **Mở Giải thích của một hóa đơn trong Khoản cần chú ý.** Chỉ ra xác suất tất toán 4 tuần, giá trị đầu vào, yếu tố đủ điều kiện và chiều ảnh hưởng. Nếu hiện “Chưa đủ cơ sở…”, giải thích đây là cơ chế từ chối nêu lý do khi thiếu bằng chứng; không cố tìm một câu kết luận thuận lợi.
3. **Mở Vì sao ưu tiên?** Cho thấy công thức và điểm xếp hạng. Nếu chính sách chỉ theo dư nợ, giải thích đúng chính sách đó; không nói rằng SHAP hay xác suất quyết định thứ tự khi chúng không tham gia công thức.
4. **Mở Tiền dự thu và nguy cơ thiếu tiền.** Xem theo tuần, hóa đơn và khách hàng; tìm một mã; đối chiếu số dư đầu + thu − chi = số dư cuối. Chỉ ra phần chi đã biết và phần ngoài phạm vi ước lượng.
5. **Xem so sánh Thu sớm 2 tuần / Thu chậm 2 tuần.** So mức thấp nhất và số dư cuối kỳ; kiểm tra phần thu bị đẩy ra ngoài kỳ. Sau đó có thể tạo riêng kế hoạch **26 tuần**, kịch bản thu chậm **28 ngày**, rồi so với kế hoạch gốc 26 tuần cùng đầu vào. Hai thao tác này là hai loại so sánh khác nhau.
6. **Xuất Excel.** Mở bảng kế hoạch, khoản cần chú ý và các sheet phân rã/so sánh. Đối chiếu một hóa đơn hoặc một tuần giữa web và Excel để cho thấy cùng một kế hoạch đã lưu.

Không dùng các số dư hoặc xác suất trong ảnh/báo cáo cũ làm đáp án cố định. Giá trị phụ thuộc dữ liệu, phiên bản và kịch bản đang chọn; kiểm tra sự nhất quán của kế hoạch hiện tại.

**Câu trình bày:** “T10 cho người dùng biết dự báo dựa trên đầu vào nào, vì sao một khoản được ưu tiên và thu chi nào tạo nên số dư. Khi thay giả định, người dùng xem được chênh lệch; kết quả vẫn là ước lượng theo mô hình, không phải cam kết tiền sẽ về.”

## 8. Kiểm chứng đã thực hiện khi soạn báo cáo

Ngày **11/11/2026**, chạy lại các nhóm kiểm thử T0, T9, Workspace và giải thích T10 trên kho tạm: **275 kiểm thử Python đạt, không có bài thất bại hoặc bị bỏ qua**. Hai file kiểm thử giao diện giải thích đạt **24/24 kiểm thử JavaScript**.

Phạm vi gồm nhập XML/ERP/sao kê, tiền và ngày, vòng đời hóa đơn, lịch sử snapshot, duyệt/từ chối/đảo, sửa nguồn, giao dịch nguyên tử, UAT, tra cứu, SHAP, ưu tiên, phân rã và Excel. Có 4 cảnh báo Python: một cảnh báo phụ thuộc và ba cảnh báo chưa hội tụ ở kiểm thử neural cố ý giới hạn 2 vòng lặp. Không dùng các vòng lặp ngắn đó để kết luận chất lượng huấn luyện.

Lệnh chạy lại từ **gốc repository**:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Resolve-Path 'portal').Path
$checks = @(
  'agent1/tests/test_t0_money_bank.py',
  'agent1/tests/test_t0_ingest_pipeline.py',
  'agent1/tests/test_ingest_dates.py',
  'agent1/tests/test_ingest_service.py',
  'agent1/tests/test_t0_t9_t1_repairs.py',
  'agent1/tests/test_observed_reconciliation.py',
  'agent1/tests/test_t10.py',
  'agent1/tests/test_service_scenarios.py',
  'agent1/tests/adaptive/test_company_workspace.py',
  'agent1/tests/adaptive/test_workspace_catalog.py',
  'agent1/tests/adaptive/test_t0_t9_uat_pack.py',
  'agent1/tests/adaptive/test_t1_explanations.py',
  'agent1/tests/adaptive/test_business_explanations.py',
  'agent1/tests/adaptive/test_explanation_reference.py',
  'agent1/tests/adaptive/test_collection_explanations.py',
  'agent1/tests/adaptive/test_cash_explanations.py'
)
.\.venv\Scripts\python.exe -X utf8 -m pytest @checks -q -p no:cacheprovider
node --test agent1/tests/adaptive/t1_explanations_ui.test.cjs agent1/tests/adaptive/t6_cash_ui.test.cjs
```

Lệnh UAT đã được kiểm tra ở chế độ `-DryRun`; phần hướng dẫn demo là kịch bản để chạy tay, chưa phải biên bản một lần demo trực tiếp mới. Báo cáo UI của lần kiểm tra đã lưu ngày 11/11 có ở [báo cáo kiểm tra UI](../outputs/ui_checks/20261111_review/README.md); thư mục này là bằng chứng cục bộ và bị Git bỏ qua.

## 9. Mã nguồn và tài liệu đối chiếu

| Phần | Nơi đọc chính |
| --- | --- |
| T0: đọc chứng từ, kiểm tiền và ngày | [ingest](../agent1_service/ingest/), [hợp đồng dữ liệu Workspace](../agent1/adaptive/data.py) |
| T0: nạp/ghi, tra cứu và lịch sử | [API Workspace](../agent1_service/workspace/api.py), [catalog](../agent1_service/workspace/catalog.py) |
| T9: adapter và sổ quyết định | [adapter Workspace](../agent1_service/workspace/reconciliation.py), [pipeline quan sát](../agent1/reconciliation/pipeline.py), [ledger](../agent1/reconciliation/ledger.py) |
| T10: xác suất và lý do nghiệp vụ | [giải thích T1](../agent1/adaptive/explanations.py), [bằng chứng nghiệp vụ](../agent1/adaptive/business_explanations.py), [mẫu nền](../agent1/adaptive/explanation_reference.py) |
| T10: ưu tiên, dòng tiền và Excel | [giải thích ưu tiên](../agent1/adaptive/collection_explanations.py), [phân rã dòng tiền](../agent1/adaptive/cash_explanations.py), [xuất Excel](../agent1_service/workspace/forecast_export.py) |
| Bộ demo | [UAT T0/T9](../pilot/t0_t9_uat_20261110/README.md), [Đại Phát](../pilot/demo_dai_phat/README.md) |
| Hướng dẫn dịch vụ | [README Agent 1](../README.md), [README dịch vụ](../agent1_service/README.md) |

Trạng thái nghiệm thu và các số đo chất lượng nghiên cứu cần đọc theo đúng phiên bản, dữ liệu và [cổng đánh giá hiện hành](03_Evaluation/GATES_CURRENT.md). Báo cáo triển khai và demo này không thay đổi các kết luận nghiệm thu đó.
