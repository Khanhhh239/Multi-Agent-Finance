# Đăng ký trước v5, bản v1.3 (v1.1 đã duyệt cộng sửa đổi v1.2 và v1.3)

Ngày cập nhật 2026-10-19. **Trạng thái: ĐÃ DUYỆT v1.1 theo bốn sửa đổi của chủ dự án. Được bắt đầu R2.** Không cần duyệt lại khi chỉ áp đúng các sửa đổi này; mọi thay đổi khác phải dừng và hỏi. Bản v1 nguyên văn nằm ở cuối tệp, chỉ là lịch sử, không còn điều khiển thực thi.

| Phiên bản | Dấu vết thay đổi và thẩm quyền |
|---|---|
| v1 | Đề xuất chờ duyệt; băm tệp gốc SHA-256 `711c4acda8451f594deb303d4dabdd2fe1eefbaf5e124ca4856c97b09211db4a` |
| v1.1 | Làm rõ tiếp theo: ba suất cho mô hình có giám sát, cả hai Cold chạy đủ 20 thế giới ở tầng chọn rồi chọn riêng. Chủ dự án duyệt có sửa đổi: hai tầng, J theo nhóm 20% thấp nhất, gộp nhánh nhỏ, chốt chặn trước niêm phong, PU là nền và thứ tự R2. Giữ các điều khoản v1 không bị sửa và giữ nguyên cổng niêm phong. |
| v1.2 | 2026-10-22: số cây cố định, định nghĩa ứng viên, tái sử dụng bộ dữ liệu nguồn, lấy mẫu âm có điều kiện, hạ tầng; ghi trước mọi so sánh (mục Sửa đổi v1.2). |
| v1.3 | 2026-10-22, trước bước sàng lọc ứng viên dùng đặc trưng mới: loại lối tắt liên kết hóa đơn của bộ sinh (mục Sửa đổi v1.3). |
| Làm rõ R2-w | 2026-10-22 16:50, sau khi bước chọn w xong và TRƯỚC khi có bất kỳ kết quả sàng lọc nào: cách khóa w khi không w nào hợp lệ (mục Làm rõ khóa w). Không đổi cổng, trần 15% hay ứng viên. |
| Làm rõ R3 | 2026-10-22, trước khi đọc văn xuôi kịch bản độc lập: tần suất và mức phủ của ca hợp lệ mới trong thế giới niêm phong (mục Làm rõ thực thi R3). Không đổi cổng, quy tắc chọn hoặc ứng viên. |

Mọi số đo dự kiến là trên **dữ liệu tổng hợp**, trừ khi một báo cáo kiểm thử ngoài hoặc thí điểm chỉ rõ nguồn thật và phạm vi nhãn. Kết luận **v4 không đạt G5 và kích hoạt M2** giữ nguyên. Ba seed v4 931 đến 933 đã được dùng để hậu kiểm, không còn là kiểm thử niêm phong và không được tính vào cổng v5.

## Làm rõ khóa w khi không w nào hợp lệ (2026-10-22 16:50, trước mọi kết quả sàng lọc)

**Sự kiện:** bước chọn w (L4-FB-PU, 8 thế giới 1001 đến 1008, seed 0) xong lúc 16:36. J của w = 0,1; 0,2; 0,5 lần lượt là 0,7026; 0,6911; 0,6720. Cả ba w đều **không hợp lệ** theo trần ca hợp lệ khó 15%: vượt trần ở 5 trên 8 thế giới với w = 0,1 (cao nhất 18,6%, ở nhánh `expense`), 5 trên 8 với w = 0,2 và 5 trên 8 với w = 0,5. Bộ điều phối ghi `no_eligible_weight` và dùng w = 0,1 cho sàng lọc.

**Điều đăng ký chưa nêu:** mục 3 chỉ nói chọn w bằng J trên L4-FB; mục 4 nói ứng viên không hợp lệ không được chọn. Không nêu cách khóa w khi không w nào hợp lệ. Việc dùng w = 0,1 là giá trị mặc định trong mã (phần tử đầu của danh sách), chưa được đăng ký.

**Làm rõ (giữ đúng tinh thần mục 3, không đổi cổng):**
- Khi không w nào hợp lệ, w được khóa là w có **J cao nhất**, tức 0,1, hòa thì theo thứ tự danh sách. Lý do: w chỉ là tham số nền chung của mọi ứng viên có giám sát; tính hợp lệ được xét cho **từng ứng viên ở tầng sàng lọc và tầng chọn**, không xét lại ở bước chọn w. Lựa chọn này trùng với w có J cao nhất nên không phụ thuộc vào kết quả sàng lọc chưa có.
- Trần 15% **không đổi** và không được nới ở bất kỳ bước nào.
- Nếu sau sàng lọc không ứng viên có giám sát nào hợp lệ, hoặc sau tầng chọn không còn ứng viên hợp lệ, áp mục 4 và mục 7: dừng, **không sinh và không chấm niêm phong**, viết đề xuất đổi hướng. Không đổi w, trần hay danh sách ứng viên để cứu.
- Chủ dự án có thể bác bỏ làm rõ này. Khi đó kết quả sàng lọc chạy bằng w = 0,1 bị bỏ và chạy lại theo quyết định của chủ dự án.

## Làm rõ thực thi R3 (2026-10-22, trước khi đọc văn xuôi kịch bản độc lập)

Mục 6 yêu cầu ca hợp lệ tương ứng cho mỗi kịch bản nhưng chưa nêu tần suất sinh. Để tần suất không thể bị chỉnh theo bộ phát hiện sau khi đã đọc kịch bản, ghi trước như sau (`agent2/world_v5_sealed.py`, có kiểm thử máy móc bằng kịch bản thay thế):
- Mỗi ca hợp lệ mới xuất hiện ở một công ty và một kỳ (train, validation, test) với xác suất 0,5, mỗi lần 1 đến 2 lượt; thế giới niêm phong v4 đã dùng 0,3 đến 0,5 và 0 đến 2 lượt.
- Mỗi ca hợp lệ mới phải có ít nhất 3 dòng trong kỳ test. Nếu lượt ngẫu nhiên thiếu, bổ sung lượt ở kỳ test cho công ty chọn ngẫu nhiên, tối đa 200 lần thử; vẫn thiếu thì dừng sinh, coi là lỗi toàn vẹn theo mục 6.
- Thế giới thử khô 5199 phải qua kiểm tra hiện diện trường (V13, `scripts/audit_field_presence.py`) trước khi chấm, để bộ mã hóa không tạo lối tắt kiểu L11.
- Các phần này chỉ dùng nếu chốt chặn trước niêm phong đạt. Đây là làm rõ thực thi, không phải sửa cổng; chủ dự án có thể bác bỏ trước R3.

## Sửa đổi v1.3 (2026-10-22, trước khi bất kỳ ứng viên nào dùng đặc trưng thay đổi được chạy)

