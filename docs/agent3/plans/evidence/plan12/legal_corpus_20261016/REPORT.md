# Corpus pháp lý tối thiểu — đối chiếu ngày 16/10/2026

Đã chuẩn bị corpus nguồn để tiếp tục PLAN_12. **11 trích đoạn runtime / 4 văn bản**, **6 trích đoạn tham khảo / 4 văn bản khác**; tải lại **11 PDF chính thức**, tất cả khớp hash registry. Đây là kết quả đối chiếu nguồn do Codex thực hiện, **không phải chứng nhận pháp lý hoặc số đo accuracy 100%**.

Kiểm chứng phần bị ảnh hưởng: **102/102 Python tests PASS** (46 explanation/corpus + 39 planning + 17 end-to-end), Chrome desktop/mobile 5 nhóm PASS, không có page errors. Hash implementation V1 replay không đổi. Các ca retrieval kiểm scope/ngày/hash và giữ ngoại lệ, không phải benchmark semantic ranking.

[Corpus JSON](../../../../../../agent3_tax_compliance/configs/explanation/corpus_20261016_v1.json) · [Manifest](corpus_manifest.json) · [Nguồn/trang/hash](source_manifest.json) · [Coverage từng rule](rule_coverage.json) · [Kiểm thử](validation_summary.json).

## 1. Phạm vi đã đưa vào runtime

| Văn bản | Phần trích và trang PDF vật lý, đánh số từ 1 | Mục đích |
|---|---|---|
| [NĐ 254/2026/NĐ-CP](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf) | Toàn Điều 10, trang 21–23; Điều 43, trang 46; khoản 1 Điều 44, trang 46 | Nội dung hóa đơn, dẫn chiếu ngoại lệ, hiệu lực/thay thế; khoản chuyển tiếp chỉ cho hàng dự trữ quốc gia |
| [NĐ 181/2025/NĐ-CP](https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/181nd.signed.pdf) | Điều 26, trang 32–34, chia 4 đoạn theo khoản/điểm | Ngưỡng đã gồm VAT, chứng từ bị loại, các trường hợp đặc thù và tổng mua cùng ngày |
| [NĐ 144/2026/NĐ-CP](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/144-ndcp.signed.pdf) | Khoản 1 Điều 1, trang 1; Điều 4, trang 3; khoản 1 Điều 6, trang 3 | Đoạn sửa đổi điểm g và hiệu lực; khoản 1 Điều 1 là phần trích riêng về bảo hiểm, không phải toàn Điều 1 |
| [TT 91/2026/TT-BTC](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/91-btc.signed.pdf) | Điều 25 khoản 1–2, trang 32 | Hiệu lực và việc TT 32/2025 hết hiệu lực theo đoạn gốc |

Các locator legacy như `Article10.pdf21` là anchor bắt đầu. Trích đoạn mới có `provision_locator` và `source_pages=[21,22,23]` để không gán nội dung trang 22–23 thành trang 21. Bản trích một phần luôn có nhãn khoản và ghi chú phạm vi. Ghi chú biên tập được hiển thị **ngoài dấu trích nguyên văn**.

## 2. Những điểm đã kiểm tra trực tiếp trên ảnh PDF

- Điều 10 NĐ 254 đúng là nội dung hóa đơn. Bản trích giữ cả khoản 3 dẫn chiếu phụ lục về trường hợp không nhất thiết đầy đủ nội dung và khoản 4 về máy tính tiền. Không chỉ lấy danh sách bắt buộc khoản 1 rồi bỏ ngoại lệ.
- Điều 26 NĐ 181 giữ nguyên `05 triệu đồng`, `đã bao gồm thuế giá trị gia tăng`, phần loại chứng từ bên mua nộp tiền mặt vào tài khoản bên bán, điều kiện tổng mua **của một người nộp thuế trong cùng một ngày**, và các trường hợp khoản 2.
- Điểm g khoản 2 Điều 26 bản gốc chỉ được retrieval trước **20/06/2026**, cận trên loại trừ. Từ ngày đó không trả điểm g cũ; Điều 4 NĐ 144 chứa đoạn sửa đổi, gồm câu cho phép khai/khấu trừ khi có chứng từ sau điều chỉnh. Không ghép văn bản NĐ 144 vào câu trích rồi gán nguồn duy nhất NĐ 181.
- NĐ 254 Điều 43 nói bãi bỏ **Điều 1 NĐ 41/2022**, không phải toàn bộ NĐ 41. Bản trích giữ đúng phạm vi.
- PDF gốc NĐ 359 có 3 trang vật lý (trang in Công báo 20–22). Sau khi đọc cả 3 trang, thấy Điều 1 khoản 1 bổ sung khoản 1b Điều 4 và khoản 2 bãi bỏ khoản 3 Điều 37, khoản 3 Điều 39; **không thấy sửa trực tiếp Điều 26**. Căn cứ `AMENDMENT_SCOPE_PENDING` trong payment rules vẫn chưa được đổi; cần xác nhận lại sự cần thiết/phạm vi căn cứ khi xử lý legal registry/rules, không tự suy toàn NĐ 181 bị thay.

## 3. Phần tham khảo được giữ ngoài runtime

