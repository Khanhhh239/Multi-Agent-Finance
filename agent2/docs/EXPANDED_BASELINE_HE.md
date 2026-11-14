# Kiểm chứng HE và so sánh baseline bốn luật

14/11/2026 · CR-049 · thử nghiệm kỹ thuật local trên C001/C002 mô phỏng.

Baseline đã mở rộng gồm **P1/E3/B5/E4** tại node doanh nghiệp. Phép so sánh
dùng lại đúng model Mahalanobis đã fit riêng từng doanh nghiệp, chấm HE mới,
cùng snapshot và thời điểm, ngân sách tối đa **5 giao dịch/phương án/DN**.
Chính sách vẫn là luật trước, ML bổ sung chỗ trống; không tăng trọng số ML.

## Phạm vi tính mã hóa

| Thành phần | Phạm vi của lần kiểm chứng này |
|---|---|
| P1 | Hai ca Concrete FHE thật qua HTTP worker tách process, dữ liệu vào/ra là bản mã |
| ML | CKKS thật, model đã fit riêng DN, worker không có khóa giải mã |
| E3/B5/E4 | Evaluator local tại DN; **chưa có HE**, không gửi dữ liệu rõ cho worker |
| Baseline bốn luật hoàn toàn HE | **Chưa khả dụng** |

Báo cáo giữ `all_rule_evaluations_he=false` và ba luật thiếu HE riêng. Kết quả
so sánh local không được gắn nhãn baseline hoàn toàn mã hóa. Đây cũng chưa
phải kiểm chứng toàn bộ 35 luật, cloud public hoặc nghiệm thu UI Portal live.

## Điều được kiểm tra

- Sinh bản xuất mô phỏng 1.2.0 mới từ bộ P1 tám giao dịch/DN, bổ sung rõ
  phone/address/khai báo quan hệ của nguồn. Giao dịch, tiền, ngày, nghĩa vụ,
  số lượng NCC và phạm vi lịch sử giữ nguyên. Không điền vào dữ liệu thật.
- Lưu snapshot mới bất biến. So toàn bộ 33 feature trước/sau mở rộng master
  phải bằng nhau; không tái sử dụng điểm HE cũ cho snapshot mới.
- Đọc model/reference/feature contract/preprocess/fit receipt từ registry
  đúng DN. Không fit, active hoặc đổi model/khóa đã lưu trong lúc chấm.
- Chấm lại bằng CKKS, giải mã tại DN, so với cùng model tính rõ và kiểm
  thứ tự/lựa chọn. Dòng ML chưa khả dụng vẫn giữ trong coverage.
  Thứ tự tuyệt đối có đổi ở các điểm gần nhau trong dung sai; không có đảo cặp
  vượt dung sai và tập lựa chọn không đổi. Không tuyên bố thứ tự giống 100%.
- P1 chọn hai ca native: C001 đã vượt nghĩa vụ và C002 có điều chỉnh âm trong
  lịch sử. So nguyên số tiền, matched, kết quả circuit và evaluator canonical;
  kiểm đọc lại cùng ciphertext đã commit. Hai ca không thay toàn bộ ma trận P1.
- Worker/process/state dùng riêng cho thử nghiệm; không dừng dịch vụ live.
  Preflight supervisor Portal không được nghiệm thu lại trong bộ đo này.

## Cách hiểu lựa chọn

Tại mỗi DN, baseline chọn **P1_T03, P1_T06, P1_T07**. Kết hợp giữ ba khoản này
và thêm **P1_T04, P1_T02**. T06/T07 thuộc cùng nhóm đồng thời, không cắt nhóm
cho vừa ngân sách và không đếm thành hai vụ gian lận độc lập.

E3/B5/E4 là kiểm tra master theo policy hiện tại. Điểm đóng góp giao dịch là
0, không được tự nâng thành ưu tiên giao dịch. Bộ nguồn so sánh có một NCC;
ba kiểm tra master không thấy trùng trong nguồn đã gửi. Vì vậy baseline mở
rộng vẫn chọn ba khoản; không có thay đổi chính sách để ép thêm cảnh báo.

ML thêm hai khoản không có nghĩa toàn bộ luật bỏ sót: T04 là điều chỉnh âm,
P1 không áp dụng; T02 chưa vượt nghĩa vụ. Còn 31 luật snapshot chưa nối.
Accuracy, precision, recall, lợi ích thêm và thời gian rà nghiệp vụ vẫn null.
Muốn kết luận giá trị cần người hiểu nghiệp vụ rà các khoản được chọn.

## Chạy lại

Từ `D:\agent22`, cần Windows DPAPI dưới tài khoản đang giữ khóa, WSL Debian,
môi trường Concrete đã setup và các model/build công khai cục bộ hiện có:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/check_expanded_baseline_he.py --output .runtime/he4/expanded-baseline-recheck-01
```

Chọn thư mục mới. Mỗi phép P1 native có thể mất vài phút; không suy thành SLA.
CLI tạo thư mục riêng có ACL, giữ key/config/ciphertext trong `.runtime`.
Chỉ xuất các báo cáo và JSON nguồn mô phỏng được allowlist; không đưa thư mục
này nguyên gói lên GitHub. Không cần đăng nhập Portal để chạy bộ kiểm chứng.

Xem [bằng chứng và lệnh kiểm thử](../../Agent2_Spec_v2_1/evidence/R2/expanded_baseline_he_20261114/REPORT.md).