**Phát hiện:** trong bộ sinh v4 và v5, chỉ các dòng trả hàng hoặc xóa nợ **gian lận** ghi `applied_invoice_id`; dòng hợp lệ không bao giờ ghi. Thế giới 1001: 10/10 dòng có liên kết là gian lận, 985 dòng không liên kết đều hợp lệ. Mọi đặc trưng dựa trên liên kết này là lối tắt của bộ sinh, không phải tín hiệu kiểm toán (sổ thật luôn liên kết chứng từ điều chỉnh với hóa đơn gốc).

**Sửa đổi:**
- Loại `ar_reversal_age_days`, `ar_reversal_unpaid`, `ar_creator_reversal_share` và ba bộ phát hiện tương ứng khỏi `L4-PU-E2-AR`, `L4-PU-E2-AR-2plus1`, `Cold-Rules-E2`.
- Thay `ed2_score` bằng `ed2_clean`, là max các đuôi còn lại (`screen_v5.LINK_SHORTCUT`, `CleanChangeSequence`, có kiểm thử).
- Bộ sinh và các thế giới đã khóa giữ nguyên; lỗi bộ sinh được ghi vào hạn chế dữ liệu và phải sửa ở phiên bản bộ sinh sau.
- Khi sửa đổi này được ghi, mới chỉ có bước chuẩn bị ma trận đang chạy; chưa có kết quả so sánh nào.

## Sửa đổi v1.2 (2026-10-22, ghi TRƯỚC mọi thí nghiệm so sánh)

Thẩm quyền: chủ dự án giao cho phiên hỗ trợ tự thực hiện R2 đến hết ngày 2026-10-22 ("tự làm đến khi xong"). Sửa đổi chỉ về **cách huấn luyện và hạ tầng**, không đổi giao thức, ứng viên, J, trần ca khó, chốt chặn hay cổng niêm phong. Bằng chứng chẩn đoán dẫn tới sửa đổi: `docs/05_ke_hoach_giao_viec/09_ban_giao_nhanh_drivers.md` (hậu kiểm trên dữ liệu tổng hợp, không dùng để chọn).

1. **Số cây cố định.** Mọi mô hình có giám sát huấn luyện đúng 400 cây, tốc độ học 0,05, lá 7 và 15, chọn lá theo AP trên validation nguồn. Bỏ dừng sớm 60 vòng của v1.1: chẩn đoán cho thấy dừng sớm theo AP có lúc dừng ở 1 cây dưới trọng số PU, làm kết quả phụ thuộc may rủi.
2. **Định nghĩa ứng viên.**
   - `L3-PU`: cột L3.
   - `L4-FB-PU`: cột L4, cân bằng họ.
   - `L4-PU-E2-AR`: cột L4 cộng `change_feature_names()` (23 đặc trưng thay đổi theo thực thể và công nợ, 21 đuôi EntityDeviation2, `ed2_score`).
   - `L4-PU-E2-AR-2plus1`: 2 khe từ `L4-PU-E2-AR`, 1 khe từ `Cold-Rules-E2`.
   - `Cold-Rules-E2` = max hạng (luật, `ed2_score`).
   - `Cold-v4` = max hạng (luật, EntityDeviation v4).

   Hạng Cold so với validation của chính thế giới đích, không nhãn.
3. **PU.** w chọn trong {0,1; 0,2; 0,5} trên `L4-FB-PU`, tầng sàng lọc, seed 0, theo J; hòa chính xác thì chọn w đứng trước. Khóa ở `results/v5/R2/PU_locked.json`. Kết quả `L4-FB-PU` với w đã khóa được dùng lại ở bước sàng lọc ứng viên (cùng ước lượng, không huấn luyện lại).
4. **Tái sử dụng bộ dữ liệu nguồn** cho một đích và một bộ cột; 11 giao thức, w và seed chỉ đổi nhãn và trọng số. Kiểm thử chứng minh kết quả giống hệt dựng mới (`tests_agent2/test_screen_v5.py`).
5. **Lấy mẫu âm có điều kiện.**
   - Chỉ dùng nếu `scripts/check_subsample_equivalence.py` trên đích 1001, `L4-PU`, w = 0,2 cho Spearman ≥ 0,95 **và** chênh recall@B3 ≤ 2 điểm phần trăm.
   - Khi dùng: giữ mọi dòng gian lận thật của nguồn (dòng nhánh bị ẩn vẫn là U với trọng số w), mọi ca hợp lệ khó, và tỷ lệ f các dòng còn lại với trọng số 1/f.
   - f là giá trị nhỏ nhất trong {0,1; 0,2} đạt kiểm tra; không đạt cả hai thì không lấy mẫu.
   - Validation nguồn và tập đích không bao giờ lấy mẫu.
6. **Hạ tầng.** Mỗi đợt chạy một tiến trình, trần bộ nhớ 10 GiB (máy đã tăng bộ nhớ ảo lên 35,7 GB), 8 luồng LightGBM, lưu JSON và cờ sau từng giao thức.
7. **Bộ sinh.** Sửa `hire_guard` (seed 1017) đã chứng minh giữ nguyên từng byte ở 1001 và 1016 (`results/v5/development/hire_guard_parity.json`).

## 1. Câu hỏi và giao thức chính

Mục tiêu chính là S2: học từ các thế giới tổng hợp khác rồi áp vào **công ty đích không có nhãn điều tra**. S2 được đánh giá riêng với chế độ khởi đầu lạnh không nhãn; S1 chỉ báo cáo phụ và không tham gia điểm chọn hoặc cổng đi tiếp.

| Giao thức | Nguồn học có giám sát | Công ty đích | Vai trò |
|---|---|---|---|
| S2 đầy đủ | Các thế giới nguồn, chỉ train và validation trước kỳ test | Chỉ lịch sử thô trước kỳ chấm, không đọc nhãn đích | Giao thức chính |
| P2 kết hợp S2 | Như S2, nhưng lần lượt ẩn một nhánh ACFE khỏi nhãn nguồn | Giữ toàn bộ giao dịch đích cạnh tranh cùng ngân sách; đo riêng gian lận của nhánh ẩn | Chọn khả năng chuyển giao |
| Khởi đầu lạnh không nhãn | Không dùng nhãn gian lận nguồn hoặc đích để khớp bộ chấm | Có lịch sử trước kỳ chấm để ước lượng nền và phân vị | Cấu hình riêng, cổng riêng |
| S1 phụ | Chỉ các dương tính đã xác nhận trong lịch sử cùng công ty và các dòng chưa biết | Nhãn chưa phát hiện là chưa biết, không phải âm tính đã xác nhận | Chẩn đoán phụ |

Lịch thời gian ban đầu giữ như v4: train năm 2024, validation nửa đầu 2025, test nửa cuối 2025. Nguồn chỉ dùng train và validation. Đích chỉ dùng thông tin quan sát trước giao dịch; tham chiếu hiệu chỉnh lấy trước kỳ chấm. Cấm đọc nhãn đích để chọn cây, ngưỡng, hệ số PU, cửa sổ, trọng số hoặc cấu hình. Đầu ra không nhãn được khớp trên lịch sử đích trước kỳ test; không khớp trên cả kỳ test.