[Gói tham khảo](../../../../../../agent3_tax_compliance/configs/explanation/legal_sources/reference_packet_20261016.json) có trích khoản 4 Điều 10 NĐ 123, khoản 7 điểm a Điều 1 NĐ 70, khoản 2 Điều 1/khoản 1 Điều 2 NĐ 359, khoản 1 và điểm a khoản 2 Điều 1/khoản 1 Điều 2 NĐ 174. Mỗi đoạn có URL PDF/hash/trang/text hash. Gói này cố ý khác schema Corpus, không thể nạp nhầm như corpus runtime.

Chưa đưa các đoạn này vào runtime vì:

- Registry vẫn để ND123/ND70/ND359 ở trạng thái hoặc locator chờ duyệt. Một trích đoạn chính xác không chứng minh đã kiểm đủ mọi sửa đổi/ngoại lệ của điều khoản được rule dùng.
- NĐ 174 dẫn Phụ lục I/II; chưa rà toàn bộ danh mục và chưa có mapping taxonomy thực được duyệt. Không suy thuế suất chỉ từ mức 8% trong văn bản.
- TT 78, TT 32 và Luật 108 đã có PDF tải lại/hash nguồn; chưa chép nội dung vào active corpus khi chưa xác định điều/khoản cần cho rule hiện tại. NĐ 41 chỉ được registry dẫn chiếu, chưa có PDF gốc trong bộ cache.

## 4. Coverage và thời gian

**2/7 rule versions có đủ locator trong corpus**: `content-2026-v1` và `payment-2025-v1`. Đây chỉ là coverage căn cứ đã chọn, không phải 2 rule đã được duyệt hoặc tax accuracy. Các version khác vẫn bị chặn bởi căn cứ chờ duyệt; toàn bộ rules/models vẫn DRAFT.

Ruleset hiện tại có cận trên **15/10/2026 loại trừ**, nên ngày 16/10/2026 nằm ngoài cửa sổ các version. Đợt này không tự kéo dài rule, không sửa model thuế, không sửa registry v1 và không thay outcome cũ. Cần xử lý cập nhật phạm vi luật/rule riêng trước khi kiểm tra thuế cho hóa đơn mới sau mốc đó.

Corpus `validated_through=2026-10-16`: không retrieval cho ngày chứng từ sau mốc kiểm tra nguồn. Tìm kiếm sửa đổi mới đã thực hiện theo các văn bản liên quan trên nguồn Chính phủ/Công báo; **không khẳng định đã rà toàn bộ hệ thống pháp luật đến ngày này**. Metadata ghi rõ `TARGETED_PRIMARY_SOURCES_NOT_EXHAUSTIVE`.

## 5. Cách bảo đảm và giới hạn độ đúng

1. Tải PDF trực tiếp qua HTTPS từ Chính phủ/Công báo, kiểm format/giới hạn dung lượng và SHA-256; mismatch bị cách ly, không dùng thay file pin cũ.
2. Kiểm tra ảnh đúng trang nguồn; chép tay, chuẩn hóa NFC và nối dòng trình bày. Không lấy OCR scan làm ground truth; không dùng bản tin/tóm tắt thay nguyên văn PDF.
3. Lưu hash text, hash PDF và hash ảnh trang có thể render lại; metadata phân biệt review nguồn bởi Codex với duyệt pháp lý độc lập. Hash chứng minh file không đổi, **không chứng minh người chép đã hiểu hoặc chép đúng mọi chữ**.
4. Trích đoạn có `required_context=true` không bị BM25 top-k loại ngoại lệ; chỉ áp dụng sau filter đúng document/hash/locator/ngày. Top-k không được dùng làm lý do cắt bỏ điều kiện quan trọng.
5. Giữ tách khoảng hiệu lực toàn văn và khoảng áp dụng riêng khoản/điểm. Dữ liệu tham khảo chưa duyệt không vượt qua source gate.
6. Kiểm thử date boundaries, nguồn/hash sai, thiếu locator, UTF-8/NFC, tampering, context tối thiểu và các luồng API/replay. Chưa dùng các test đó để công bố semantic retrieval accuracy hoặc legal accuracy.

Vẫn cần lượt đối chiếu độc lập/nghiệp vụ trước release pháp lý. Model Qwen chưa cài/bật; corpus không mở auto-accept hoặc thay quyết định GoRules. Khi toàn bộ nguyên văn/context vượt budget, fallback được giữ; không cắt ngoại lệ để ép chạy model.

## 6. Tái hiện

Từ `D:\financial`, trên workspace đã có venv:

```powershell
# Network: PDF nguồn vào cache local, không ghi dữ liệu hóa đơn
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\prepare_legal_corpus_sources.py
# Rebuild từ bản chép đã đối chiếu và bytes nguồn pin
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\build_legal_corpus.py
# Kiểm thử phần bị ảnh hưởng
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_legal_corpus.py
# Từ thư mục app
.\.venv\Scripts\python.exe -m src.explanation_v2.cli --probe
```

PDF/ảnh nguồn lưu trong `agent3_tax_compliance/data/plan12_legal_corpus/`, bị gitignore. Git chỉ nhận corpus pháp luật, schema, scripts và báo cáo/provenance công khai. Nếu chạy refresh vào ngày khác, builder yêu cầu phiên nguồn/ngày review khớp: cập nhật theo một phiên corpus mới sau đối chiếu, không sửa ngày review cũ để qua gate. `corpus_v1.json` rỗng trước đây được giữ nguyên để truy lịch sử; mặc định mới là `corpus_20261016_v1.json`. Env override `AGENT3_EXPLANATION_CORPUS` vẫn có thể trỏ bản khác có chủ đích.
