# WP-D · Dữ liệu — vector hoá máy phát, hard case, sinh lớn, dữ liệu thật bổ sung

> **Hồ sơ kế hoạch từ 15/10/2026.** Các trạng thái, lệnh và danh sách việc dưới đây phản ánh thời điểm lập; đọc [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md) trước khi dùng.

Tham chiếu: 02_Data/04–07. Mã: `agent1/synth/world.py`, `scripts/build_worlds.py`, `agent1/synth/fidelity.py`.

---

## WP-D1 · Vector hoá và tối ưu máy phát (P1, cần trước khi sinh lớn)

1. **Đo trước**: `python -X importtime` không cần; dùng `cProfile` trên `World.run()` với 6 công ty; liệt kê hàm chiếm >5% thời gian.
2. **Vector hoá**:
   - `bank_ledger`: thay vòng `for g, sub in p.groupby("grp")` bằng: sắp xếp, gán `txn_idx` theo nhóm (`groupby.ngroup()`), tổng tiền bằng `bincount`, và sinh `memo` theo lô bằng `np.vectorize` nhỏ hoặc xây trước bảng mẫu; chỉ phần chuỗi (memo, tên) còn Python.
   - `promises`: vector hoá theo từng mốc kiểm tra (7/21/45/75) thay vòng `for k in cand`.
   - `outflows`: tách tính VAT bằng `resample` (đã) và vòng lặp tuần (13 lần/năm) chấp nhận được.
3. **Tính tái lập**: sau tối ưu, kết quả phải **giống hệt** với cùng seed (so hash parquet) hoặc ghi rõ lý do khác biệt.
4. **Kiểu dữ liệu**: `payday` hỗn hợp int/'eom' (L15) → luôn chuỗi (`"5"`, `"eom"`); cập nhật `calendar_vn.obligation_schedule` tương ứng.
5. **Đo tốc độ**: bảng thời gian vs số HĐ (10k, 100k, 1M) vào `docs/02_Data/06`.
- **Tiêu chí**: ≥5× nhanh hơn ở 1M HĐ; kết quả giống seed.

## WP-D2 · Hard-case worlds (P0/P1)

Thêm cờ vào `WorldConfig` và sinh `hc_*` (12 công ty × 7 năm mỗi cái). Mỗi cờ bật **đúng một** hard case, các phần khác như `src`.

| WP | Cờ / thế giới | Việc | Nhãn bổ sung | Đo |
|---|---|---|---|---|
| D2.1 | `hc_lumpy_customer` | 1 khách chiếm 40–60% doanh thu (Pareto α=1,0 + ép khách đầu) | `customers.is_anchor` | độ phủ khi khách lớn trễ/vỡ nợ |
| D2.2 | `hc_group_payer` | người trả ≠ khách (nhóm công ty): `payer_group` | `bank_txns.payer_group_id` | T9 liên kết |
| D2.3 | `hc_heterogeneity` | tăng dị biệt khách: phương sai trễ do danh tính khách ≈0,6 (L13) bằng phân phối `late_med` rộng hơn & `ontime_base ~ Beta(0.8,0.8)` | — | cải thiện lợi ích đặc trưng khách |
| D2.4 | `hc_cod_realistic` | giảm COD theo số lượng về 20–30% | — | tỷ trọng bán chịu theo số lượng |
| D2.5 | `hc_discount_early` | điều khoản 2/10 net 30: 25% khách trả sớm ngày 10 | `invoices.discount_taken` | T1 hồi quy sớm |
| D2.6 | `hc_retention` | giữ lại bảo hành 5% trả sau 24 tháng (xây dựng) | `retention_amount, retention_due` | đuôi, T6 |
| D2.7 | `hc_fx` | 15% HĐ bằng USD, tỷ giá ngày | `currency, fx_rate` | quy đổi, lãi lỗ tỷ giá |
| D2.8 | `hc_credit_note` | HĐ điều chỉnh/thay thế/huỷ (TT78): chuỗi điều chỉnh | `invoices.adjusts_invoice_id` | T0 cổng, T3 |
| D2.9 | `hc_verbal` | 15% khách có "thoả thuận miệng" khất nợ không ghi; chỉ lộ ở kết quả | `invoices.verbal_extension_days` | T7 phát hiện, T8 giá trị ghi thêm |
| D2.10 | `hc_supply_shock` | gián đoạn chuỗi cung ứng cục bộ theo ngành 8 tuần | `events` | T6/T7 |
| D2.11 | `hc_seasonal_extreme` | doanh thu tập trung 60% vào 4 tháng | — | T4/T6 |
| D2.12 | `hc_new_company` | công ty mới ≤12 tháng lịch sử | — | cold start |

