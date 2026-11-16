# Báo cáo nghiệm thu hiệu quả & khả năng phát hành luồng Agent2 theo Bundle

- **Run ID**: `r6-bundle-eval-20261116T061426Z`
- **Ngày tạo**: `2026-11-16T06:14:26.439991+00:00`
- **Môi trường**: Staging cô lập (`.runtime/bundle-e2e-acceptance-v1`), **dữ liệu mô phỏng**, **chưa deploy Portal live**, `he_execution = false`, `live_deployed = false`.

---

## 1. Bảng so sánh Chỉ 35 luật vs 35 luật + ML theo từng doanh nghiệp (Budget = 5 giao dịch/phương án/DN)

| Doanh nghiệp | Snapshot / Bundle A / Run A1 | Model ML ghim | Chọn 35 luật | Chọn 35 luật + ML | Hữu ích thêm | Không hữu ích thêm | Chưa đủ căn cứ thêm | Thời gian rà thêm (giây) | Thời gian chờ tài liệu (giây) | Nhãn gian lận xác minh |
|---|---|---|---|---|---|---|---|---|---|---|
| `C001` | `snp_26d3d13b00…` / `rbun_de03aeaef…` / `c001-bundle-a-k1` | `isolation_forest` | 3/5 (`C1_K1_01_P1A, C1_K1_02_P1B, C1_K1_03_C2`) | 5/5 (`C1_K1_01_P1A, C1_K1_02_P1B, C1_K1_03_C2, C1_K1_06_PAY, C1_K1_07_ML_ISSUE`) | 1 | 1 | 0 | 109.0 | 1800.0 | `None` (`human_declared_feedback_only`) |
| `C002` | `snp_c0ab0ac62c…` / `rbun_0833ce637…` / `c002-bundle-a-k1` | `ecod` | 4/5 (`C2_K1_01_A6, C2_K1_02_B1, C2_K1_03_B2, C2_K1_04_E2`) | 5/5 (`C2_K1_01_A6, C2_K1_02_B1, C2_K1_03_B2, C2_K1_04_E2, C2_K1_07_ML_INCONC`) | 1 | 0 | 1 | 38.0 | 3600.0 | `None` (`human_declared_feedback_only`) |

### Kiểm chứng biên kế hoạch so sánh đã khóa

- Giao dịch xuất hiện ở cả hai phương án chỉ rà **1 lần** rồi dùng chung kết quả (`shared_reviewed_once_ids`).
- `confirmed_risk` (*Có vấn đề cần xử lý*) **không** tự quy thành gian lận đã xác minh (`verified_fraud`).
- `inconclusive` (*Chưa đủ căn cứ*) được tách riêng khỏi mẫu số đúng/sai.
- **`C001` biên**: Đủ 5/5 từ luật -> ML thêm `0` (`budget_full_no_slots`); thiếu khả dụng (`3` < 5) -> chỉ chọn `3` (không padding); giao dịch lịch sử `C001_HIST_HIGH_CONTROL` bị loại khỏi ứng viên: `True`.
- **`C002` biên**: Đủ 5/5 từ luật -> ML thêm `0` (`budget_full_no_slots`); thiếu khả dụng (`3` < 5) -> chỉ chọn `3` (không padding); giao dịch lịch sử `C002_HIST_HIGH_CONTROL` bị loại khỏi ứng viên: `True`.

---

## 2. Báo cáo Fallback, Khả dụng nguồn và Backlog theo DN / Kỳ / Bundle

| DN | Kỳ | Khả dụng 35 luật (đủ/thiếu 1 phần) | Fallback khi mất ML (dùng phương án) | Chặn HE cloud | Tổng vụ | Tiếp nhận (`selected`) | Deferred (`budget`) | Backlog đầu kỳ | Phát sinh trong kỳ | Xử lý trong kỳ | Backlog cuối kỳ | Tuổi chờ max (giờ) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `C001` | `2026-W43` | 25/25 đủ (gap=0), stat=25/25, ml=25/25, graph=0/25 | 25/25 -> `fb_missing_unsup_rules_only_v1` (null!=0=True) | `True` | 16 | 3 | 6 | 0 | 13 | 0 | 13 | 0.0 |
| `C002` | `2026-W43` | 25/25 đủ (gap=0), stat=25/25, ml=25/25, graph=0/25 | 25/25 -> `fb_missing_unsup_rules_only_v1` (null!=0=True) | `True` | 22 | 3 | 18 | 0 | 19 | 0 | 19 | 0.0 |

### Kiểm chứng snapshot thiếu một phần nguồn (`missing_source_probe`)

- **`C001`** (bỏ `vendor_status_history, payroll_entitlements`): `25/25` dòng báo thiếu nguồn một phần, các luật unavailable `B4, E1` giữ nguyên `null` (`keep_null=True`), các nhánh còn lại vẫn chấm đủ `25` dòng.
- **`C002`** (bỏ `vendor_status_history, payroll_entitlements`): `25/25` dòng báo thiếu nguồn một phần, các luật unavailable `B4, E1` giữ nguyên `null` (`keep_null=True`), các nhánh còn lại vẫn chấm đủ `25` dòng.

