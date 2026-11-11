# Agent1 · Trợ lý dòng tiền cho doanh nghiệp

Workspace local để nạp sổ kế toán, chọn mô hình theo lịch sử doanh nghiệp và lập kế hoạch thu chi. Kỳ dự báo tùy chọn **1–52 tuần**, mặc định **13 tuần**. Có kịch bản thu chậm, biến động chi, rủi ro theo khách và xuất Excel kèm phân rã dòng tiền.

Trong **Dự báo → Khoản cần chú ý**, bấm **Giải thích** để xem xác suất tất toán **4 tuần**, tối đa ba yếu tố đủ điều kiện, giá trị thực và chiều ảnh hưởng. Chỉ thêm một câu nghiệp vụ khi có bằng chứng từ dữ liệu thực đã dùng trong dự báo. Không hiển thị đối chiếu giả định, kể cả trong kế hoạch cũ; không tạo thêm đối chiếu cho kế hoạch mới. Giao diện không có mục kỹ thuật, mức nền hoặc tên mô hình.

Kỳ hạn và số hóa đơn đã tất toán được giữ trong **Thông tin đầu vào**, chưa dùng làm lý do xác suất cao/thấp. Kỳ hạn cần kiểm định riêng phản ứng của mô hình; số hóa đơn chỉ phản ánh lượng lịch sử. Giá trị hóa đơn chỉ được đưa vào yếu tố chính khi ảnh hưởng đủ lớn và ổn định, không suy ra khả năng chi trả của khách. Nếu không có yếu tố đạt, UI báo **Chưa đủ cơ sở để đưa ra lý do nghiệp vụ đáng tin cho dự báo này**. Nếu yếu tố lớn nhất chưa thể diễn giải, UI nói rõ phần giải thích còn thiếu.

Chính sách hiển thị ban đầu yêu cầu chiều ảnh hưởng nhất quán qua các mẫu nền và độ lớn tối thiểu **1 điểm phần trăm** trên cả khoảng kiểm tra. Đây là ngưỡng lọc sản phẩm, không phải chứng nhận mô hình hay độ tin cậy thống kê. Câu lịch sử thanh toán cần ít nhất 10 hóa đơn, loại khoản tất toán/ghi nhận sau ngày lập hóa đơn đích, khớp đầu vào và cùng bằng chứng giữa các thành viên đang phục vụ. Câu chỉ nêu số hóa đơn trả sau hạn thực tế; chiều ảnh hưởng lấy từ kết quả mô hình, không tự suy từ lịch sử. Kế hoạch cũ thiếu đánh giá nghiệp vụ cần tạo lại để có yếu tố chính. SHAP đầy đủ và bằng chứng vẫn lưu cùng kế hoạch để kiểm tra nội bộ.

SHAP liệt kê đủ 64 tổ hợp của sáu nhóm đầu vào T1. Nền dùng chung cho các hóa đơn trong cùng lần dự báo: toàn bộ công nợ mở khi có tối đa 512 hóa đơn; tập lớn hơn lấy 128 hóa đơn phân tầng theo tuổi, kỳ hạn, giá trị và lịch sử khách, có trọng số giữ tỷ trọng từng tầng. Ba mẫu bổ sung kiểm tra độ nhạy của chiều ảnh hưởng, mức đóng góp và yếu tố đứng đầu. Mã hóa đơn, đầu vào đã chuẩn bị, trọng số và các mẫu kiểm tra được lưu một lần trong `explanation_references` của kế hoạch. Kiểm tra quan hệ lịch sử và các cặp đầu vào tương quan có thể cảnh báo tổ hợp ít được dữ liệu hỗ trợ. Các kiểm tra này không chứng minh hết thiên lệch hoặc quan hệ nhân quả; mức tham chiếu không phải tỷ lệ trả thực tế, độ ổn định không phải độ tin cậy của xác suất. Kỳ giải thích 4 tuần độc lập với kỳ kế hoạch dòng tiền.

Mục **Khoản cần chú ý** còn hiển thị chính sách, thứ tự và điểm ưu tiên. Bấm **Vì sao ưu tiên?** để xem công thức, so sánh với khoản kế tiếp, cách xử lý bằng điểm, dư nợ, nguy cơ chưa tất toán, tranh chấp và lời hứa. Điểm có thể dùng dư nợ, nguy cơ hoặc tích hai yếu tố. Nguy cơ dùng ước lượng lịch sử khách tính riêng tại ngày chốt, không áp dụng kịch bản thu chậm; giao diện nêu rõ khi nguồn này khác dự báo T1 và có SHAP riêng khi xác suất tham gia điểm.

