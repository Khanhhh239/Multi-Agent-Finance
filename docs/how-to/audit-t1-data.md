# Tải và audit dữ liệu Séc cho T1

Chạy từ gốc repo. Chuẩn bị Python và dependency theo [Getting started](../getting-started.md). Nội dung và mục đích hai nguồn nằm tại [data/T1 README](../../data/T1/README.md).

## Audit snapshot đã có

```powershell
python scripts/data_audit/audit_czech_t1_datasets.py --snapshot 2026-10-18
```

Script cần manifest hoàn tất và toàn bộ file raw của snapshot. Nó kiểm tra hash nguồn, đọc dòng hóa đơn tổng của Bộ Tài chính và toàn bộ trang hóa đơn y tế, rồi ghi:

- `data/T1/interim/czech/<snapshot>/`: hai bảng invoice audit, bảng coverage theo tháng và bảng theo tổ chức y tế.
- `research/references/data-checks/t1/czech_t1_full_audit.json`: thống kê của **lần audit vừa chạy**, ghi đè file cùng tên.

Nếu so sánh nhiều snapshot, giữ riêng kết quả JSON trước khi chạy lần khác và ghi snapshot trong báo cáo. Bảng audit giữ flag chất lượng; script không train, impute hoặc tự dedup thành tập train.

## Tải một snapshot mới

```powershell
python scripts/data_download/download_czech_t1_datasets.py --snapshot YYYY-MM-DD --workers 3
python scripts/data_audit/audit_czech_t1_datasets.py --snapshot YYYY-MM-DD
```

Thay `YYYY-MM-DD` bằng ngày tải thực tế. Dùng thư mục ngày mới khi lấy phiên bản nguồn mới: tên snapshot là ngày thu thập, **không phải truy vấn trạng thái quá khứ của API**. Lệnh tải dùng mạng, ghi raw và manifest tại `data/T1/raw/czech/<snapshot>/`.

Downloader tiếp tục trang đã tải dựa trên cache/metadata; không coi đó là cơ chế khóa phiên bản nguồn. Kiểm tra `complete`, count, hash và flag thay đổi nguồn trong manifest. Kiểm tra trước/sau không bảo đảm API được chụp trong một transaction nguyên tử.

## Audit mẫu BPI/DC

```powershell
python scripts/data_audit/audit_t1_source_samples.py
```

Lệnh chỉ xử lý mẫu có trên máy, ghi đè `research/references/data-checks/t1/t1_dataset_sample_profiles.json`. Profile hiện có còn ghi lịch sử mẫu Séc đã dọn, nên không chạy chỉ để kiểm tra cú pháp/link; khi chạy lại phải ghi rõ thay đổi phạm vi. Mẫu BPI là prefix XES; mẫu DC không phải mẫu ngẫu nhiên hay toàn bộ dữ liệu.

## Kết thúc kiểm tra

Đối chiếu manifest và lỗi/gate, không chỉ số dòng. Nếu đổi nguồn hoặc quy tắc audit, cập nhật tài liệu và bằng chứng theo [Contributing](../CONTRIBUTING.md). Raw/interim được ignore; không ép đưa dữ liệu lớn vào Git.