Trong P2 kết hợp S2, các dòng thuộc nhánh bị ẩn vẫn ở lịch sử nhưng có trạng thái **U, chưa biết**. Dương tính quan sát có trạng thái **P, đã xác nhận**. S1 cũng dùng P và U; không được tuyên bố nhãn 0 của dữ liệu tổng hợp là âm tính đã kiểm tra. Nếu dùng giảm trọng số U trong hàm mất mát, phải ghi đó là phép xấp xỉ PU, có thể vẫn có thiên lệch; không đổi cách diễn giải nhãn thành âm tính thật. Chỉ dữ liệu được xác nhận hợp lệ bằng một nguồn riêng mới được gọi là âm tính đã xác nhận.

Đối chiếu R0 loại dòng nhờ biết nhãn thật không được trở thành cách lọc lịch sử trong S1 hoặc S2 v5. Không dùng họ kịch bản bị ẩn để sửa từng dòng đầu vào vận hành.

Khởi đầu lạnh ở đây nghĩa là **không có nhãn**, không phải hoàn toàn không có lịch sử. Tối thiểu 20 quan sát quá khứ cho nền thực thể; thiếu nền phải báo thiếu năng lực. Ngày đầu không có lịch sử chỉ chạy các luật có đủ bằng chứng, báo riêng là chế độ giảm, không gán các cổng khởi đầu lạnh dưới đây cho chế độ đó.

## 2. Thế giới phát triển và cách chia

1. Dùng đầy đủ **20 thế giới mới**, seed 1001 đến 1020. Tầng sàng lọc dùng đúng tám đích 1001 đến 1008 đã định trước; tầng chọn dùng đủ 20 đích. Không chọn tập con sau khi thấy kết quả. Nếu một thế giới lỗi kiểm định, sửa lỗi hạ tầng hoặc bộ sinh, ghi nhật ký và sinh lại đồng nhất trước khi so sánh; không loại vì mô hình làm kém.
2. Mỗi thế giới yêu cầu 200.000 giao dịch. Số công ty là số nguyên đều trong 30 đến 60; hệ số tiền lấy trên thang log từ 1 đến 20. Lịch lương thay đổi giữa các lịch hợp lệ theo cơ chế chung. Tỷ trọng L0, L1, L2 lấy từ Dirichlet(1,1,1) cho mỗi thế giới và ghi manifest, không chọn tỷ trọng theo điểm mô hình. Tỷ lệ gian lận mặc định 0,004, công khai là giả định tổng hợp; không diễn giải thành tần suất thật.
3. Mỗi thế giới làm đích một lần, học có giám sát từ **19 thế giới còn lại**. Mã công ty, thực thể và giao dịch có tiền tố thế giới; cấm trùng khóa giữa nguồn và đích. Mỗi vòng P2 kết hợp S2 ẩn lần lượt đủ 10 nhánh ACFE ở tất cả thế giới nguồn, trong cả train và validation; không bỏ nhánh khó.
4. Tất cả ứng viên dùng cùng bảng dữ liệu, nhãn quan sát, ngân sách và giao thức. Mỗi giao thức lưu JSON, cờ cảnh báo và băm trước khi chạy tiếp. Nếu tài nguyên buộc giảm số thế giới, phải sửa đăng ký và được duyệt **trước khi chạy và xem bất kỳ kết quả so sánh nào**, không tự đổi sang thế giới thuận lợi.

Các seed phát triển v4 có thể dùng để kiểm thử hồi quy mã; không trộn chỉ số v4 vào điểm chọn v5. Ba thế giới hậu kiểm v4 không dùng để chọn hệ số hoặc xếp hạng ứng viên v5.

**Hai tầng bắt buộc:** tầng sàng lọc dùng tám thế giới 1001 đến 1008, seed mô hình 0, đủ S2 và 10 nhánh P2 kết hợp S2, tức 88 giao thức mỗi ứng viên. Ba ứng viên dẫn đầu theo J của tầng sàng lọc được sang tầng chọn; hòa điểm lấy thứ tự danh sách đã khóa. Tầng chọn dùng đủ 20 thế giới và năm seed 0 đến 4, lấy trung bình điểm dự đoán của năm seed, tức 220 giao thức và 1.100 lượt khớp mỗi ứng viên có giám sát trước lưới cây. **Chỉ chọn cấu hình cuối bằng tầng chọn.** Các đích ở tầng sàng lọc vẫn học từ 19 thế giới khác như khoản 3; tám là số đích được chấm, không phải quyền giảm nguồn.

Trước khi chạy cả tầng, đo thử một ứng viên trên một thế giới với đủ 11 giao thức, ghi thời gian đã đo, số lượt khớp, chi phí chuẩn bị và ước tính thời gian toàn tầng. Đây là ước tính, không phải cam kết tốc độ. Chạy bằng tiến trình tách rời, giới hạn bộ nhớ, lưu JSON và cờ cảnh báo sau từng giao thức; không tự giảm nguồn, thế giới, nhánh hoặc seed vì thời gian lâu.

## 3. Đăng ký các họ ứng viên và kiểm soát số lần thử

Các ý tưởng R2 được giới hạn theo giao việc: thay đổi theo thực thể và đuôi trái; thay đổi theo nhóm; công nợ; PU; đa dạng thế giới; tập hợp năm seed. Không thêm đặc trưng phân nhánh theo tên một kịch bản v4 hoặc v5. Các hàm chỉ nhận trường nghiệp vụ quan sát được và thời gian quá khứ, không nhận tên họ, nhãn thật hoặc mã kịch bản.

Trước từng ý tưởng R2 phải ghi tiêu chí giữ hoặc bỏ và phép so sánh vào nhật ký, sau đó mới chạy. Giữ cả kết quả không đạt. Lưới ban đầu cho bộ cây giữ hai cấu hình `(7 lá, 0,05)` và `(15 lá, 0,05)` của v4, tối đa 600 cây và dừng sớm 60 vòng; không mở lưới sau khi xem niêm phong. Tập hợp lấy trung bình điểm từ năm seed cố định **0, 1, 2, 3, 4**, không chọn seed tốt nhất.

**PU là nền bắt buộc:** mọi ứng viên có giám sát, kể cả L3 và L4-FB đối chứng, huấn luyện với trọng số dòng U là w. Chỉ chọn w trong **0,1; 0,2; 0,5** bằng J tầng sàng lọc trên L4-FB; khóa w trước khi sàng lọc các ứng viên còn lại. Nếu hòa, dùng thứ tự hệ số đã liệt kê. Giảm trọng số U là xấp xỉ PU, không chứng minh U là âm tính thật. nnPU chỉ thử nếu còn thời gian, là ứng viên riêng; phải đăng ký cách ước lượng tiên nghiệm từ dữ liệu nguồn trước khi chạy và không dùng nhãn thật của đích.

