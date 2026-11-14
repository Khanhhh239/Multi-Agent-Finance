# Pipeline Agent 1 đầu-cuối

Mô tả mã Workspace hiện tại, đối chiếu 14/11/2026. Kỳ dự báo cho phép 1–52 tuần, mặc định 13; cửa sổ đánh giá/chọn T1 hiện là 13 tuần. Chọn kỳ dài hơn trên giao diện chưa chứng minh chất lượng ở kỳ đó.

## Dòng dữ liệu

```text
CSV / Excel / XML
        ↓
T0: ghép cột → kiểm tra → xem trước → xác nhận lưu
        ↓
Kho doanh nghiệp: bản ghi + phiên bản + nguồn + ngày biết
        ↓
T9: đề xuất → người dùng duyệt/từ chối/đảo → công nợ quan sát
        ↓
Snapshot tại cutoff + phạm vi thanh toán/tài khoản đã xác nhận
        ├─ Cập nhật: global → học tiếp → validation → audit → registry
        │                                      └─ challenger chờ nhãn nếu cần
        └─ Dự báo: bundle đã sẵn sàng / global fallback
                         ↓
              T1 PMF tất toán + adapter partial
                         ↓
       T6: công nợ + T5 còn lại + hoạt động nếu bật/đủ điều kiện
                         ↓
        Kỳ vọng, P50, P10/P90 và xác suất thiếu tiền
                         ↓
     Lưu forecast + artifact + dữ liệu + engine/runtime cùng phiên bản
                         ↓
       T10 / hàng đợi ưu tiên / kịch bản / Excel, JSON
                         ↓
      Tiền thực tế đủ phạm vi → chấm → hiệu chỉnh đủ điều kiện
```

## Nạp, học và dự báo là ba thao tác riêng

**Nạp/đối soát** thay dataset và công nợ kể từ ngày thông tin được biết; không tự fit T1. T9 chỉ ghi phân bổ sau duyệt, giữ giao dịch bank và lịch sử khi đảo. Thiếu vài nghìn đồng không tự thành phí hoặc xóa nợ.

**Cập nhật bundle** chạy qua API/worker hoặc job được scheduler gọi. Mỗi chu kỳ khởi tạo học tiếp từ global gốc trên cửa sổ trượt, chọn một cấu hình bằng validation rồi audit. Thiếu nhãn hoặc không đạt thì giữ T1/partial hiện tại; risk/operating vẫn được làm mới theo quy trình chung. Đủ lịch không có nghĩa chắc chắn đổi model.

**Dự báo** chụp dataset, payment coverage và bundle trong cùng giao dịch đọc SQLite rồi kết thúc giao dịch trước mô phỏng. Không fit trong `/v1/predict`. Mọi thành phần được dùng phải học và sẵn sàng không sau cutoff; operating bị tắt không chặn dự báo AR. Import/kích hoạt song song không ghép dữ liệu từ hai snapshot vào một forecast.

## Vai trò từng khối

| Khối | Đầu ra/hợp đồng |
|---|---|
| [T0/T9](02_t0_t9_du_lieu_va_doi_soat.md) | Dữ liệu kiểm tra được, quyết định có nguồn, dư nợ theo ngày biết |
| [T1 + partial](T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md) | PMF tất toán và xác suất/tỷ lệ trả một phần, chọn/lưu cùng bundle |
| [T5/hoạt động](04_t4_t5_thu_moi_va_chi.md) | Phần nghĩa vụ chưa trả/nhận, phạm vi chi và dòng hoạt động bổ sung |
| [T6](T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) | Chuỗi tiền nhiều lần thu, số dư và xác suất dưới ngưỡng |
| [T10](T10_BUNDLE_EVIDENCE_2026-11-13.md) | Bằng chứng đã lưu, giải thích, phân rã và kịch bản cùng phiên bản |

T2/risk phục vụ thông tin riêng, không nhân giảm dòng thu thêm một lần. T7, T8 và T4 trong pipeline nghiên cứu cũ không tự trở thành bộ điều khiển khủng hoảng, chat/Zalo hoặc doanh thu mới đang bật trong Workspace. Hành động/lời hứa được nạp có cấu trúc; luồng giải thích hiện dùng bảng/template.

## Truy vết và điểm vào mã

| Mã | Vai trò |
|---|---|
| [workspace/api.py](../../agent1_service/workspace/api.py) | API, snapshot nhất quán, lưu forecast/replay và export |
| [adaptive/data.py](../../agent1/adaptive/data.py), [workspace/reconciliation.py](../../agent1_service/workspace/reconciliation.py) | Hợp đồng nạp, ngày biết, T9 và công nợ |
| [t1_catalog.py](../../agent1/adaptive/t1_catalog.py), [t1_data.py](../../agent1/adaptive/t1_data.py), [t1_update.py](../../agent1/adaptive/t1_update.py) | Catalog, landmark/nhãn, học/chọn/audit |
| [workspace/t1_lifecycle.py](../../agent1_service/workspace/t1_lifecycle.py) | Registry, chu kỳ và challenger từng doanh nghiệp |
| [methods.py](../../agent1/adaptive/methods.py), [cash_adapter.py](../../agent1/adaptive/cash_adapter.py) | Huấn luyện bundle và dự báo nhiều lần thu |
| [cash_history.py](../../agent1/adaptive/cash_history.py), [t10_explanations.py](../../agent1/adaptive/t10_explanations.py) | Đối chiếu/hiệu chỉnh và giải thích/replay |

Đổi active hoặc nạp dữ liệu không sửa forecast cũ. `company_bundle_version` xác định registry doanh nghiệp; `model_version` xác định tham số T1 + partial. Không xóa registry đang phục vụ hoặc được forecast tham chiếu. Replay kiểm cả source/runtime; khác phiên bản phải phục hồi đúng môi trường hoặc lập forecast mới.

Kiểm thử chức năng và nghiệm thu dự báo là hai loại bằng chứng riêng; đọc [quy tắc nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md). Luồng này không tự thanh toán, gửi tin cho khách hoặc mở pilot thật.
