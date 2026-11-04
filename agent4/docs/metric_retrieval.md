# Metric Retrieval

Document embedding gồm label, description, synonyms và category; formula không
được đưa vào embedding text. Lexical retrieval dùng Unicode NFC/casefold và BM25,
không stemming tiếng Anh. Hai ranking được trộn bằng RRF với tie-break theo ID.

Relationship trong `config/metric_relationships.yaml` được curate và validate
với REGISTRY. Expansion chỉ đi một hop, có candidate budget và lưu provenance.
Metadata reranking chỉ boost/penalize thận trọng theo unit, period type, group-by
và view; không hard-filter khi câu hỏi không nêu constraint rõ ràng.