Thứ tự R2 được khóa: (1) sinh 20 thế giới, kiểm V1 đến V12 và ghi manifest; (2) chọn và khóa w; (3) `agent2/change_detect.py`, lớp mới `EntityDeviation2` với hai đuôi, CUSUM hai phía theo lương nhân viên, đơn giá nhà cung cấp, số tiền hóa đơn khách hàng, dịch chuyển nhóm cùng người lập hoặc duyệt trong kỳ, kiểm thử vét cạn; (4) công nợ gồm tuổi hóa đơn chưa thu, tỷ lệ không thu theo người phụ trách, đảo hoặc xóa nợ sau lập; (5) sàng lọc theo danh sách dưới đây; (6) tầng chọn năm seed chỉ cho ba ứng viên dẫn đầu. Không sửa lớp EntityDeviation cũ.

| Thứ tự | Ứng viên đã được cho phép |
|---|---|
| 1 | L3-PU |
| 2 | L4-FB-PU |
| 3 | L4-PU cộng EntityDeviation2 cộng công nợ |
| 4 | Cấu hình 3 với chính sách 2+1, kênh không nhãn là luật cộng EntityDeviation2 |
| 5 | Cold mới: luật cộng EntityDeviation2, hoàn toàn không nhãn |
| 6 | Cold cũ để đối chứng |

Khóa danh sách, tiêu chí giữ hoặc bỏ, phép so sánh và băm trong nhật ký trước chạy. Không mở thêm ứng viên sau khi xem kết quả. Chủ dự án đã làm rõ: **ba suất chuyển tầng chỉ dành cho ứng viên có giám sát; Cold chọn riêng như v1**. Cold không chiếm ba suất này. Theo lời làm rõ tiếp theo của chủ dự án ngày 2026-10-19, **Cold mới và Cold cũ đều chạy đủ tầng chọn trên 20 thế giới 1001 đến 1020**, không loại một Cold sau tầng sàng lọc. Sau đó mới chọn Cold riêng bằng cùng J, tức trung bình Q của bốn thế giới thấp nhất; giữ trần báo nhầm ca khó 15% ở từng thế giới và từng giao thức, cùng chốt chặn Cold ở mục 5. Các thành phần không nhãn cố định không được khớp theo nhãn hoặc seed có giám sát.

Mỗi ý tưởng có đối chứng dùng cùng nguồn học và cùng năm seed. Hiệu được báo trên toàn bộ thế giới, gồm số âm và thế giới tệ nhất, không chỉ trung bình. Danh sách hữu hạn ứng viên, thứ tự đơn giản đến phức tạp và băm mã phải được ghi vào manifest trước lần chạy so sánh chính. Muốn bổ sung họ ứng viên ngoài giao việc này phải được chủ dự án duyệt sửa đăng ký trước khi thử; không mở rộng sau niêm phong.

## 4. Quy tắc chọn theo nhóm thế giới thấp nhất

Với ứng viên c và thế giới đích w, đặt:

- R(c,w): recall chung ở S2 đầy đủ, trên tất cả dòng gian lận trong kỳ test.
- B(c,w): trung bình đều recall các nhánh có ít nhất 10 dòng dương kiểm thử ở thế giới w. Mọi nhánh có dưới 10 dòng dương được gộp thành một nhóm: tổng số dương được cảnh báo chia tổng số dương của các nhánh đó, rồi tính như một nhánh trong trung bình. Mỗi nhánh dùng cờ cảnh báo từ giao thức ẩn chính nhánh ấy; mọi giao dịch vẫn cạnh tranh cùng ngân sách. Nhóm gộp không có dòng dương thì không tạo phần tử rỗng trong trung bình; thiếu kết quả một giao thức vẫn là lỗi, không phải nhánh ít mẫu.
- Q(c,w) = [R(c,w) + B(c,w)] / 2.
- **J(c) là trung bình Q(c,w) của 20% số thế giới thấp nhất:** hai thế giới trong tám đích sàng lọc, bốn thế giới trong 20 đích tầng chọn. Báo thêm giá trị nhỏ nhất, trung bình và từng thế giới; không dùng giá trị nhỏ nhất thay J.

Điều kiện hợp lệ: tỷ lệ cảnh báo trên **toàn bộ ca hợp lệ khó không quá 15% ở từng thế giới**, kiểm riêng S2 đầy đủ và từng nhánh P2 kết hợp S2. Không thay trần bằng trung bình nhiều thế giới. Chỉ số thiếu hoặc không hữu hạn làm ứng viên không hợp lệ; không tự điền 0 hoặc bỏ thế giới. Nếu không còn ứng viên hợp lệ, dừng vòng chọn và báo thất bại phát triển.

Tầng sàng lọc lấy ba ứng viên hợp lệ có J cao nhất, hòa điểm theo thứ tự danh sách. Tầng chọn chỉ xét các ứng viên được chuyển tầng và chọn ứng viên hợp lệ có J cao nhất. Nếu chênh với điểm cao nhất **nhỏ hơn 0,01**, chọn ứng viên đứng trước trong danh sách đã khóa trước chạy. Không dùng AP, số liệu v4 hoặc bất kỳ số v5 niêm phong nào để phá hòa. Báo kèm trung bình, nhỏ nhất, từng thế giới, độ phân tán và ngân sách; trung bình không được thay J khi chọn.

Khởi đầu lạnh chọn riêng giữa các ứng viên hoàn toàn không nhãn, gồm luật và luật kết hợp EntityDeviation2. Dùng cùng J, cùng các nhánh đánh giá và cùng trần 15%; nhãn chỉ được dùng để **đo và chọn trên thế giới phát triển**, không khớp các thành phần chấm điểm hoặc hiệu chỉnh theo công ty đích. Lưu riêng cấu hình S2 có giám sát và cấu hình không nhãn.

Ngân sách cố định **tối đa ba dòng mỗi công ty mỗi tuần**, không có ngưỡng riêng cho một họ hoặc công ty niêm phong. Quy tắc gộp vụ và buộc thứ tự khi hòa được khóa trước R4. Không đổi từ ngân sách dòng sang ngân sách vụ sau khi có kết quả.

## 5. Chốt chặn phát triển và cổng niêm phong v5

**Chốt chặn trước niêm phong:** sau chọn bằng tầng chọn, ứng viên S2 được chọn phải đồng thời đạt recall S2 trung bình ít nhất **65%**, B trung bình ít nhất **40%**, recall S2 của thế giới tệ nhất ít nhất **50%**, và trần ca khó 15% ở từng thế giới, từng giao thức. Không đạt bất kỳ điều kiện nào thì **không sinh và không chấm niêm phong v5**; viết ngay đề xuất đổi hướng theo mục 7. Không đổi sang ứng viên khác để cứu cổng sau khi chọn.

Cold phải đồng thời đạt recall chung trung bình ít nhất **40%**, B trung bình ít nhất **33%**, recall thế giới tệ nhất ít nhất **30%**, cùng trần ca khó. Cold không đạt thì bỏ Cold; S2 vẫn đi tiếp nếu đạt. Các chốt chặn này tránh tiêu lượt niêm phong khi phát triển đã không đủ năng lực. Chúng không thay các cổng niêm phong đã đăng ký dưới đây.

Kiểm trên **bốn thế giới niêm phong v5**, sau thử khô, đúng một lượt hoàn chỉnh. Dùng trung bình đều theo thế giới, không gộp dòng khiến thế giới lớn chi phối. Bảy kịch bản v4 đã lộ không được tính vào tập “mới” của v5; tập mới được xác định bằng danh mục kịch bản độc lập v5 đã khóa trước chấm.

