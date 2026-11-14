# R0 — Kiểm kê và thu gọn Agent2

- spec_version: 2.1
- status: READY_FOR_REVIEW (chưa được người duyệt ghi DONE)
- Commit nguồn: `3cae5a3bba535694235179651b2e5daee8237656`; nhánh `platform-Khanh`; working tree cũ có thay đổi, diff hash `5e2f1a1206fc0a6c99c3522a8b023d504adc91df9fc811488a5cc33b31498d40`.
- Người thực hiện: Codex (trợ lý), ngày 10/11/2026. Không giả tên người phụ trách hoặc người duyệt.
- Chỉ đạo: người dùng yêu cầu gỡ dự án cũ, giữ luật cứng, thống kê/điểm, graph và ML không nhãn, đọc Agent2_Spec_v2_1. Ghi tại CR-004.

## Kết quả

Đã đưa bản Agent2 cũ ra `D:\agent22_legacy_20261110\agent2`; 3173 file ngoài môi trường .venv được kiểm tra nguyên checksum. Dữ liệu, model, phiếu rà, nhật ký, báo cáo cũ vẫn ở kho dự phòng; không còn trong runtime đang dùng. Môi trường .venv dùng lại để tránh cài lại. Các agent khác, portal, bộ spec và PDF gốc không bị dọn.

Lõi có 35 module Python gồm dependency/schema/fixture và trang trạng thái tạm. Luật/feature/đồ thị giữ nguyên mã; ECOD, IF, LOF, AE giữ thuật toán và điểm. Tách nguyên các hàm thống kê thuần; gỡ CatBoost và chọn model bằng tiêm mẫu. Trang trạng thái tạm không phải UI R5 và không nhận dữ liệu; API cũ trả 410.

Không có bộ xác suất gian lận đã calibration được xác minh. Giữ p-value, percentile/midrank, ngưỡng và anomaly score đúng nghĩa; không đổi tên thành probability.

## Bằng chứng

| ID | Bằng chứng | Kết quả |
| --- | --- | --- |
| R0-01 | inventory.csv, module_map.csv | Đủ 6 nhóm và map module logic |
| R0-02 | archive_verification.json, after_tests.log | Mã giữ có hash/IO/fit/effects; parity luật/feature exact, điểm float 1e-10 |
| R0-03 | baseline.json, before_tests.json, after_tests.json | 357 trước; 363 candidate; exit 0/skip 0 |
| R0-04 | state_migration.csv, source_audit.json | Nguồn DOCX đã đọc; không tự ánh xạ nhãn/kết luận |

Checker R0 là kiểm tài liệu/evidence, không phải tuyên bố R1–R6 đã pass. FLOW-01/02/04/06 có chứng cứ ở lõi; FLOW-03/05/07/08 not_testable vì chưa có các contract/integration v2.1 tương ứng. Không dựng test đỏ hoặc test xanh giả cho thành phần chưa tồn tại.

## Việc còn lại

- D-01: dữ kiện stack/runner/DB đã điều tra; Tech lead cần xác nhận và nhóm cần chỉ định người thật. Không tự ghi APPROVED.
- D-03/04/05/06/07/08/09/14: min history, fallback/weights, grouping/budget, mandatory route, target nhãn, release/checklist policy chưa chốt; chỉ chặn phần liên quan.
- D-10/18/19: nơi xử lý raw data, retention và staging/prod chưa chốt; không upload dữ liệu thật/khai production-ready.
- R1 chưa triển khai: validation/snapshot contract mới, tiền âm và allocation nhiều-nhiều cần kiểm theo catalog; không lấy việc giữ nguyên engine cũ làm bằng chứng hỗ trợ đầy đủ.
- R2 chưa triển khai MethodScore/unavailable/job/artifact registry. R3–R6 và TH1/TH2/HE chưa thực hiện.

## Kết thúc

Dừng tại R0 theo task card. Phần dọn theo chỉ đạo đã làm; pipeline mới chưa được phát hành. Tiến độ cao nhất READY_FOR_REVIEW; người được nhóm chỉ định mới ghi DONE.
