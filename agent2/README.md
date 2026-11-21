# Agent 2 · Soát xét Giao dịch & Kiểm soát Nội bộ

Phân hệ phát hiện giao dịch bất thường, kiểm tra tuân thủ quy trình phê duyệt và quản lý hồ sơ rà soát cho doanh nghiệp vừa và nhỏ.

## Kiến trúc 4 nhánh phân tích

1. **Luật nghiệp vụ (`sme_fraud/rules.py`, `rule_snapshot.py`)**: Bộ 35 quy tắc kiểm soát chi tiêu, tách hóa đơn né hạn mức, thanh toán trùng và lệch chuẩn hạch toán.
2. **Thống kê (`benford.py`, `score_statistics.py`)**: Kiểm định phân phối chữ số đầu Benford và điểm lệch chuẩn `RobustZ` theo lịch sử doanh nghiệp.
3. **Đồ thị quan hệ (`identity_graph.py`, `entity_graph.py`)**: Phát hiện liên kết vòng tròn hoặc dùng chung định danh/tài khoản giữa nhân sự và nhà cung cấp.
4. **Học máy không nhãn & Mã hóa đồng cấu (`ml_estimators.py`, `bundle_he.py`)**: Mô hình `Isolation Forest`, `ECOD`, `LOF`, `Autoencoder` ghim theo từng doanh nghiệp (`MethodStore`), hỗ trợ mở rộng chấm trên bản mã (HE).

## Chạy trong nền tảng chung (Khuyên dùng)

Từ thư mục gốc repo:

```powershell
.\run_web.ps1
```

- Agent 2 chạy tại cổng `8766` và kết nối qua cầu bảo mật của Portal tại `http://127.0.0.1:8800/#agent2`.
- Tệp giao dịch (`CSV`, `XLSX` hoặc `JSON` hợp đồng) có thể nạp ngay tại mục **Nạp dữ liệu chung** của Portal hoặc nạp bảng đa nguồn 35 luật trực tiếp trong giao diện Agent 2.

## Triển khai lên máy chủ Linux

Nhánh `deploy` chỉ giữ phần chạy thật của Agent 2 (`sme_fraud/`, `experiments/`) cùng công cụ thiết lập HE; bộ kiểm thử, các bản demo/benchmark và tài liệu nội bộ nằm ở nhánh `main`.

| Tệp | Dùng cho |
|---|---|
| `requirements-he.txt`, `requirements-he4-linux.txt` | Gói cài vào image Docker (`.he-venv`, gồm TenSEAL và Concrete) |
| `requirements.txt` | Cài môi trường cục bộ |
| `config/analysis-bindings.example.json` | Mẫu cấu hình gắn mô hình phân tích |
| `scripts/sync_portal_live_runtime.py` | Được `scripts/setup_he.py` gọi khi thiết lập HE lần đầu |
| `examples/full_rules/C001_B1_signal.json` | Được `data_pipeline/build_test_pack.py` chép vào bộ dữ liệu kiểm thử |
Xem [deploy/azure-vm/README.md](../deploy/azure-vm/README.md).