| Cổng | Điều kiện phải cùng đạt | Lý do đặt trước |
|---|---|---|
| V5-S2 chung | Trung bình recall chung từ **60%** | Ngưỡng cho giao thức chuyển công ty mới; đây là đề xuất cho vòng mới, không hạ cổng G5 để đổi kết luận v4 |
| V5-S2 mới | Trung bình recall trên kịch bản mới từ **35%** | Đòi hỏi chuyển giao tốt hơn mốc 31,22% S2 v4 trên dữ liệu tổng hợp; không chấp nhận chỉ tăng ở kịch bản đã biết |
| V5-S2 sàn | Recall chung của **từng thế giới từ 45%** | Chặn trường hợp trung bình che một thế giới suy sụp; không được bỏ thế giới kém nhất |
| V5-S2 lệch dev | Chênh tuyệt đối giữa recall S2 trung bình niêm phong và recall S2 trung bình ngoài thế giới của ứng viên chọn ở phát triển **không quá 15 điểm phần trăm** | So cùng định nghĩa S2; không so với J vốn gộp P2 hoặc S1 |
| V5-S2 báo nhầm | Toàn bộ ca hợp lệ khó **không quá 15% ở từng thế giới** | Điều kiện năng lực rà soát, giữ đồng nhất trần chọn và cổng; báo thêm ca khó mới riêng |
| V5-Cold | Không nhãn: recall chung trung bình từ **35%**, recall mới trung bình từ **30%**, recall chung từng thế giới từ **25%**, ca khó từng thế giới không quá **15%** | Mức dịch vụ thấp hơn mô hình có giám sát nhưng phải có sàn và giới hạn quá tải rõ ràng |

Các cổng là điều kiện đồng thời. V5-Cold trượt có nghĩa **không chấp nhận cung cấp chế độ khởi đầu lạnh**, không được dùng S2 đạt để quảng bá chế độ đó. S2 trượt bất kỳ điều kiện nào là thất bại phương pháp chính. Không lấy một phương pháp khác trong bảng chẩn đoán thay cho cấu hình đã chọn. S1 không cứu được cổng S2.

Khoảng bootstrap 95% theo vụ được báo cho recall, chênh và vụ phát hiện, cùng số dòng và vụ ở từng thế giới. Quyết định cổng dựa trên ước lượng điểm đã định nghĩa ở trên; không đổi sang một đầu khoảng hoặc thêm ngoại lệ sau khi xem số. Cảnh báo rõ nếu một kịch bản chỉ có rất ít vụ. Các khoảng không xác nhận hiệu năng doanh nghiệp thật.

## 6. R3 và R4 sau khi đăng ký được duyệt

R3 dùng một phiên agent khác, lịch sử tách biệt; phiên viết chỉ đọc brief được cấp, mẫu văn xuôi, ACFE và các vụ án Việt Nam. Cấm đọc `agent2/`, `docs/04_*`, `results/`, báo cáo hậu kiểm hoặc điểm mô hình. Không giao tên các điểm yếu mô hình cho phiên viết để nhắm kịch bản. Đây là độc lập giữa phiên, chưa thay thế tác giả nghiệp vụ hoặc kiểm toán viên độc lập.

Brief yêu cầu 8 đến 10 kịch bản và ca hợp lệ tương ứng, cơ chế dễ, vừa, khó, dấu thời gian, quy mô và nguồn; người mã hóa không sửa ý kịch bản để thuận lợi cho bộ phát hiện. Phải ghi nguồn, quyền truy cập, dấu vết bàn giao và những lần tác giả làm rõ. Chốt văn xuôi trước khi mã hóa. Nếu không kiểm soát được giới hạn đọc của phiên viết, không gọi tập đó là độc lập và phải báo chủ dự án trước R4.

Sinh bốn thế giới với seed do khâu giữ niêm phong chọn và ghi manifest trước sinh, khác mọi seed phát triển và thử khô. Mỗi thế giới yêu cầu 200.000 dòng, trong miền ngẫu nhiên hóa công ty và quy mô của đăng ký. Bảo đảm đủ kịch bản trong test và báo số vụ; mục tiêu tối thiểu ba vụ test cho mỗi kịch bản mới, tối thiểu 40 vụ gian lận test mỗi thế giới. Nếu bộ sinh không đáp ứng, chỉ sửa tính toàn vẹn và sinh lại trước khi chấm; không dùng điểm bộ phát hiện để quyết định sinh lại.

Kiểm V1 đến V12, khóa băm dữ liệu, kịch bản, mô hình, mã phụ thuộc, tham số và chính sách. Sau chọn, huấn luyện bản S2 cuối trên cả 20 nguồn theo cùng train và validation thời gian; lịch sử đích chỉ dùng cho thành phần không nhãn. Danh sách tệp băm phải bao gồm cả bộ luật và hợp đồng đặc trưng, không chỉ sáu module v4. Chạy thử khô trên seed khác trước khi chấm v5. Chỉ chấm một lần, lưu đầy đủ trước khi in chỉ số; lỗi hạ tầng chỉ được khôi phục nếu chưa có báo cáo hoặc chỉ số từng phần bị lộ, có nhật ký và bằng chứng.

Trước tải ERP Fraud Data, phải trình riêng **tên tệp, nguồn gốc chính thức, dung lượng xác minh và giấy phép**, chờ chủ dự án đồng ý. Bản đăng ký này không phải đồng ý tải. Không đưa dữ liệu thật lên Git hoặc dịch vụ ngoài. Chưa tải dữ liệu ngoài trong R0 hoặc R1.

## 7. Điều kiện đổi hướng sản phẩm

Nếu S2 v5 trượt bất kỳ cổng nào, giữ nguyên kết quả, không sửa rồi chấm lại, và viết đề xuất đổi hướng trong `09_ket_qua_niem_phong_v5.md`. Không tự mở vòng v6 để tiếp tục tìm số đạt.

Hướng phải trình chủ dự án là dịch vụ rà soát định kỳ cho đơn vị kế toán, với các quy tắc bằng chứng rõ, đối chiếu chứng từ và hàng đợi con người quyết định. Chưa quảng bá phát hiện gian lận tự động hoặc thu hồi tổn thất dựa trên dữ liệu tổng hợp. Nếu chỉ Cold trượt nhưng S2 đạt, không chào bán Cold; phải trình lại phạm vi sản phẩm S2 trước thí điểm.

Đề xuất đổi hướng phải nêu: công việc kế toán nào được hỗ trợ; phần nào vẫn phải người xử lý; ngân sách cảnh báo và thời gian; phép đo đáng kiểm tra, thời gian rà soát, mức sẵn lòng trả cần thu trong thí điểm. Các con số thí điểm chỉ được xác lập sau đồng ý pháp lý và doanh nghiệp; không tự thay bằng số tổng hợp. Nếu không còn ứng viên phát triển hợp lệ dưới trần 15%, hoặc ứng viên S2 đã chọn trượt chốt chặn phát triển ở mục 5, cũng dừng và viết ngay đề xuất này mà không sinh hoặc chấm niêm phong v5.

