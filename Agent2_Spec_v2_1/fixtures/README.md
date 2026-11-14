# Fixture ownership

Các mẫu kèm là dữ liệu tổng hợp kiểm tra logic, không phải dữ liệu train/benchmark ML. R0 ghi hash, R1 tạo adapter/fixture bổ sung cho late-arrival, concurrency, tenant, refund/cancel/many-to-many theo test_catalog. Lưu ở fixtures/generated_v1/ và ghi owner/expected/provenance. Đóng băng trước chạy baseline/candidate. Thay đổi cần CR/version/hash mới; không sửa fixture sau test để làm xanh. Từng test case trong catalog phải có fixture ID và expected trong acceptance evidence.
