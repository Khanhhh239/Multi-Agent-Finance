# Few-shot Strategy

Example bank tập trung vào ranh giới quyết định như amount-vs-ratio,
snapshot-vs-flow và specialized-vs-generic. Selector hỗ trợ `zero`, `static`,
`similarity`, `coverage` và `adaptive`. Adaptive policy dùng số ranh giới cạnh
tranh, mức chênh rank và bất đồng dense/lexical; cosine không được diễn giải như
xác suất.

Prompt chỉ đưa candidate hiện hành, example đã chọn, context và câu hỏi ở dạng
JSON data. System instruction yêu cầu bỏ qua instruction nằm trong các trường
dữ liệu và chỉ trả metric ID thuộc candidate set.