## Điểm báo cáo bắt buộc

1. Sau R0 và R1: đã bàn giao và nhận phê duyệt v1.1 ngày 2026-10-19. Được bắt đầu R2 sau commit đăng ký này.
2. Sau tầng sàng lọc: báo bảng J và ba ứng viên dẫn đầu, sau đó chạy tiếp tầng chọn, không chờ duyệt lại.
3. Sau chốt chặn: báo quyết định đi tiếp hoặc dừng; nếu S2 trượt, không sinh hoặc chấm niêm phong và viết đề xuất đổi hướng.
4. Trước tải dữ liệu ngoài: hỏi riêng với tệp, nguồn, dung lượng và giấy phép đã xác minh.
5. R3 dùng phiên tách biệt theo mục 6. Sau R4 bàn giao kết quả, quyết định cổng và đề xuất đổi hướng nếu trượt; không chỉnh sau kết quả.

Tại lúc cập nhật đăng ký: chưa chạy R2, chưa sinh thế giới phát triển v5, chưa tải dữ liệu ngoài hoặc chấm niêm phong v5.

---

## Phụ lục lịch sử: bản v1 nguyên văn, đã được thay thế bởi v1.1

# Đăng ký trước v5, đề xuất chờ chủ dự án duyệt

Ngày soạn 2026-10-19. **Trạng thái: CHỜ DUYỆT. Không bắt đầu R2.** Chủ dự án cần trả lời đúng ý “duyệt” cho bản này hoặc chỉ rõ nội dung cần sửa. Việc cho phép làm R0 không tự động là duyệt R1. Nếu sửa bản đề xuất, lưu dấu vết thay đổi và xin duyệt bản cuối trước khi thực hiện các thí nghiệm R2.

Mọi số đo dự kiến là trên **dữ liệu tổng hợp**, trừ khi một báo cáo kiểm thử ngoài hoặc thí điểm chỉ rõ nguồn thật và phạm vi nhãn. Kết luận **v4 không đạt G5 và kích hoạt M2** giữ nguyên. Ba seed v4 931 đến 933 đã được dùng để hậu kiểm, không còn là kiểm thử niêm phong và không được tính vào cổng v5.

## 1. Câu hỏi và giao thức chính

Mục tiêu chính là S2: học từ các thế giới tổng hợp khác rồi áp vào **công ty đích không có nhãn điều tra**. S2 được đánh giá riêng với chế độ khởi đầu lạnh không nhãn; S1 chỉ báo cáo phụ và không tham gia điểm chọn hoặc cổng đi tiếp.

| Giao thức | Nguồn học có giám sát | Công ty đích | Vai trò |
|---|---|---|---|
| S2 đầy đủ | Các thế giới nguồn, chỉ train và validation trước kỳ test | Chỉ lịch sử thô trước kỳ chấm, không đọc nhãn đích | Giao thức chính |
| P2 kết hợp S2 | Như S2, nhưng lần lượt ẩn một nhánh ACFE khỏi nhãn nguồn | Giữ toàn bộ giao dịch đích cạnh tranh cùng ngân sách; đo riêng gian lận của nhánh ẩn | Chọn khả năng chuyển giao |
| Khởi đầu lạnh không nhãn | Không dùng nhãn gian lận nguồn hoặc đích để khớp bộ chấm | Có lịch sử trước kỳ chấm để ước lượng nền và phân vị | Cấu hình riêng, cổng riêng |
| S1 phụ | Chỉ các dương tính đã xác nhận trong lịch sử cùng công ty và các dòng chưa biết | Nhãn chưa phát hiện là chưa biết, không phải âm tính đã xác nhận | Chẩn đoán phụ |

Lịch thời gian ban đầu giữ như v4: train năm 2024, validation nửa đầu 2025, test nửa cuối 2025. Nguồn chỉ dùng train và validation. Đích chỉ dùng thông tin quan sát trước giao dịch; tham chiếu hiệu chỉnh lấy trước kỳ chấm. Cấm đọc nhãn đích để chọn cây, ngưỡng, hệ số PU, cửa sổ, trọng số hoặc cấu hình. Đầu ra không nhãn được khớp trên lịch sử đích trước kỳ test; không khớp trên cả kỳ test.

Trong P2 kết hợp S2, các dòng thuộc nhánh bị ẩn vẫn ở lịch sử nhưng có trạng thái **U, chưa biết**. Dương tính quan sát có trạng thái **P, đã xác nhận**. S1 cũng dùng P và U; không được tuyên bố nhãn 0 của dữ liệu tổng hợp là âm tính đã kiểm tra. Nếu dùng giảm trọng số U trong hàm mất mát, phải ghi đó là phép xấp xỉ PU, có thể vẫn có thiên lệch; không đổi cách diễn giải nhãn thành âm tính thật. Chỉ dữ liệu được xác nhận hợp lệ bằng một nguồn riêng mới được gọi là âm tính đã xác nhận.

Đối chiếu R0 loại dòng nhờ biết nhãn thật không được trở thành cách lọc lịch sử trong S1 hoặc S2 v5. Không dùng họ kịch bản bị ẩn để sửa từng dòng đầu vào vận hành.

Khởi đầu lạnh ở đây nghĩa là **không có nhãn**, không phải hoàn toàn không có lịch sử. Tối thiểu 20 quan sát quá khứ cho nền thực thể; thiếu nền phải báo thiếu năng lực. Ngày đầu không có lịch sử chỉ chạy các luật có đủ bằng chứng, báo riêng là chế độ giảm, không gán các cổng khởi đầu lạnh dưới đây cho chế độ đó.

## 2. Thế giới phát triển và cách chia

1. Dùng đầy đủ **20 thế giới mới**, seed 1001 đến 1020. Yêu cầu ít nhất 8 thế giới là sàn tối thiểu về thiết kế; kế hoạch được duyệt này không cho phép chỉ chọn 8 trong 20 sau khi thấy kết quả. Nếu một thế giới lỗi kiểm định, sửa lỗi hạ tầng hoặc bộ sinh, ghi nhật ký và sinh lại đồng nhất trước khi so sánh; không loại vì mô hình làm kém.
2. Mỗi thế giới yêu cầu 200.000 giao dịch. Số công ty là số nguyên đều trong 30 đến 60; hệ số tiền lấy trên thang log từ 1 đến 20. Lịch lương thay đổi giữa các lịch hợp lệ theo cơ chế chung. Tỷ trọng L0, L1, L2 lấy từ Dirichlet(1,1,1) cho mỗi thế giới và ghi manifest, không chọn tỷ trọng theo điểm mô hình. Tỷ lệ gian lận mặc định 0,004, công khai là giả định tổng hợp; không diễn giải thành tần suất thật.
3. Mỗi thế giới làm đích một lần, học có giám sát từ **19 thế giới còn lại**. Mã công ty, thực thể và giao dịch có tiền tố thế giới; cấm trùng khóa giữa nguồn và đích. Mỗi vòng P2 kết hợp S2 ẩn lần lượt đủ 10 nhánh ACFE ở tất cả thế giới nguồn, trong cả train và validation; không bỏ nhánh khó.
4. Tất cả ứng viên dùng cùng bảng dữ liệu, nhãn quan sát, ngân sách và giao thức. Mỗi giao thức lưu JSON, cờ cảnh báo và băm trước khi chạy tiếp. Nếu tài nguyên buộc giảm số thế giới, phải sửa đăng ký và được duyệt **trước khi chạy và xem bất kỳ kết quả so sánh nào**, không tự đổi sang thế giới thuận lợi.

