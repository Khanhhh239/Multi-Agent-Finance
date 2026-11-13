# T6 thu nhiều lần và vận hành bundle theo chu kỳ

Ngày 13/11/2026. Đây là hợp đồng mã hiện tại và bằng chứng kiểm thử phần mềm.
Không thay gate pilot hoặc kết luận chất lượng trên doanh nghiệp thật.

## Mô phỏng và các điều kiện nghiệm thu

`adaptive.cash_adapter.iter_cash_paths` sinh riêng cho từng hóa đơn: tiền thu
từng tuần, dư nợ cuối từng tuần và tuần tất toán. Hàm `sample_cash` cộng các
chuỗi đó; không giữ đồng thời ma trận của toàn bộ danh mục trong bộ nhớ.

Tại mỗi tuần, hazard tất toán bằng khối xác suất T1 của tuần chia cho xác
suất còn chưa tất toán. Đường tất toán thu đúng dư nợ còn lại. Đường chưa
tất toán có thể trả một phần theo nhánh partial đã học; trạng thái đã nhận
tiền chuyển ngay sau khoản thu đầu tiên. Tất toán rồi thì thu bằng 0.

| Điều kiện | Cách kiểm |
| --- | --- |
| Không thu vượt dư nợ | Tiền thu lũy kế + dư nợ từng tuần = dư nợ đầu kỳ; dư nợ không âm, không tăng. |
| Tail vẫn có thể trả một phần | Kiểm các đường tuần tất toán = 14: có tiền thu trong 13 tuần nhưng vẫn còn nợ. Tail mô tả thời điểm tất toán, không phải số tiền chắc chắn mất. |
| Không thu lại tiền cũ hoặc coi giảm trừ là thu | Dự báo bắt đầu từ `observed.remaining_amount`; kiểm cả thanh toán trước ngày chốt và sửa giảm công nợ có lịch sử phiên bản. |
| Không trừ rủi ro lần hai | Xác suất xóa nợ chỉ phục vụ thông tin/xếp hạng. Thay xác suất này không đổi chuỗi tiền; nhánh `p_bad`/cure cũ đã xóa. |
| Tuần tất toán khớp T1 | So tần suất tuần tất toán trên 80.000 đường mỗi hóa đơn với đủ 14 ô T1, gồm tail. |
| Kỳ vọng và Monte Carlo cùng mô hình | `expected_cash` tính kỳ vọng theo cùng hazard, xác suất partial và phân phối tỷ lệ; kiểm trung bình đường thu với kỳ vọng giải tích. |
| Giới hạn SHAP không cắt danh mục | Kiểm danh mục 45 hóa đơn, gồm khoản tạm hoãn liên hệ; SHAP 0/30 cho cùng chuỗi tiền và số dư. Danh sách ưu tiên vẫn có giới hạn hiển thị riêng. |

T6 cộng tiền thu công nợ với lịch thu/chi T5 và số dư đầu kỳ. Phần hoạt động,
nếu bật, vẫn có nguồn và mô hình riêng. Không cộng tiền đã nhận tại ngày
chốt vào dự thu nữa; số dư đầu kỳ phải là số dư đã gồm giao dịch thực tế.

## Giữ riêng kỳ vọng, trung vị và dải tiền

Mỗi tuần trả về:

- `balance` và `expected_balance`: số dư kỳ vọng giải tích, giữ tên `balance`
  để các kế hoạch/phân rã hiện có tiếp tục đọc được.
- `median_balance`: trung vị số dư mô phỏng.
- `balance_quantiles`: P10/P50/P90 **gốc** của mô phỏng.
- `low`/`high`: dải đang phục vụ; khi hiệu chỉnh, giữ thêm `raw_low`/`raw_high`.

Giao diện, biểu đồ và Excel có P50 riêng. Không lấy P50 thay kỳ vọng trong
phương trình đối chiếu tiền. `any_below_floor_probability` đếm đường từng
xuống dưới ngưỡng trong kỳ; không nhân các xác suất biên theo tuần.

Protocol mới là `settlement-partial-paths-v1`; kế hoạch từ engine cũ không
được dùng chung để hiệu chỉnh. `calibrate_bands` chỉ dùng dự báo đã lưu
trước/kịp origin, cùng model/scenario/phạm vi tài khoản/protocol, đã đủ nhãn
và các origin không chồng lấn. Cần ít nhất 12 origin; thiếu thì giữ dải gốc.
`band_status` cho biết trạng thái. Hiệu chỉnh dải không thay kỳ vọng,
trung vị, phân vị mô phỏng gốc hoặc xác suất cảnh báo gốc.