Tranh chấp/lời hứa/ngày quá hạn không được cộng điểm riêng. Khoản đã xóa nợ và khoản vừa liên hệ/tạm bỏ qua chưa đủ 7 ngày bị loại theo quy tắc hiện hành; cùng điểm giữ thứ tự snapshot. Giải thích xếp hạng cũng được lưu cùng kế hoạch và xuất các trường chính sang Excel. Điểm phân luồng chưa chứng minh tiền thu thêm do liên hệ khách.

Xếp hạng giữ đúng chênh lệch 1 VND với số tiền lớn; điểm dựa trên dư nợ × nguy cơ được tính bằng số thập phân trước khi so sánh. UI và Excel giữ chữ số của các khoản lớn. Hàng đợi trống vẫn báo còn công nợ nếu các khoản chỉ đang tạm hoãn liên hệ. Kế hoạch cũ giữ nguyên bản đã lưu; tạo dự báo mới để nhận kết quả sửa.

Trong **Dự báo → Tiền dự thu và nguy cơ thiếu tiền**, xem đóng góp theo hóa đơn/khách hàng cho toàn kỳ hoặc từng tuần, tìm mã và xem lịch chi. Phân rã gồm toàn bộ công nợ mở sau loại xóa nợ, kể cả các khoản đang tạm hoãn liên hệ. Bán thu ngay, thu bán chịu mới và chi biến đổi bổ sung được ghi riêng nếu bật ước lượng hoạt động. Bảng đối chiếu giữ đúng đẳng thức **số dư đầu + dự thu − dự chi = số dư cuối**; cảnh báo nêu tuần cần chú ý, dư nợ còn phụ thuộc khách và các khoản chi lớn.

So sánh tự động **thu sớm/chậm 2 tuần** tính từ kế hoạch đang xem, giữ nguyên chi và các dòng hoạt động. Chỉ dịch phần dự thu công nợ đã có trong kỳ; thu sớm nhất ở tuần 1, không kéo phần dư nợ ngoài kỳ chưa xác định thời điểm vào kỳ. Thu chậm ra ngoài kỳ được ghi riêng. Đây là độ nhạy số dư kỳ vọng, chưa tính lại xác suất thiếu tiền/P10/P90. SHAP cho các mục tiêu đó là phần mở rộng sau. Phân rã, kịch bản và phiên bản dữ liệu được lưu cùng kế hoạch; Excel có thêm sáu sheet chi tiết. Kế hoạch cũ vẫn mở được và cần tạo lại để có phân rã.

## Bắt đầu

Yêu cầu Git, Python 3.12 và PowerShell. Nếu đã clone nhánh `agent1-Khanh`, bắt đầu từ lệnh tạo `.venv`.

```powershell
git clone --branch agent1-Khanh --single-branch https://github.com/Khanhhh239/Multi-Agent-Finance.git
cd Multi-Agent-Finance
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-service.txt
.\scripts\start-business.ps1 -Port 8011 -Company SME
```

Mở **http://127.0.0.1:8011/workspace**. Khóa kết nối nằm trong `.state-business-keys/api-token.txt`. Với doanh nghiệp có mã khác, script in đúng đường dẫn thư mục khóa trên màn hình khởi động.

Khi mở Agent 1 trong Portal, Workspace tự nhận khóa kết nối từ trang cha qua `postMessage`, không cần dán khóa. Mục **Nạp dữ liệu** có ở cả khung Portal và tab riêng, cho chọn tệp CSV/Excel/XML, ghép cột, kiểm tra rồi xác nhận lưu trực tiếp vào Agent 1. Trang **Sổ dữ liệu** có nút **Nạp dữ liệu** để chuyển sang biểu mẫu này. Nạp tệp dùng chung cho nhiều agent vẫn thực hiện tại Portal. Tab riêng tự kết nối bằng mã dùng một lần, hết hạn sau 60 giây, rồi tạo phiên cookie HttpOnly có hiệu lực 8 giờ. F5 tự khôi phục phiên. **Ngắt kết nối**, hết hạn hoặc khởi động lại dịch vụ sẽ kết thúc phiên; mở lại từ Portal hoặc nhập khóa để kết nối lại. Khóa API không được lưu trong localStorage/sessionStorage.

