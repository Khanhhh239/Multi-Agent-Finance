# Bàn giao Antigravity: nối ML với cùng snapshot nguồn đầy đủ của 35 luật

Ngày 14/11/2026 · workspace `D:\agent22` · đây là nhiệm vụ xây bridge mới,
chưa phải biên bản đã triển khai hoặc đã chấm thành công trên Portal.

## Bối cảnh

Agent2 hiện có hai đường dữ liệu:

| Đường | Đã có | Phần cần nối |
|---|---|---|
| Snapshot canonical Finance input 1.0/1.1/1.2 | Bộ tạo 33 feature point-in-time; artifact/model theo DN; adapter ML; luồng HE thử nghiệm riêng | Chưa nhận trực tiếp profile nguồn đầy đủ mới |
| `agent2-rule-snapshot/1.0.0` | Nguồn native, lịch sử/coverage/checksum, danh sách ứng viên; 35 luật qua nhập/snapshot/API/UI tại DN | Chưa bridge sang bộ 33 feature và nhánh ML, nên ML hiện unavailable đúng thiết kế |

Code 35 luật đã qua 120 gói/140 ca đối chiếu, 255 kiểm thử hồi quy và 6 bước UI
trên server riêng. Những kiểm thử đó **không chứng minh bridge ML đã có**.
Triển khai/QA Portal là hai nhiệm vụ riêng; thống nhất revision và quyền sửa
file trước, tránh một người restart trong khi người khác đang nghiệm thu.

Mục tiêu: cùng một snapshot bất biến, cùng DN/as_of và cùng tập ứng viên trả
kết quả luật và ML ghép đúng từng giao dịch. Ví dụ một khoản không trúng luật
vẫn được ML đánh giá mức bất thường nếu đủ feature/model. Giữ lịch sử làm
context, không biến toàn bộ lịch sử thành các ứng viên cần rà.

Luật là một thành phần, không đặt tỷ trọng 70–80%. Điểm ML là bất thường so với
reference, chưa phải xác suất gian lận. Bước này chưa xác nhận lợi ích nghiệp vụ.

## Đọc trước và điểm tích hợp

- `agent2/docs/FULL_RULE_PIPELINE.md`: profile nguồn đầy đủ, giới hạn native.
- `agent2/docs/SNAPSHOT_FEATURES.md`: semantics 33 cột, hai đồng hồ và missing.
- `agent2/docs/COMPANY_MODEL_JOBS.md`, `METHOD_OUTPUTS.md`: fit riêng, artifact,
  preprocess/reference, tương thích và score độc lập với luật.
- `agent2/sme_fraud/rule_snapshot.py`: dispatch/kết quả 35 luật; hiện ba nhánh
  độc lập thống kê/graph/ML cố ý trả unavailable.
- `agent2/sme_fraud/snapshot_features.py`: `COLUMNS`, `feature_contract()`,
  `build_from_snapshot()`; phiên bản hiện tại snapshot-point-in-time/1.1.0.
- `agent2/sme_fraud/feature_pipeline.py`: artifact feature và provenance.
- `agent2/sme_fraud/method_adapters.py`: `score_batch()`, kiểm model/reference.
- `agent2/sme_fraud/method_jobs.py`, `method_store.py`: fit/score tách biệt,
  kho artifact bền vững. `analysis_resources.py`: binding model ghim theo DN.
- `agent2/sme_fraud/snapshot_analysis.py`, `analysis_branches.py`,
  `web/workbench.js`: tích hợp API/DTO/giao diện theo vai trò.
- `agent2/docs/HE_REGISTRY_EXPORT.md`, `HE_WEB_ANALYSIS.md`,
  `EXPANDED_BASELINE_HE.md`: ranh giới đường chấm mã hóa hiện có.

## Việc xây theo thứ tự

### 1. Chốt mapping nguồn cho đủ 33 feature

Xuất bảng từ `snapshot_features.COLUMNS`, mỗi dòng có: tên/thứ tự feature,
đơn vị/semantics, bảng + trường nguồn native, quan hệ/ID/revision, cutoff,
coverage cần, và lý do null khi không đủ nguồn. Không tự chọn 33 cột khác.

Đối chiếu đặc biệt:

- `posted_at` của native không tự đồng nghĩa mọi trường effective_at/created_at/
  approved_at. Ghi rõ đồng hồ nghiệp vụ và thời điểm được biết; nếu nguồn không
  đủ để xác nhận semantics thì trả missing/incompatible thay vì đổi tên trường.
- Chuỗi invoice_number hoặc invoice_gross_vnd trong giao dịch không tự chứng
  minh có bản ghi hóa đơn, revision, phân bổ và toàn bộ lịch sử thanh toán.