Mặc định vẫn độc lập giữa hóa đơn. `shared_customer_risk` là kịch bản stress
được gắn nhãn, chưa phải tham số phụ thuộc đã được lựa chọn/kiểm định.
Phép đo raw partial phải hoàn tất trước nghiên cứu chọn phụ thuộc hoặc
hiệu chỉnh dải bằng tập sai số ngoài mẫu riêng.

## Cập nhật định kỳ và bản kê bundle

`UpdatePolicy` mặc định 28 ngày/lần, tối đa 730 ngày lịch sử, trọng số gần
đây có half-life 180 ngày. Không cho cấu hình cửa sổ lớn hơn 730 ngày.
Thanh toán mới cập nhật dataset/công nợ; `/v1/predict` dùng trạng thái mới
với cùng bundle đang phục vụ. Không train T1 trong request dự báo hoặc mỗi
giao dịch. Kiểm thử API xác nhận dư nợ 100 → 60 sau khoản thu 40, cùng mã T1.

Job `python -m agent1_service.jobs.t1_update` được gọi từ scheduler bên ngoài;
trạng thái `next_due` trong kho ngăn cập nhật trước chu kỳ. Lượt thay đổi này
không cài scheduler trên máy hoặc kích hoạt phiên bản trong kho doanh nghiệp.

`serving_manifest` lưu riêng mã T1/hash model, adapter, partial, phiên bản
dữ liệu, policy/hash policy và `ready_on`. Bản global dùng hash catalog làm
phiên bản nguồn dữ liệu; catalog giữ provenance/replay của gói. Bản local
dùng hash dữ liệu tại lần học được chấp nhận. Thử cập nhật nhưng thiếu nhãn
hoặc không qua audit giữ T1, partial và manifest hiện tại. Dữ liệu của lần
thử cập nhật nằm ở metadata update riêng. Challenger chỉ có ngày sẵn sàng
phục vụ mới sau khi qua audit; không lùi ngày quyết định về ngày học.

## Kiểm chứng trên doanh nghiệp mới

Runner `scripts/business/evaluate_t6_new_company.py` có ba pha tách biệt:

1. `lock`: khóa danh sách doanh nghiệp, hash dataset/catalog/source, policy
   thích nghi, ngân sách/seed mô phỏng, ngưỡng tiền và quy tắc cảnh báo.
2. `predict`: chỉ chuyển dữ liệu đã biết tại cutoff vào T1 và T6; thích nghi
   bằng validation/audit quá khứ, so với global. Lưu hai dự báo và toàn bộ
   đường số dư, hash và receipt trước khi chấm. Chạy lại không học lại nếu
   receipt hợp lệ đã tồn tại.
3. `score`: chỉ đọc dự báo đã đóng băng, sau đó mở nhãn tương lai từ sao kê
   đủ phạm vi. Không dùng điểm tương lai để thay cấu hình. Báo cáo lỗi tiền,
   interval score/coverage, CRPS biên, energy score của cả đường tiền,
   Brier thiếu tiền từng tuần/cả kỳ, báo giả và bỏ sót.

Energy score dùng khoảng cách Euclid trên toàn chuỗi, chia căn bậc hai của
số tuần; CRPS được tính từ toàn bộ mẫu theo tuần. Kết quả tổng hợp cho trọng
số bằng nhau giữa doanh nghiệp; không coi hóa đơn/tuần của cùng doanh nghiệp
là các doanh nghiệp độc lập.

Ví dụ config JSON (`dataset` tương đối so với vị trí config):

```json
{
  "development_firms": ["FIRM_USED_TO_SELECT_POLICY"],
  "companies": [{
    "firm_id": "NEW_FIRM",
    "dataset": "new_firm.json",
    "cutoff": "2025-12-31",
    "truth_asof": "2026-04-30",
    "accounts": ["BANK_ACCOUNT"],
    "opening_balance": 100000000,
    "synthetic": false,
    "heldout_from_global_and_policy_selection": true
  }]
}
```

