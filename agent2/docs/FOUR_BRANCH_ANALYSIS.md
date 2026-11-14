# Bốn nhánh phân tích snapshot — CR-027

Mở **http://127.0.0.1:8800/#agent2**, dùng phiên Portal đã được cấp quyền, nhập/kiểm tra/lưu JSON rồi bấm **Xem kết quả kiểm tra**. Kết quả có bốn phần theo doanh nghiệp và từng giao dịch:

| Nhánh | Đang làm gì? | Khi thiếu điều kiện |
|---|---|---|
| Luật nghiệp vụ | P1 đối chiếu phân bổ/hóa đơn và E3 tên NCC bằng evaluator đã nối. Hiện độ phủ canonical vẫn một phần; có bộ đếm đã chạy/không áp dụng/chưa khả dụng. | Thiếu nguồn hoặc chưa có evaluator giữ unavailable, không coi là không vi phạm. Chưa có điểm tổng đầy đủ. |
| So sánh thống kê | Dùng thống kê RobustZ và phân phối tham chiếu đã fit riêng cho DN. | Thiếu phiên bản/reference/đầu vào phù hợp thì chưa khả dụng. |
| Quan hệ đối tượng | Đọc quan hệ đã biết tại cutoff, hiển thị đối tượng, liên kết, căn cứ và bối cảnh yếu. Chọn nút trong sơ đồ để đọc tên/mã nguồn. | Thiếu đối tượng hoặc định danh thì báo thiếu; không tự nối tài khoản chỉ vì giống chữ số. Không có điểm rủi ro đồ thị. |
| Phân tích bất thường | Chấm bằng phiên bản ML không nhãn được ghim cho DN: IF, ECOD, LOF hoặc Autoencoder hiện có. | Không có model được chỉ định, sai feature/phiên bản/thời gian hoặc nguồn thiếu thì chưa khả dụng; không tự fit. |

Mở từng phần trong giao dịch để xem chi tiết. Vị trí tương đối **0–100** là vị trí so với tập đối chiếu, **không phải xác suất sai phạm** hoặc ngưỡng cảnh báo. Điểm 0 vẫn là kết quả khả dụng. Nhãn **Phân tích hồi cứu** cho biết đây là backtest; không chứng minh model từng được triển khai tại ngày giao dịch.

Thẻ “Cần đối chiếu theo luật” hiện chỉ đếm hai đối chiếu hóa đơn/tên NCC. Các nhánh khác được trình bày riêng; không tự tăng trọng số, cộng thành tổng, chọn ngưỡng hoặc đưa ML/đồ thị vào hàng đợi. Nguồn thiếu của snapshot được giữ trên màn hình kết quả; bộ đếm hai đối chiếu không thay cho độ phủ cả bốn nhánh.

## Chỉ định model phía server

Không chọn thuật toán hoặc gửi artifact từ browser. Người vận hành dùng **job fit riêng** trong [COMPANY_MODEL_JOBS.md](COMPANY_MODEL_JOBS.md), có quyền `model.fit` và `data.import`, dữ liệu history/reference kết thúc trước kỳ đánh giá. Inference chỉ cần quyền đọc/import hiện hành, không cần `model.fit`.

Sau job thành công, lấy `job.artifact_id` từ receipt và ghim ID bất biến trong file theo mẫu `config/analysis-bindings.example.json`:

```json
{
  "version": "analysis-bindings/1.0.0",
  "bindings": [
    {
      "tenant_id": "YOUR_TENANT",
      "company_id": "YOUR_COMPANY",
      "statistics_artifact_id": null,
      "ml_artifacts": {}
    }
  ]
}
```

Thay `statistics_artifact_id` bằng ID `mth_<64 hex>` của **robust_z** đã fit, khi có. Ví dụ `ml_artifacts` là `{"ecod": "mth_<ID_THAT_DA_FIT>"}` hoặc `{"isolation_forest": "mth_<ID_THAT_DA_FIT>"}`. Các ký hiệu trong `<...>` là hướng dẫn, không phải ID hợp lệ. Không tự lấy model mới nhất, dùng ID của DN khác hoặc artifact legacy khác contract. Có thể ghim nhiều lựa chọn, UI giữ riêng kết quả khả dụng và chưa khả dụng.