- `support_doc_count` không thay các bản ghi chứng từ gốc đã xác minh.
- Hạn mức giao dịch/người lập không tự thành hạn mức đã được người duyệt xác
  nhận. Chỉ dùng khi có nguồn phê duyệt đúng semantics của feature hiện hành.
- Tài khoản không có mã ngân hàng không được tự bổ sung mã hoặc tạo liên kết
  ngân hàng mạnh để làm feature graph khả dụng.
- Coverage complete là khai báo bên xuất; không tự chứng minh nguồn bên ngoài
  đầy đủ. Feature lịch sử thiếu nguồn vẫn null + lý do, không điền 0.

Giữ amount gốc, định danh, nhãn và evidence riêng. Không dùng hit/điểm/tên luật,
case signal/control, tên tệp, source_id/seed/template, company/transaction IDs
làm predictor. Tránh rò rỉ kịch bản mô phỏng vào model.

### 2. Xây adapter đọc snapshot, tạo frame và provenance

Ưu tiên bridge riêng để giữ semantics/byte contract cũ ổn định; không đưa DTO
placeholder của native vào ma trận dự báo. Kiểm quyền/checksum trước đọc, recheck
trước trả kết quả, không có cờ client bỏ validation. Đọc chứng từ đã xác minh
không là xác minh mới; quyền evidence.verify vẫn bảo vệ thao tác nhập/xác minh.

Tạo các kênh features/missing/rows/evidence/contract/manifest, ghim snapshot ID,
tenant/DN, data checksum, as_of, candidate IDs, bridge version/hash và source
references. Projection nội bộ nếu có phải truy ngược về snapshot gốc, không
âm thầm tạo một nguồn độc lập rồi chỉ ghép kết quả theo tên file hoặc số dòng.

Dùng nguyên semantics point-in-time: context đã biết tại cutoff của từng dòng,
lịch sử trước nhóm; các giao dịch đồng thời không thấy nhau. Nguồn đến muộn
không sửa feature quá khứ. Không tự cắt nguồn để vừa giới hạn tính toán.

Đầu ra có schema 33 cột đúng thứ tự, giá trị null/mask rõ. 33 cột **không đồng
nghĩa 33 giá trị đã đủ**. Nếu không thể bảo toàn semantics của contract cũ,
tạo contract/phiên bản mới và kiểm model không tương thích; không chép fingerprint
cũ vào frame mới để qua gate. Thay file adapter cũ có thể đổi fingerprint do
contract ghim code hash; đánh giá tác động trước khi sửa.

### 3. Nạp model đúng DN, chấm độc lập với luật

Model phải được ghim bằng artifact ID/binding phía server. Kiểm tenant/DN,
checksum, full feature contract, selected_columns, preprocess/runtime/reference
và kỳ fit. Không dùng model “mới nhất”, model DN khác hoặc nhận pickle từ browser.

Fit và inference tách biệt: dùng history trước reference, cả hai trước kỳ chấm,
không trùng giao dịch. Mẫu B1 hiện ở tháng 8/2025; model fit sau mốc đó phải bị
chặn đúng chính sách. Không sửa ngày mẫu/model, fit receipt hoặc overlap check.
Muốn có ca chấm thành công, chuẩn bị nguồn mô phỏng đúng kỳ và artifact phù hợp
trong sandbox; fit thử là job offline có quyền, không tự fit trong `/analyze`
hoặc thay model live. Phân biệt backtest với prospective deployment.

Thiếu model/không tương thích/thiếu feature: giữ dòng và trả unavailable, điểm
null + mã lý do. Missing policy dùng đúng policy đã fit: strict hoặc median_flags
với median học từ train; không học từ batch đang chấm, không tự đổi cột.

Chấm mọi ứng viên đủ điều kiện kể cả không trúng luật. Không chọn top-K hoặc
lọc theo hit luật trước ML. Kết quả model/feature/provenance không ghi ngược
vào dữ liệu nguồn, không thay matched/score của 35 luật.

### 4. Tích hợp API/UI và giữ ranh giới HE

Ghép bằng khóa tenant + company + snapshot + transaction/revision; chứng minh
revision từ snapshot không bị tạo giả. Analysis context/ID phải ghim bridge,
feature contract và model/preprocess/reference/execution receipt để không đọc
nhầm cache của lượt trước. Cùng snapshot ID chưa đủ nếu model/cutoff khác nhau.

Trên UI cùng một giao dịch hiện kết quả luật và ML cùng nguồn/thời điểm. Người
rà thấy trạng thái và lý do dễ hiểu; model/version/feature details nằm ở view
quản lý. Không hiển thị “80% gian lận” từ raw score hoặc empirical midrank.