Dữ liệu đã xác nhận được lưu thành các snapshot trong `agent1.db` ở thư mục trạng thái của doanh nghiệp; nội dung bản ghi trong SQLite được mã hóa. `api-token.txt` và `encryption.key` ở thư mục khóa riêng bên cạnh. Với Portal, mã `TEN_DN` dùng kho `agent1/.state-business-firm-TEN_DN-data/` và thư mục khóa `agent1/.state-business-firm-TEN_DN-data-keys/`. F5 không xóa dữ liệu. Trong khung Portal, khóa được gửi lại khi trang tải, kể cả khi trình duyệt chặn cookie giữa `localhost` và `127.0.0.1`. Mật khẩu mở khóa **Nạp dữ liệu** của Portal là cơ chế khác với khóa truy cập Agent 1.

Trang **Sổ dữ liệu** cho tìm theo mã, khách hàng, nội dung, lọc ngày/trạng thái và phân trang. Bấm mã để xem bản ghi, phiên bản cũ và liên kết hóa đơn → thanh toán → sao kê → quyết định T9, kể cả quyết định đã đảo. **Lịch sử từng lần nạp** ghi tên tệp, người nạp (nếu được cung cấp), thời gian, số dòng mới/sửa/trùng/lỗi và công nợ trước–sau. Lần kiểm tra còn lỗi hoặc chưa xác nhận hiển thị riêng, chưa tác động dữ liệu. Các lần kiểm tra từ phiên bản cũ thiếu tên tệp vẫn được hiển thị với thời gian và số dòng hợp lệ đã lưu; giao diện ghi rõ chưa đủ thông tin xác định đã xác nhận nạp hay chưa. Dấu `—` chỉ thông tin chưa được ghi lại. Đọc lịch sử không tạo hoặc sửa nhật ký cũ. Ghi dataset và nhật ký cùng giao dịch; gửi lại cùng xác nhận không ghi thêm lần nạp. Nhật ký tên tệp bắt đầu từ khi bật tính năng này, không suy đoán các lần nạp cũ. Tệp gốc nạp trực tiếp vẫn nằm ở nơi bạn chọn trên máy; Workspace lưu bản ghi đã kiểm tra.

`payment_id` là định danh khoản thanh toán: cùng mã/nội dung không cộng thêm, khác mã là hai khoản riêng. Phân bổ vẫn bị chặn nếu vượt giá trị hóa đơn hoặc tiền sao kê. `outflows` trong Workspace biểu diễn các lần đến hạn của **lịch cố định T5** (lương, thuê, trả nợ định kỳ…), là dữ liệu tùy chọn; không yêu cầu bảng chi dự kiến tổng quát. Chi hoạt động khác chỉ được ước lượng từ sao kê khi bật tùy chọn và có mô hình đủ lịch sử. Số dư dự báo phải được đọc cùng phạm vi chi này.