File chỉ do người vận hành đáng tin cậy sửa; `company.json` và quyền director trong browser không tự cấp quyền sửa file. Đây là binding cho chấm chẩn đoán, **không phải active bundle đã qua release gate**. Không có file/mapping thì trả thiếu phiên bản; không tự tìm model trong thư mục khác.

Portal mới nhận cấu hình `agents.agent2.model_db` và `agents.agent2.analysis_bindings`, truyền vào backend:

```powershell
& .venv/Scripts/python.exe -X utf8 -B start_review.py --port 8766 --snapshot-db <snapshots.sqlite3> --model-db <models.sqlite3> --analysis-bindings <bindings.json> --portal-url http://127.0.0.1:8800
```

Lệnh này cần secret bridge do Portal cung cấp qua environment; người dùng thường bật Agent2 từ Portal. Không chép secret vào câu lệnh. Với Portal launcher đang chạy chưa có hai tham số mới, backend mode Portal mặc định đọc `models-v2.sqlite3` và `analysis-bindings.json` cạnh snapshot DB. Đây là hai tên tệp cố định, không quét/chọn model tự động; thiếu file không tạo DB hoặc fit model.

ModelStore được mở **read-only sau khi kiểm quyền**. Model dùng đúng tenant/DN, checksum, phiên bản runtime/feature/tiền xử lý, thời gian reference và kỳ đánh giá. Giao dịch đã ở tập fit/reference không được trình bày như ngoài mẫu. Thay mapping trong lúc phân tích làm yêu cầu trả 409 để chạy lại; dùng thay thế file nguyên tử khi cập nhật. Hỏng/thiếu model chỉ làm nhánh liên quan chưa khả dụng; thu hồi quyền vẫn chặn toàn kết quả.

## API và giới hạn

`POST /api/v1/companies/{company}/snapshots/{snapshot}/analyze` giữ body `{as_of, view?}`. Contract tăng lên **snapshot-analysis/1.1.0**:

- Giữ `checks`/`groups` P1/E3; thêm `rows[].branches` luôn đủ bốn nhánh, `branch_summary`, `source_limits` và `analysis_context_id`.
- DTO review chỉ có trường nghiệp vụ, quan hệ/căn cứ, trạng thái và vị trí tương đối. Tên algorithm, predictor, raw score và ID/config model không gửi cho kế toán.
- Director đúng DN mới được view technical: thêm `methods`, `graph_evidence`, `rule_coverage` và binding metadata. Hai view dùng cùng phép tính và cùng analysis_id.
- analysis_id gắn snapshot/as_of/code/runtime/binding/artifact thực đọc, thay model hoặc tình trạng model khả dụng làm ID thay đổi. Không lưu job kết quả hoặc ghi queue.
- Giữ giới hạn 200 transaction records/1.000 source records/5 MiB response; không cắt dòng/lịch sử. Source limits là các record đã biết tại as_of toàn yêu cầu; feature/graph từng dòng vẫn dùng cutoff riêng.

Các kernel, bộ feature 33 cột, thang điểm cũ và schema MethodScore/RuleResult không đổi. Chưa nối evaluator cho toàn bộ 35 luật, chưa xác nhận độ chính xác hoặc nghiệm thu production/full R2/R5. BR-026-01 về khoản thanh toán đầu vượt hóa đơn vẫn là quyết định nghiệp vụ cần chốt.

## Demo và kiểm thử

Demo tạo dữ liệu/phiên/DB tạm, fit bốn artifact bằng job riêng trước khi mở trình duyệt (RobustZ + IF cho C001, RobustZ + ECOD cho C002), bỏ quyền fit của người dùng, rồi đi qua UI Portal thật. Các spy chặn fit/write trong toàn bộ phase phân tích:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_four_branch_analysis.py --output-dir <thu-muc-moi>
```

Nguồn mô phỏng, không dùng nhãn và không chứng minh accuracy. Các model/profile demo không tự chuyển sang dữ liệu live. Bộ test `test_four_branch_analysis.py` kiểm đủ 5 dòng dù không trúng luật, bốn lựa chọn ML, ghim sai DN/tenant/feature/runtime, model tương lai/overlap, nguồn thiếu, không fit/write, reference đóng băng và thay binding giữa request.