Yêu cầu cloud ciphertext-only vẫn giữ: tạo feature/model/key/decrypt tại DN,
worker chỉ nhận/tính/trả bản mã. Đối chiếu plaintext trong sandbox DN được ghi
rõ execution mode; không biến nó thành fallback từ yêu cầu HE của Portal.

Đường HE hiện kiểm chứng Mahalanobis với **2 feature được chọn**, không phải
HE cho đủ 33 feature hay IF/ECOD/LOF/AE. Bridge 33 feature chỉ có thể cấp đúng
subset cho model HE đã ghim nếu contract/provenance tương thích và đường export
đã kiểm lại; không tự đổi selected_columns/model/khóa hoặc giả có HE mới.
Nếu chưa nối HE cho profile mới, báo unavailable rõ trên đường đó; không lấy
điểm HE cũ của snapshot khác để trình bày như lần chấm mới.

## Nghiệm thu bắt buộc

1. C001/C002 mỗi bên 5 ứng viên và lịch sử riêng: trả đủ 5 dòng. Cùng transaction
   ID ở hai DN không trộn feature/model/evidence; đảo thứ tự nguồn không đổi vector.
2. Ít nhất một dòng không trúng luật vẫn có điểm ML khi nguồn/model tương thích.
3. Cặp nguồn canonical và full-source tương đương về nghiệp vụ: đối chiếu đủ 33
   cột, mask, thời gian, evidence và kết quả cùng model. Không ép null thành 0
   để đạt parity; cột không ánh xạ được ghi gap/contract mới.
4. Chứng từ đến muộn, master revision tương lai, hai khoản đồng thời và lịch sử
   hóa đơn thiếu nguồn giữ đúng semantics R1. Thử signed/zero ở miền được hỗ trợ;
   native ngoài miền phải bị chặn rõ, không abs hoặc đổi ngày nguồn.
5. Không có model, model khác DN, sai fingerprint/thứ tự cột, fit tương lai,
   train/reference overlap, corrupt artifact: unavailable/null đúng lý do;
   không mở kho model để ghi hoặc fit ngầm khi chấm.
6. Thay ID đồng bộ không đổi numeric feature. Thêm outlier khác vào batch chấm
   không đổi reference/điểm các dòng cũ. Dòng thiếu feature xử lý đúng policy đã fit.
7. Retry/restart giữ artifact/model/source binding; quyền thu hồi hoặc model
   binding đổi giữa chừng bị chặn. Không sửa snapshot/model/key live khi test.
8. Kết quả 35 luật trước/sau bridge giữ nguyên trên cùng nguồn. Các test R1/R2,
   canonical và HE bị tác động phải chạy lại; không bỏ compatibility gate để pass.
9. Nếu nối đường HE: chấm mới từ đúng snapshot, so cùng model tính rõ tại DN
   với tolerance/ranking khai trước; worker không có dữ liệu rõ/model rõ/secret
   key. Đường chưa hỗ trợ không được ghi full-HE passed.

## Đánh giá sau khi bridge đạt

Giữ chính sách đã chọn: cùng kỳ, tối đa **5 giao dịch/phương án/DN**, luật trước,
ML bổ sung chỗ trống. Chưa có chính sách tổng hợp transaction priority cho cả
35 luật thì phải liệt kê gap, không tự cộng điểm hoặc biến context/master/D/F4
thành mandatory routing. Bridge có thể hoàn tất kỹ thuật trước phần policy này.

Chỉ so các kết quả cùng source/candidate/cutoff, ghi rõ snapshot/model và phần
unavailable. Số ML bổ sung không tự là số luật bỏ sót hay số gian lận. Precision,
lợi ích thêm/thời gian rà cần kết luận nghiệp vụ có căn cứ, không tự điền nhãn.

## Đầu ra Antigravity cần bàn giao

- Bảng mapping đủ 33 feature, danh sách nguồn/semantics chưa đáp ứng và cách xử lý.
- Bridge có schema/version/provenance, tích hợp API/UI, hướng dẫn vận hành.
- Báo cáo parity từng feature/mask, 5 dòng/DN, model pins, kết quả âm tính kỹ
  thuật và hồi quy; tách kết quả local DN với HE thật/chưa hỗ trợ.
- Danh sách file sửa, ảnh hưởng fingerprint/model cũ và kế hoạch rollback.
  Thay đổi schema/contract phải theo quy trình spec v2.1, không sửa checksum để
  che thay đổi semantics. Không nhận R2 DONE hoặc accuracy chỉ từ dữ liệu mô phỏng.

Không deploy live, sửa bindings/model/khóa live hoặc push Git trong nhiệm vụ
xây bridge nếu chưa được giao triển khai riêng. Dữ liệu thử/model thử nằm trong
sandbox private; không đưa DB, credential, keys hoặc ciphertext context private
lên Git. Đọc các AGENTS.md áp dụng nếu đi vào vùng module agent khác.