Cách làm: mỗi hard case = 1 hàm trong `world.py` được bật bởi cờ; không đổi RNG của các phần khác (dùng `rng.spawn` cho từng hard case để các kết quả chung không đổi khi bật/tắt).
- **Kiểm**: `validate_world` + `fidelity.report`; mô tả tác động (biến nào đổi) trong `docs/02_Data/05_hard_cases.md` (đổi trạng thái ✅).

## WP-D3 · Sinh quy mô lớn và kiểm định bằng C2ST (P1)

1. **Kế hoạch**: 20 thế giới `dr_*` (WP-3.3) + 4 thế giới lớn `big_*` (100–200 công ty, 3–6M HĐ). Dung lượng ~0,5–1 GB.
2. **Tạo** `scripts/build_big.py`: chạy song song (`concurrent.futures.ProcessPoolExecutor`, ≤4 tiến trình), mỗi tiến trình `AGENT1_THREADS=2`; tiến độ vào `outputs/build_big.log`.
3. **C2ST** (Classifier two-sample test): `agent1/synth/c2st.py` — huấn luyện LightGBM phân biệt hoá đơn thật (Customer Invoices) và tổng hợp (cùng đặc trưng quan sát được: ngày, số tiền tương đối, hạn, thứ trong tuần, khoảng đáo hạn, trễ…); báo cáo AUC (0,5 = không phân biệt). Mục tiêu: AUC <0,75 trên đặc trưng cấu trúc; liệt kê đặc trưng phân biệt mạnh nhất để sửa máy phát.
4. **Kiểm định marginal** (KS/Wasserstein) với UK PPR (nhóm 30/31–60/60+) *khi chưa dùng chỉnh*; Atradius chỉ để kiểm chạy đúng.
5. **Kiểm tra độc lập thêm**: DSO theo ngành so với BCTC niêm yết VN (WP-D4.4) — không dùng để chỉnh.
- **Tiêu chí**: C2ST AUC báo cáo; 0 lỗi `validate_world`; marginal trong dung sai 3 điểm phần trăm (trừ thế giới cố ý lệch).

## WP-D4 · Dữ liệu thật bổ sung (P1; cần đăng nhập/điều khoản — hỏi người giao việc nếu bị chặn)

| WP | Nguồn | Việc | Ghi chú |
|---|---|---|---|
| D4.1 | Home Credit `installments_payments` (Kaggle) | `real_loaders.home_credit_installments()`; chuẩn hoá `DAYS_*` → ngày tương đối; dùng cho T1/T3 | cần `kaggle` CLI + chấp nhận luật cuộc thi; đọc điều khoản dùng ngoài cuộc thi |
| D4.2 | M5 | tái lập WSPL của LightGBM đa chân trời ⇒ xác nhận quy trình T4 | Kaggle login |
| D4.3 | SEC FSDS | df Student-t (WP-6.4) | cần User-Agent của chính bạn |
| D4.4 | BCTC niêm yết VN (vnstock / UBCKNN) | DSO, DPO theo ngành để kiểm tra độc lập | đọc điều khoản trước; vnstock giới hạn tốc độ |
| D4.5 | UNU-WIDER, Tổng điều tra kinh tế 2026 | phân bố quy mô SME → thay giả định logNormal(40 tỷ) | điền biểu mẫu/tải số |
| D4.6 | Payment Times Úc | tải tay; đối chiếu họ phân phối trễ | chấp nhận Terms |
| D4.7 | Khảo sát 5–10 văn phòng kế toán (không phải mã) | tỷ lệ ghi sổ lô, FIFO sai, nội dung CK, nhập tay | tạo form + hướng dẫn phỏng vấn trong `docs/02_Data/survey_accounting.md` |

Mỗi nguồn thêm vào `scripts/crawl.py` (khoá mới) + `MANIFEST.json` + một mục ở `docs/02_Data/02` (nếu dùng) hoặc `03` (nếu loại).

## WP-D5 · Bộ đánh giá niêm phong
- Sinh `tgt2` (seed mới) khi cần kiểm thử cuối; **chỉ chạy một lần** cho báo cáo cuối; lưu hash.
- Lưu mọi `config.json` vào `docs/02_Data/worlds_registry.csv` (tên, seed, hash, ngày, mục đích).

**DoD WP-D**: máy phát nhanh ≥5×; 12 `hc_*`; ≥24 thế giới đa dạng; C2ST + marginal có báo cáo; tối thiểu D4.1, D4.3, D4.4 xong (nếu truy cập được).