**T5 cập nhật 11/11/2026:** nạp khoản thực trả/nhận ở bảng **Thanh toán nghĩa vụ T5** (`expense_payments`), liên kết `expense_id` và dòng sao kê. Dự báo chỉ tính phần còn lại; khoản chi đến/quá hạn chưa trả được chuyển sang ngày làm việc kế tiếp hoặc ngày dự kiến mới do doanh nghiệp nhập. Không tự coi lịch cũ là đã trả. Tuần có một vài khoản chi vẫn báo chưa xác nhận đủ nếu chưa được rà soát. Nghĩa vụ theo hồ sơ (TNCN, thuế nhà thầu, thưởng, thuê, gốc/lãi vay, quyết toán TNDN còn phải nộp) và hoàn VAT đã duyệt dùng cùng luồng nạp T5; hoàn VAT được tách thành dòng thu. Xem [hợp đồng T5](agent1_service/README.md#t5-ledger).

“Đã nạp đủ thanh toán đến ngày chốt” là xác nhận của người dùng. Ví dụ, dự báo 31/10 nhưng mới nạp thanh toán đến 25/10 thì không được mặc nhiên coi các hóa đơn còn thiếu payment là chưa trả. Ngày giao dịch lớn nhất không chứng minh dữ liệu đầy đủ. Kỳ sao kê chỉ được ghi khi số dư đầu kỳ cộng thu trừ chi khớp số dư cuối kỳ; tài khoản/kỳ chưa nạp không có bằng chứng kiểm tra đầy đủ.

## Thử toàn bộ luồng bằng Đại Phát

```powershell
.\scripts\start-business.ps1 -Port 8012 -Company DEMO_DAIPHAT -DemoTraining
```

Mở **http://127.0.0.1:8012/workspace#data** và kết nối bằng khóa trong `.state-business-firm-DEMO_DAIPHAT-data-keys/api-token.txt`. Nạp sáu CSV từ [pilot/demo_dai_phat](pilot/demo_dai_phat) theo thứ tự số. Chọn ngày trong file `yyyy-mm-dd` và số tiền `plain`. Giao diện và Excel hiển thị `dd-mm-yy`.

| Thao tác | Giá trị diễn tập |
|---|---|
| Ngày chốt kiểm định và dự báo | `31-10-26` |
| Số dư đầu kỳ | `425000000` VND |
| Ngưỡng cảnh báo | `200000000` VND |
| Chạy gốc | 13 tuần, Kế hoạch gốc |
| So sánh | Chạy gốc 26 tuần rồi chọn Thu chậm thêm 28 ngày |

Hướng dẫn có **12 bước và 13 ảnh web**, gồm nhập file, xem điểm, chọn phiên bản, thử kịch bản và xuất Excel. [Đọc PDF mới nhất](docs/06_Pilot/pdf/So-tay-Agent1.pdf) · [Bản Markdown](docs/06_Pilot/SO_TAY_AGENT1.md).

Dữ liệu Đại Phát là synthetic. Bản huấn luyện minh họa có Brier 4 tuần 0,0949 so với mốc 0,1341 trên 82 hóa đơn audit. Khoảng tin cậy cải thiện chứa 0. Xem [bằng chứng và giới hạn](docs/HANDOFF.md).

## Đối soát khoản thu T9

Trong **Dữ liệu → Đối soát khoản thu · T9**, bấm **Tìm đề xuất đối soát**. Nhập tên người xử lý, đối chiếu chứng từ rồi duyệt từng giao dịch, hoặc từ chối kèm lý do. Ca mơ hồ có danh sách ứng viên với điểm gợi ý và form phân bổ thủ công kèm nguồn bằng chứng. Mở **Sổ phân bổ đã xác nhận và lịch sử xử lý** để xem hoặc đảo quyết định với lý do. Phân bổ được duyệt cập nhật ngay công nợ và dataset dự báo; đề xuất và từ chối không làm giảm công nợ. Sau khi dữ liệu đổi, cần tìm đề xuất mới. Điểm gợi ý không phải xác suất đúng.

Mẫu sao kê nhận thêm các cột tùy chọn `memo` (nội dung chuyển khoản), `counterparty` (tên người chuyển), `customer_id` và `cash_flow_class`; hóa đơn nhận `customer_name`. Dữ liệu thiếu bằng chứng vẫn được giữ chờ kiểm tra. CSV thanh toán phải đúng khách hàng và đúng loại khoản thu. Mã đã xóa chỉ được nhập lại với ngày ghi nhận mới hơn lịch sử xóa.

Để sửa dữ liệu nhập sai, mở **Dữ liệu → Sửa dữ liệu nguồn / bản ghi nhập nhầm**, chọn bảng và mã rồi tải bản ghi. Nhập giá trị đúng, người xử lý và bằng chứng; bấm **Xem trước ảnh hưởng** rồi **Xác nhận sửa nguồn và đảo phân bổ bị ảnh hưởng**. Có thể thêm nhiều bản ghi vào cùng lần sửa, ví dụ sửa số tiền sao kê cùng số dư cuối kỳ. Hệ thống giữ nguyên mã, tự ghi ngày giờ bản sửa, đảo các quyết định liên quan và giữ bản cũ trong lịch sử; hỗ trợ cả sửa trong cùng ngày. Sau khi lưu, tìm đề xuất và duyệt lại. Các kế hoạch đã lưu vẫn giữ kết quả và phiên bản dữ liệu ban đầu.

Việc sửa số tiền, khách hoặc ngày của hóa đơn có thể làm ngừng sử dụng các thanh toán, lời hứa và quyết định xóa nợ cũ liên quan; màn hình xem trước liệt kê phạm vi này. Khoản phân bổ do T9 tạo được sửa bằng cách đảo rồi ghép lại, hoặc sửa chứng từ hóa đơn/sao kê nguồn; không sửa trực tiếp dòng thanh toán do T9 tạo. Bản sửa vẫn phải qua kiểm tra T0, cân đối sao kê và danh mục tài khoản được duyệt. Số tiền ngân hàng lấy theo phiên bản hiện hành, không cộng cả bản sai và bản sửa.

Adapter Workspace dùng lại constrained flow, scorer và ledger T9; ghi quyết định và dataset trong cùng giao dịch, lưu lịch sử duyệt/từ chối/đảo. Xem [tài liệu dịch vụ](agent1_service/README.md) và [bộ dữ liệu, kịch bản UAT T0/T9](pilot/t0_t9_uat_20261110/README.md) để kiểm tra luồng này.

## Người nhận bàn giao

| Nơi đọc | Nội dung |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | Kiến trúc, luồng dữ liệu, cấu hình, kiểm tra và phần còn thiếu |
| [agent1_service/README.md](agent1_service/README.md) | API, phân quyền, phục hồi và dịch vụ nghiên cứu |
| [docs/06_Pilot/pdf/So-tay-Agent1.pdf](docs/06_Pilot/pdf/So-tay-Agent1.pdf) | Thực hành cho kế toán và người vận hành |
| [pilot/demo_dai_phat](pilot/demo_dai_phat) | Sáu CSV mô phỏng, manifest và file lỗi để thử nhập liệu |
| [docs/06_Pilot/RA_SOAT_WORKSPACE_DONG_TIEN.md](docs/06_Pilot/RA_SOAT_WORKSPACE_DONG_TIEN.md) | Đối chiếu yêu cầu sản phẩm và các tính năng còn thiếu |

## Kiểm tra

```powershell
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
.\.venv\Scripts\python.exe -m pytest tests/adaptive -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

Kiểm tra UI với Portal đang chạy tại `http://localhost:8800` và bộ UAT T0/T9 đã nạp: từ thư mục gốc repo, chạy `.\.venv\Scripts\python.exe -X utf8 agent1/scripts/pilot/check_portal_workspace_ui.py`. Script cần Playwright (`python -m pip install playwright`) và Chrome đã cài; mở một trình duyệt kiểm thử riêng, không nạp thêm dữ liệu hoặc thay đổi phân bổ. Kết quả JSON và ảnh màn hình nằm trong `agent1/outputs/ui_checks/20261111/`. Các ca gồm kết nối trong khung, tìm/liên kết bản ghi, F5 Portal, F5 tab riêng, màn 390px, thanh đối soát và ngắt phiên.

GRU/LSTM và Chronos dùng phụ thuộc tùy chọn trong `requirements-forecast.txt`. Chỉ cài khi cần kiểm định nhánh chuỗi tiền mở rộng. MLP hóa đơn dùng scikit-learn. `AGENT1_DL_DEVICE` mặc định `cpu`. Chronos cần thư mục trọng số local `AGENT1_CHRONOS_DIR`.

## Cấu trúc

```text
agent1/adaptive/          Học, kiểm định và dự báo riêng theo doanh nghiệp
agent1_service/workspace/ API workspace, worker, xuất Excel, phục hồi
agent1_service/ui/        Giao diện và tài nguyên dùng local
scripts/start-business.ps1 Điểm khởi động trên Windows
scripts/business/        Sinh demo, kiểm tra và dựng tài liệu
pilot/demo_dai_phat/      Dữ liệu diễn tập đã gắn mã DEMO_
docs/06_Pilot/pdf/        PDF bàn giao mới nhất
tests/adaptive/          Kiểm thử luồng SME
agent1/models/           Mô hình và thí nghiệm nghiên cứu
```

Các tài liệu nghiên cứu nằm trong thư mục `docs/01_…` đến `docs/05_…`. Đọc [chỉ mục nghiên cứu](docs/00_INDEX.md) và [cổng nghiệm thu](docs/03_Evaluation/GATES_CURRENT.md) khi làm việc với pipeline nghiên cứu.

## Vận hành và dữ liệu riêng

Tác vụ lớn cần ít nhất **3 GiB RAM hệ thống trống** trước khi bắt đầu. Worker giữ giới hạn RSS mặc định 2 GiB. Huấn luyện không giới hạn tổng thời gian, tiến độ cập nhật mỗi 15 giây. Để máy và dịch vụ hoạt động trong lúc học.

Workspace demo tự tạo mật khẩu báo cáo ngẫu nhiên trong thư mục khóa nếu chưa có. Báo cáo HTML mã hóa được lưu dưới `outputs/private-training-reports/`. Có thể đổi thư mục bằng `AGENT1_REPORT_DIR`. Khóa API, mật khẩu, CSDL và trọng số do máy nhận tạo riêng. `.gitignore` loại các file này khỏi Git.

Luồng nghiên cứu T0/T9/T1 đã tích hợp lõi đối soát từ agent1-Thắng cùng lịch sử quan sát có duyệt. Xem mục “Luồng T0–T9 thống nhất” trong [tài liệu dịch vụ](agent1_service/README.md). Workspace SME dùng các endpoint `/v1/` riêng và cùng kho lưu mã hóa.