### Đề xuất tách biệt để người phụ trách chốt ngân sách hàng đợi cấp vụ

- Gioi han 5 giao dich/phuong an/DN chi dung cho phep so sanh 35 luat vs ML; KHONG phai ngan sach vu viec san xuat.
- Thời gian rà trung bình quan sát trên fixture: `46.5 giây/vụ`.
- **`D-07` (Don vi ky & han muc vu/ky theo DN)**: calendar_week_vn; muc thu staging hien la 3 vu/tuan (~15-30 phut ra thuc te khi 1 vu co 1-3 giao dich); can chot theo so gio ke toan DN bo tri hang tuan.
- **`D-04 / D-05 / D-06` (Nguong xet duyet & dieu kien mo lai vu)**: Chot nguong diem ML/rules toi thieu de khong day vu nhiễu vao queue; giu mandatory_routing cho hard_trigger co du nguon.
- **`Backlog Policy` (Chinh sach ton dong & tuoi cho)**: Khong tu xoa backlog; qua tuoi cho 14-30 ngay can canh bao qua han va cho phep dong hang loat co ly do hoac tai danh gia ky moi.

---

## 3. Biên bản thử nghiệm Rollback toàn luồng trên Staging (`Bundle A → In-flight A → Bundle B → Rollback về A`)

| DN | Bundle A (`bundle_id`) | Bundle B (`bundle_id`) | Run dở (`in-flight A`) giữ đúng A? | Run K2 trên B đọc nguyên nguồn? | Run sau Rollback (`A2`) dùng A? | Phiếu / Task / Chứng từ / Audit B còn nguyên? | Quota / Backlog / Dedup không reset? | Retry + Reload + Restart không trùng? |
|---|---|---|---|---|---|---|---|---|
| `C001` | `rbun_de03aeaef…` | `rbun_aab52224c…` | `True` (`c001-inflight-a`) | `True` (`c001-bundle-b-k2`) | `True` (`c001-bundle-a-after-rollback`) | rev=1, task=`tsk_6af3674be7e4f32cb8ddfed0`, shaOK=`True`, audits=3 | `True` (active=0) | `True` (`no_db_restore=True`) |
| `C002` | `rbun_0833ce637…` | `rbun_43c87bc96…` | `True` (`c002-inflight-a`) | `True` (`c002-bundle-b-k2`) | `True` (`c002-bundle-a-after-rollback`) | rev=1, task=`tsk_e06fdaa2f40a858f1e5cfac4`, shaOK=`True`, audits=3 | `True` (active=0) | `True` (`no_db_restore=True`) |

- Cô lập chéo doanh nghiệp `C001` / `C002`: **`True`**.

---

## 4. Kết luận nghiệm thu tách biệt 3 phần

1. **Đạt kỹ thuật trên staging**: **`DAT_KY_THUAT_STAGING`** — Enterprise-local shadow pipeline tren moi truong staging co lap, du lieu mo phong.
2. **Đủ bằng chứng hiệu quả phát hiện gian lận thật hay chưa**: **`CHUA_DU_BANG_CHUNG_HIEU_QUA_THUC_TE`** — Toan bo du lieu va phan hoi danh gia la du lieu mo phong; chua co nhan gian lan da xac minh (ReviewLabel) tren doanh nghiep that cho tap kiem thu.
3. **Đủ điều kiện phát hành production hay còn bị chặn**: **`BI_CHAN_BLOCKED`** (`approved_for_production=False`)

### Các cổng đang chặn phát hành production / active:

- **`OPEN_GOVERNANCE_DECISIONS`**: Con cac quyet dinh chu so huu chua chot: D-04, D-05, D-06, D-07, D-09, D-14, D-17, D-18, D-19.
- **`MISSING_REAL_VERIFIED_LABELS`**: Chua co bo nhan ReviewLabel da xac minh tren du lieu doanh nghiep that de dat gate D-09.
- **`CASE_BUDGET_AND_SLA_NOT_APPROVED`**: Ngan sach hang doi cap vu (B=3 staging), mandatory routing va SLA xu ly ton dong chua duoc phe duyet cho production.
- **`CLOUD_HE_EXECUTOR_UNAVAILABLE`**: Bundle executor hien chay enterprise_local_only (he_execution=false); chua noi full cloud HE va chua thu nghiem HE END-TO-END cho bundle.
- **`SHARED_PORTAL_IDENTITY`**: Portal dung chung tai khoan workspace, chua xac minh danh tinh ca nhan nguoi rà/phe duyet doc lap.
- **`NOT_DEPLOYED_LIVE`**: Chua thuc hien quy trinh rollout/backup tren he thong Portal live.

*Chi tiết JSON đầy đủ nằm tại thư mục `Agent2_Spec_v2_1/evidence/R6/bundle_release_eval_20261116`.*
