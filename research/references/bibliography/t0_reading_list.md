# Paper cho T0: nền dữ liệu, lịch sử và đối soát

Chọn lọc và kiểm tra ngày **18/10/2026** để phục vụ [bản đánh giá T0](../../../docs/reports/t0-method-review.md). Tám PDF đã được tải nguyên bản từ nguồn công khai; [manifest](../papers/t0/manifest.json) ghi URL, phiên bản, số trang, dung lượng và SHA-256. [BibTeX](t0_references.bib) dùng để trích dẫn.

## Danh mục

| Mã | Paper / bản PDF trong repo | Tác giả, năm và loại nguồn | Nguồn gốc |
|---|---|---|---|
| R1 | [Lakehouse: A New Generation of Open Platforms that Unify Data Warehousing and Advanced Analytics](../papers/t0/2021_lakehouse_open_platforms.pdf) | Armbrust, Ghodsi, Xin, Zaharia; CIDR 2021 | [Trang hội nghị](https://www.vldb.org/cidrdb/2021/lakehouse-a-new-generation-of-open-platforms-that-unify-data-warehousing-and-advanced-analytics.html); PDF từ trang tác giả Stanford |
| R2 | [Delta Lake: High-Performance ACID Table Storage over Cloud Object Stores](../papers/t0/2020_delta_lake_acid_storage.pdf) | Armbrust và cộng sự; PVLDB 2020 | [Bản nhà xuất bản](https://www.vldb.org/pvldb/vol13/p3411-armbrust.pdf) |
| R3 | [Temporal Features in SQL:2011](../papers/t0/2012_temporal_features_sql2011.pdf) | Kulkarni và Michels; SIGMOD Record 2012, Industry Perspectives | [Trang SIGMOD Record](https://sigmodrecord.org/2012/09/30/temporal-features-in-sql2011/) |
| R4 | [Automating Large-Scale Data Quality Verification](../papers/t0/2018_automating_data_quality_verification.pdf) | Schelter và cộng sự; PVLDB 2018 | [Bản nhà xuất bản](https://www.vldb.org/pvldb/vol11/p1781-schelter.pdf) |
| R5 | [Deep Entity Matching with Pre-Trained Language Models — Ditto](../papers/t0/2020_ditto_deep_entity_matching.pdf) | Li và cộng sự; công trình PVLDB, bản tác giả arXiv v3 năm 2020 | [arXiv:2004.00584v3](https://arxiv.org/abs/2004.00584v3) |
| R6 | [Match, Compare, or Select? An Investigation of Large Language Models for Entity Matching](../papers/t0/2025_match_compare_select_entity_matching.pdf) | Wang và cộng sự; COLING 2025 | [ACL Anthology](https://aclanthology.org/2025.coling-main.8/) |
| R7 | [The Subset Sum Matching Problem](../papers/t0/2025_subset_sum_matching_problem.pdf) | Wu và cộng sự; bản mở rộng arXiv 2025, tác giả ghi được nhận tại ECAI 2025 | [arXiv:2508.19218v1](https://arxiv.org/abs/2508.19218v1) |
| R8 | [Labeling Training Data for Entity Matching Using Large Language Models](../papers/t0/2026_llm_labeling_entity_matching_v2.pdf) | Steiner và Bizer; **preprint**, v2 sửa ngày 05/10/2026 | [arXiv:2606.28823v2](https://arxiv.org/abs/2606.28823v2) |

## Đọc gì và dùng đến đâu?

**R3 — đọc đầu tiên, phần 2.4 về bitemporal.** Paper phân biệt thời gian có hiệu lực với thời gian trạng thái được ghi nhận trong database. Áp dụng cho T0 bằng cách mô hình hóa cả hiệu lực nghiệp vụ và lúc thông tin dùng được. Việc ánh xạ system time sang availability của pipeline phải được thiết kế riêng; paper không tự biết độ trễ API/validation của dự án.

**R7 — đọc tiếp, nhất là định nghĩa bài toán, mục 5 về MILP và mục 8.** Bài toán khớp các tổng nhóm gần với thanh toán gộp; paper so sánh greedy, DP và MILP trên benchmark tạo ra. Kết quả bằng nhau về tổng chưa xác định đúng khách/hóa đơn. Cần bổ sung identity, currency, thời gian, lý do phí, phân bổ từng phần và kiểm định nghiệp vụ. Không sử dụng mục tiêu tối đa số phần tử khớp như một bảo đảm đúng sổ.

**R4 — đọc cho quality gate.** Paper dùng constraint khai báo và thực thi kiểm tra dữ liệu ở quy mô lớn. Mượn nguyên tắc kiểm tra tự động để xây invariant tiền, khóa, replay và cutoff. Dự án có thể thực thi các contract này bằng SQL/Python; không cần đưa Spark/Deequ vào MVP chỉ vì paper dùng chúng.

**R1 — đọc để hiểu lựa chọn kiến trúc.** Paper trình bày lakehouse kết hợp định dạng mở, quản lý dữ liệu và truy cập phân tích/ML. Có thể dùng làm nền cho lập luận về nền dữ liệu dùng chung. Không phải benchmark Bronze/Silver/Gold so với PostgreSQL/DuckDB cho SME Việt Nam; không chứng minh Medallion là SOTA.

**R2 — đọc khi cần transaction và version trên object storage.** Paper mô tả Delta Lake với log giao dịch, ACID, upsert và time travel. Version vật lý giúp tái lập bảng; không đồng nghĩa đã xử lý đúng business time và availability time. Áp dụng khi nhu cầu vận hành đủ để bù chi phí triển khai và quản trị.

**R5 — đọc làm đối chứng matcher có giám sát.** Ditto khai thác mô hình ngôn ngữ pretrained và kiến thức miền để phân loại cặp thực thể; có bước blocking đi trước. Cân nhắc khi dữ liệu text/rule đơn giản đã đạt trần và có nhãn. Benchmark entity matching không tự bao gồm ràng buộc phân bổ số tiền hoặc giao dịch nhiều–nhiều; không gọi Ditto là SOTA hiện tại.

**R6 — đọc cho tương tác giữa các ứng viên.** Công trình nghiên cứu match/compare/select và framework ComEM thay cho việc quyết định từng cặp hoàn toàn riêng lẻ. Có thể tham khảo khi một giao dịch có nhiều ứng viên gần nhau. Khả năng chọn thực thể vẫn cần lớp ràng buộc tài chính, cơ chế không khớp và thí nghiệm riêng trên nội dung chuyển khoản Việt Nam.

**R8 — hướng thử nghiệm mới, đọc sau khi có baseline.** Bản v2 nghiên cứu LLM gán nhãn cho matcher nhỏ; hiệu quả phụ thuộc lựa chọn cặp và miền, đồng thời có hạn chế ở một số tập chứa nhiều thực thể chưa gặp. Có thể dùng để giảm công gán nhãn rồi audit bởi người; giữ gold test độc lập. Đây là preprint, không phải bằng chứng production hoặc SOTA cho đối soát ngân hàng.

## Nguồn kỹ thuật bổ sung, không phải paper

- [Databricks: Medallion architecture](https://developers.databricks.com/perspectives/what-is-the-medallion-architecture-in-a-modern-data-lakehouse): xác định vai trò các lớp và Gold aggregate/feature.
- [dbt: Snapshots](https://docs.getdbt.com/docs/build/snapshots): hiểu `timestamp`/`check` và các mốc do snapshot công cụ ghi lại.
- [Martin Fowler: Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html): phân biệt log event nghiệp vụ với bảng snapshot/lịch sử quan sát.
- [MISA Developer Portal](https://developer.misa.vn/) và [giới thiệu MISA BankHub](https://sme.misa.vn/63513/): kiểm tra loại dữ liệu/tích hợp; quyền API và điều kiện sử dụng cụ thể vẫn cần xác nhận với nhà cung cấp.

Thứ tự gợi ý: **R3 → R7 → R4 → R1/R2 → R5/R6/R8**. Tách rõ paper nền tảng, nghiên cứu gần đây và preprint; năm mới hơn không bảo đảm phù hợp hơn với task.
