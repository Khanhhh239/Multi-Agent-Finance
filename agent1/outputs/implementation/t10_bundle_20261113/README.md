# Kiểm chứng T10 bundle — hoàn tất 14/11/2026

Lượt triển khai bắt đầu 13/11; thư mục giữ ngày bắt đầu. Đây là bằng chứng
chức năng và tính nhất quán của engine, không phải gate chất lượng tiền,
coverage, can thiệp thu nợ hoặc doanh nghiệp thật.

## Kết quả

- `tests.xml`: chạy rộng 403 ca; 397 đạt, 3 lỗi, 3 bỏ qua.
- `recheck.xml`: 150 ca thuộc các phần bị ảnh hưởng sau sửa; tất cả đạt.
- `checks_summary.json`: hợp theo classname/name, lấy kết quả sau cùng:
  **401 Python đạt, 0 lỗi, 3 bỏ qua** trên 404 ca duy nhất. Đây không phải
  một lần full-suite thứ hai. `collect_checks.py` tái lập phép hợp.
- `ui.xml`: **31 ca JavaScript đạt**. Kiểm browser nằm trong Python XML:
  mở bằng chứng partial, chạy kịch bản và kiểm layout desktop/mobile.
- `ruff.json`: 0 lỗi E9/F; `node --check` và `git diff --check` đạt.

Ba lỗi trong lượt rộng: một danh sách sheet còn trông chờ hai sheet dịch
kỳ vọng cũ; hai model giả được khai báo trong hàm nên không thể lưu thành
artifact. Đã cập nhật sheet và chuyển các model giả ra cấp module, giữ
nguyên xác suất/kiểm tra tiền. Thêm thông báo rõ khi T1 không thể lưu/phát
lại. Ba ca bỏ qua là GRU/GRU-wide/LSTM vì môi trường không cài Torch, không
phải ba ca T10 bị bỏ qua.

## Bằng chứng có thể mở

`example/` được tạo bằng `scripts/business/verify_t10_bundle.py`, với global
bundle thực tế và ba hóa đơn fixture, seed `261113710`, 2.000 đường. Không
train, không kích hoạt model, không ghi vào kho doanh nghiệp.

- `forecast.json`: SHAP của T1 (đích xác suất tất toán 4 tuần), adapter facts,
  profile partial/hỗ trợ, phân rã kế toán, phiên bản và hash replay.
- `forecast.xlsx`: cùng số engine, thêm các sheet partial và phiên bản.
- `noop.json`: phát lại nguyên trạng; số dư, phân vị và xác suất không đổi.
- `customer_delay.json`: chỉ khách A trả chậm thêm 2 tuần, cùng các lần rút.
- `expense_deferral.json`: chỉ khoản RENT dời thêm 1 tuần.
- `verification.json`: các bất biến đã kiểm và danh tính engine/runtime.

Trong fixture này, xác suất có ít nhất một tuần thiếu tiền lần lượt là
0,849 ở baseline; 1,0 khi khách A chậm; 0,6235 khi dời RENT. Đây là độ nhạy
của fixture trong mô hình, không phải tác động nhân quả hoặc số đo chất
lượng trên doanh nghiệp. Kiểm thiếu tiền cả kỳ dùng các đường danh mục,
không nhân xác suất tuần hoặc cộng P10 từng hóa đơn.

JSON/Excel giữ phần lẻ của kỳ vọng; UI làm tròn khi định dạng tiền. Ví dụ
hóa đơn I0 còn nợ 60 triệu; tuần 1 engine tính tiền từ tất toán
22.853.921,015447687 và partial 488.332,7648183405 VND, tổng
23.342.253,780266028 VND. Không lấy SHAP xác suất nhân lại vào số tiền này.

## Tái lập từ gốc repository

```powershell
$env:PYTHONPATH = 'agent1'
$env:PYTHONUTF8 = '1'
.venv/Scripts/python.exe -m pytest agent1/tests/adaptive agent1/tests/test_t6.py agent1/tests/test_t10.py agent1/tests/test_service_scenarios.py agent1/tests/test_service_aci_state.py agent1/tests/test_aci_band.py agent1/tests/test_cash_cohort.py agent1/tests/test_cash_context.py agent1/tests/test_error_propagation_cash.py -q
node --test agent1/tests/adaptive/t6_cash_ui.test.cjs agent1/tests/adaptive/t1_explanations_ui.test.cjs
.venv/Scripts/python.exe agent1/scripts/business/verify_t10_bundle.py --output agent1/outputs/implementation/t10_bundle_20261113/example_replay
```

Lệnh trên kiểm bản hiện tại; không ghi đè XML đã lưu. Ví dụ dùng cùng fixture
đã xem, không phải holdout doanh nghiệp mới. Không đổi source/runtime giữa
lúc tạo forecast và kịch bản; replay sẽ từ chối nếu khác bản. Source/runtime
lịch sử được giữ trong kho phục vụ, chưa có bộ tự triển khai nhiều môi
trường engine.
