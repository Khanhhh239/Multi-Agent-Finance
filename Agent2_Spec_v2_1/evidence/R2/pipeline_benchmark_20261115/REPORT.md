# CR-058 — kiểm thử lại và benchmark chung

READY_FOR_REVIEW kỹ thuật. [Báo cáo đối chiếu pipeline](../../../../reports/pipeline_recheck_20261115.md)
và [hướng dẫn API/CLI](../../../../agent2/docs/PIPELINE_BENCHMARK.md).

`checks.json` ghi phạm vi và giới hạn; `tests.json` hợp nhất test ID, không cộng
lặp lượt chạy; `browser_checks.json` chứa9 nhóm nghiệm thu cô lập. Source hash
PDF gốc và code hiện tại trong `source_hashes.json`.

Lượt này dùng model HE đã train trước để chấm local shadow; không train HE lại,
không chấm HE cloud mới hoặc thay live. Fixture kiểm crypto vòng đời và model
demo không phải nhãn gian lận thật. Không có khóa, token hoặc ciphertext trong
evidence công khai. Chưa phê duyệt ensemble, quality gate hay active delivery.