```powershell
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py lock --config config.json --output agent1/outputs/t6/new_company_run
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py predict --output agent1/outputs/t6/new_company_run
.\.venv\Scripts\python.exe agent1/scripts/business/evaluate_t6_new_company.py score --output agent1/outputs/t6/new_company_run
```

Khai báo holdout là cam kết nguồn dữ liệu cần được kiểm tra bởi người tổ chức
đánh giá; mã không thể tự chứng minh một doanh nghiệp chưa từng bị xem ở
ngoài quy trình. Runner từ chối doanh nghiệp trùng nhóm development đã khai.

`verify_t6_new_company.py` tạo hai ledger toy mới với seed khóa `261113605`,
chạy cùng quy trình và lưu tại
`outputs/implementation/t6_partial_paths_20261113/fresh_synthetic_final/`.
Ledger đã được xem trong lượt kiểm tra tích hợp ban đầu; lượt verified tính
lại cùng ca sau khi thêm kiểm tra ổn định số học cho số dư VND lớn.
Cả hai lần thích nghi giữ incumbent vì một cửa sổ validation chưa đủ nhãn
được xác nhận ở đúng ngày lịch sử. Đây là bằng chứng của nhánh giữ bundle
và cơ chế đóng băng/chấm, không phải bằng chứng fine-tune tốt hơn global.
Coverage raw của hai ca lần lượt 3/13 và 10/13 tuần, nên không nghiệm thu
chất lượng dải hoặc cảnh báo trên doanh nghiệp thật từ lượt này.

## 7. Hoàn thiện T10 cho bundle mới

[Hợp đồng T10 ngày 13/11](T10_BUNDLE_EVIDENCE_2026-11-13.md) bổ sung bước 7:
adapter/T6 xuất bằng chứng có cấu trúc theo hóa đơn/tuần, T10 đọc forecast
đã lưu cùng đúng T1/adapter/partial/T6, tách SHAP xác suất với giải thích tiền
và phân rã kế toán. Kịch bản chạy lại MC so kỳ vọng, P10/P50/P90 và Δ xác suất
thiếu tiền bằng cùng nguồn ngẫu nhiên. Protocol dải hiện tăng từ
`settlement-partial-paths-v1` lên `settlement-partial-paths-v2` sau sửa RNG
khách cụ thể. Bộ dịch kỳ vọng cũ đã xóa. Các kết quả kiểm thử T6 bên dưới
là bằng chứng trước bước 7; kiểm thử bản hiện tại lưu riêng ở output T10.

## Code cũ đã dọn

- Xóa bản sao `experiments/t1_compact/legacy_cash.py`; các lệnh tái lập lịch
  sử đọc trực tiếp source snapshot frozen qua `historical_workspace`.
- Xóa `conditional_payment_pmf`, nhánh rút `p_bad`, `rho_bad` và tham số
  `recovery_rate` không sử dụng khỏi engine nghiên cứu. Xóa việc fit cure,
  chẩn đoán và nhánh benchmark cure tương ứng trong `scripts/run_t6.py`.
- Xóa tham số cũ ở T10 và import không còn sử dụng; phiên bản measurement
  của runner cũ đổi để không gán nhầm kết quả mới cho báo cáo v5.

`models/t6_cash.py` còn bên gọi từ `/forecast` research và các nghiên cứu
T4/ACI/T10. Nó không phải engine của `/v1/predict`; không xóa cả pipeline
nghiên cứu đang có bên gọi. Source snapshot và báo cáo cũ giữ nguyên.

Các kiểm tra chức năng chính nằm ở `test_t6_acceptance.py`,
`test_cash_adapter.py`, `test_t6_new_company.py`, `test_t1_periodic.py`,
`test_cash_explanations.py` và `test_t5_runtime.py`. XML kết quả và báo cáo
tổng hợp nằm trong `outputs/implementation/t6_partial_paths_20261113/`.

Kết quả tổng hợp theo mã ca kiểm thử sau các lượt sửa/chạy lại: **386 ca
Python đạt, 3 bỏ qua; 28 ca UI đạt; Ruff E9/F không có lỗi**. Đây không phải
một lượt full-suite mới: XML chạy rộng và các XML chạy lại phần bị ảnh hưởng
đều được giữ, `summarize_checks.py` lấy kết quả sau cùng của mỗi ca vào
`checks_summary.json`. Hai ca lỗi trong lượt chạy rộng đã đạt khi chạy lại.