Các seed phát triển v4 có thể dùng để kiểm thử hồi quy mã; không trộn chỉ số v4 vào điểm chọn v5. Ba thế giới hậu kiểm v4 không dùng để chọn hệ số hoặc xếp hạng ứng viên v5.

Thiết kế đầy đủ có 20 đích nhân 11 giao thức, tức **220 giao thức cho một ứng viên**; một ứng viên tập hợp năm seed tương ứng 1.100 lượt khớp trước khi tính lưới cây nội bộ. Đây là số công việc theo thiết kế, chưa phải thời gian chạy đã đo. Phải thực thi lần lượt theo giới hạn bộ nhớ, lưu kết quả để tiếp tục sau ngắt, không tự giảm số seed hoặc thế giới vì thời gian lâu.

## 3. Đăng ký các họ ứng viên và kiểm soát số lần thử

Các ý tưởng R2 được giới hạn theo giao việc: thay đổi theo thực thể và đuôi trái; thay đổi theo nhóm; công nợ; PU; đa dạng thế giới; tập hợp năm seed. Không thêm đặc trưng phân nhánh theo tên một kịch bản v4 hoặc v5. Các hàm chỉ nhận trường nghiệp vụ quan sát được và thời gian quá khứ, không nhận tên họ, nhãn thật hoặc mã kịch bản.

Trước từng ý tưởng R2 phải ghi tiêu chí giữ hoặc bỏ và phép so sánh vào nhật ký, sau đó mới chạy. Giữ cả kết quả không đạt. Lưới ban đầu cho bộ cây giữ hai cấu hình `(7 lá, 0,05)` và `(15 lá, 0,05)` của v4, tối đa 600 cây và dừng sớm 60 vòng; không mở lưới sau khi xem niêm phong. Tập hợp lấy trung bình điểm từ năm seed cố định **0, 1, 2, 3, 4**, không chọn seed tốt nhất.

Với giảm trọng số U, chỉ thử ba hệ số cố định **0,1; 0,2; 0,5** trên phát triển. Nếu dùng nnPU, phải chốt cách ước lượng tiên nghiệm lớp từ dữ liệu nguồn quan sát, miền giá trị hợp lệ và cách chọn siêu tham số trước thí nghiệm tương ứng; không lấy tỷ lệ nhãn thật của công ty đích làm tiên nghiệm. Hệ số không phải bằng chứng rằng mọi U đều hợp lệ.

Mỗi ý tưởng có đối chứng dùng cùng nguồn học và cùng năm seed. Hiệu được báo trên toàn bộ thế giới, gồm số âm và thế giới tệ nhất, không chỉ trung bình. Danh sách hữu hạn ứng viên, thứ tự đơn giản đến phức tạp và băm mã phải được ghi vào manifest trước lần chạy so sánh chính. Muốn bổ sung họ ứng viên ngoài giao việc này phải được chủ dự án duyệt sửa đăng ký trước khi thử; không mở rộng sau niêm phong.

## 4. Quy tắc chọn theo thế giới tệ nhất

Với ứng viên c và thế giới đích w, đặt:

- R(c,w): recall chung ở S2 đầy đủ, trên tất cả dòng gian lận trong kỳ test.
- B(c,w): trung bình đều 10 recall theo nhánh bị ẩn của P2 kết hợp S2. Các dòng của mọi nhánh vẫn cạnh tranh cùng ngân sách; chỉ mẫu số đo recall thay đổi.
- Q(c,w) = [R(c,w) + B(c,w)] / 2.
- **Điểm chọn J(c) = nhỏ nhất của Q(c,w) trên toàn bộ 20 thế giới.**

Điều kiện hợp lệ: tỷ lệ cảnh báo trên **toàn bộ ca hợp lệ khó không quá 15% ở từng thế giới**, kiểm riêng S2 đầy đủ và từng nhánh P2 kết hợp S2. Không thay trần bằng trung bình nhiều thế giới. Chỉ số thiếu hoặc không hữu hạn làm ứng viên không hợp lệ; không tự điền 0 hoặc bỏ thế giới. Nếu không còn ứng viên hợp lệ, dừng vòng chọn và báo thất bại phát triển.

Chọn ứng viên hợp lệ có J cao nhất. Nếu chênh với điểm cao nhất **nhỏ hơn 0,01**, chọn ứng viên đứng trước trong danh sách đã khóa trước chạy. Không dùng AP, số liệu v4 hoặc bất kỳ số v5 niêm phong nào để phá hòa. Báo kèm trung bình, nhỏ nhất, từng thế giới, độ phân tán và ngân sách; trung bình không được thay J khi chọn.

Khởi đầu lạnh chọn riêng giữa các ứng viên hoàn toàn không nhãn, gồm luật và luật kết hợp EntityDeviation2. Dùng cùng J, cùng các nhánh đánh giá và cùng trần 15%; nhãn chỉ được dùng để **đo và chọn trên thế giới phát triển**, không khớp các thành phần chấm điểm hoặc hiệu chỉnh theo công ty đích. Lưu riêng cấu hình S2 có giám sát và cấu hình không nhãn.

Ngân sách cố định **tối đa ba dòng mỗi công ty mỗi tuần**, không có ngưỡng riêng cho một họ hoặc công ty niêm phong. Quy tắc gộp vụ và buộc thứ tự khi hòa được khóa trước R4. Không đổi từ ngân sách dòng sang ngân sách vụ sau khi có kết quả.

## 5. Cổng chấp nhận v5 đề xuất

Kiểm trên **bốn thế giới niêm phong v5**, sau thử khô, đúng một lượt hoàn chỉnh. Dùng trung bình đều theo thế giới, không gộp dòng khiến thế giới lớn chi phối. Bảy kịch bản v4 đã lộ không được tính vào tập “mới” của v5; tập mới được xác định bằng danh mục kịch bản độc lập v5 đã khóa trước chấm.

| Cổng | Điều kiện phải cùng đạt | Lý do đặt trước |
|---|---|---|
| V5-S2 chung | Trung bình recall chung từ **60%** | Ngưỡng cho giao thức chuyển công ty mới; đây là đề xuất cho vòng mới, không hạ cổng G5 để đổi kết luận v4 |
| V5-S2 mới | Trung bình recall trên kịch bản mới từ **35%** | Đòi hỏi chuyển giao tốt hơn mốc 31,22% S2 v4 trên dữ liệu tổng hợp; không chấp nhận chỉ tăng ở kịch bản đã biết |
| V5-S2 sàn | Recall chung của **từng thế giới từ 45%** | Chặn trường hợp trung bình che một thế giới suy sụp; không được bỏ thế giới kém nhất |
| V5-S2 lệch dev | Chênh tuyệt đối giữa recall S2 trung bình niêm phong và recall S2 trung bình ngoài thế giới của ứng viên chọn ở phát triển **không quá 15 điểm phần trăm** | So cùng định nghĩa S2; không so với J vốn gộp P2 hoặc S1 |
| V5-S2 báo nhầm | Toàn bộ ca hợp lệ khó **không quá 15% ở từng thế giới** | Điều kiện năng lực rà soát, giữ đồng nhất trần chọn và cổng; báo thêm ca khó mới riêng |
| V5-Cold | Không nhãn: recall chung trung bình từ **35%**, recall mới trung bình từ **30%**, recall chung từng thế giới từ **25%**, ca khó từng thế giới không quá **15%** | Mức dịch vụ thấp hơn mô hình có giám sát nhưng phải có sàn và giới hạn quá tải rõ ràng |

Các cổng là điều kiện đồng thời. V5-Cold trượt có nghĩa **không chấp nhận cung cấp chế độ khởi đầu lạnh**, không được dùng S2 đạt để quảng bá chế độ đó. S2 trượt bất kỳ điều kiện nào là thất bại phương pháp chính. Không lấy một phương pháp khác trong bảng chẩn đoán thay cho cấu hình đã chọn. S1 không cứu được cổng S2.

Khoảng bootstrap 95% theo vụ được báo cho recall, chênh và vụ phát hiện, cùng số dòng và vụ ở từng thế giới. Quyết định cổng dựa trên ước lượng điểm đã định nghĩa ở trên; không đổi sang một đầu khoảng hoặc thêm ngoại lệ sau khi xem số. Cảnh báo rõ nếu một kịch bản chỉ có rất ít vụ. Các khoảng không xác nhận hiệu năng doanh nghiệp thật.

## 6. R3 và R4 sau khi đăng ký được duyệt

R3 dùng một phiên agent khác, lịch sử tách biệt; phiên viết chỉ đọc brief được cấp, mẫu văn xuôi, ACFE và các vụ án Việt Nam. Cấm đọc `agent2/`, `docs/04_*`, `results/`, báo cáo hậu kiểm hoặc điểm mô hình. Không giao tên các điểm yếu mô hình cho phiên viết để nhắm kịch bản. Đây là độc lập giữa phiên, chưa thay thế tác giả nghiệp vụ hoặc kiểm toán viên độc lập.

Brief yêu cầu 8 đến 10 kịch bản và ca hợp lệ tương ứng, cơ chế dễ, vừa, khó, dấu thời gian, quy mô và nguồn; người mã hóa không sửa ý kịch bản để thuận lợi cho bộ phát hiện. Phải ghi nguồn, quyền truy cập, dấu vết bàn giao và những lần tác giả làm rõ. Chốt văn xuôi trước khi mã hóa. Nếu không kiểm soát được giới hạn đọc của phiên viết, không gọi tập đó là độc lập và phải báo chủ dự án trước R4.

Sinh bốn thế giới với seed do khâu giữ niêm phong chọn và ghi manifest trước sinh, khác mọi seed phát triển và thử khô. Mỗi thế giới yêu cầu 200.000 dòng, trong miền ngẫu nhiên hóa công ty và quy mô của đăng ký. Bảo đảm đủ kịch bản trong test và báo số vụ; mục tiêu tối thiểu ba vụ test cho mỗi kịch bản mới, tối thiểu 40 vụ gian lận test mỗi thế giới. Nếu bộ sinh không đáp ứng, chỉ sửa tính toàn vẹn và sinh lại trước khi chấm; không dùng điểm bộ phát hiện để quyết định sinh lại.

Kiểm V1 đến V12, khóa băm dữ liệu, kịch bản, mô hình, mã phụ thuộc, tham số và chính sách. Sau chọn, huấn luyện bản S2 cuối trên cả 20 nguồn theo cùng train và validation thời gian; lịch sử đích chỉ dùng cho thành phần không nhãn. Danh sách tệp băm phải bao gồm cả bộ luật và hợp đồng đặc trưng, không chỉ sáu module v4. Chạy thử khô trên seed khác trước khi chấm v5. Chỉ chấm một lần, lưu đầy đủ trước khi in chỉ số; lỗi hạ tầng chỉ được khôi phục nếu chưa có báo cáo hoặc chỉ số từng phần bị lộ, có nhật ký và bằng chứng.

Trước tải ERP Fraud Data, phải trình riêng **tên tệp, nguồn gốc chính thức, dung lượng xác minh và giấy phép**, chờ chủ dự án đồng ý. Bản đăng ký này không phải đồng ý tải. Không đưa dữ liệu thật lên Git hoặc dịch vụ ngoài. Chưa tải dữ liệu ngoài trong R0 hoặc R1.

## 7. Điều kiện đổi hướng sản phẩm

Nếu S2 v5 trượt bất kỳ cổng nào, giữ nguyên kết quả, không sửa rồi chấm lại, và viết đề xuất đổi hướng trong `09_ket_qua_niem_phong_v5.md`. Không tự mở vòng v6 để tiếp tục tìm số đạt.

Hướng phải trình chủ dự án là dịch vụ rà soát định kỳ cho đơn vị kế toán, với các quy tắc bằng chứng rõ, đối chiếu chứng từ và hàng đợi con người quyết định. Chưa quảng bá phát hiện gian lận tự động hoặc thu hồi tổn thất dựa trên dữ liệu tổng hợp. Nếu chỉ Cold trượt nhưng S2 đạt, không chào bán Cold; phải trình lại phạm vi sản phẩm S2 trước thí điểm.

Đề xuất đổi hướng phải nêu: công việc kế toán nào được hỗ trợ; phần nào vẫn phải người xử lý; ngân sách cảnh báo và thời gian; phép đo đáng kiểm tra, thời gian rà soát, mức sẵn lòng trả cần thu trong thí điểm. Các con số thí điểm chỉ được xác lập sau đồng ý pháp lý và doanh nghiệp; không tự thay bằng số tổng hợp. Nếu không còn ứng viên phát triển hợp lệ dưới trần 15%, cũng dừng và trình hướng này mà không tiêu tốn lượt niêm phong v5.

## Điểm dừng bắt buộc

1. **Sau R0 kèm R1:** bàn giao báo cáo, mã, JSON, kiểm thử, commit và bản đăng ký này; dừng chờ chủ dự án trả lời “duyệt”.
2. **Trước tải dữ liệu ngoài:** hỏi riêng từng bộ với tệp, nguồn, dung lượng và giấy phép đã xác minh.
3. **Sau R4:** bàn giao kết quả v5 và quyết định cổng; nếu trượt, có đề xuất đổi hướng, không chỉnh sau kết quả.

Chưa có phê duyệt R1 tại thời điểm soạn. Chưa bắt đầu R2, chưa tạo bộ phát hiện cải tiến, chưa sinh thế giới v5, chưa chạy niêm phong v5.
