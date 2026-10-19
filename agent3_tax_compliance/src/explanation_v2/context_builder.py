"""Never sends raw OCR, party identities, credentials, or tenant IDs to the LLM."""
from .contracts import Context, Fact

RESULT_TEXT = {
    'PASS': 'Kiểm tra này đã đạt trong phạm vi model và bản dữ liệu được chọn.',
    'FAIL': 'Kiểm tra này không đạt; cần xem bằng chứng và xử lý nội dung liên quan.',
    'REVIEW': 'Kiểm tra này cần người đối chiếu trước khi có thể sử dụng kết quả.',
}
ELIGIBILITY_TEXT = {
    'NOT_EVALUATED_MISSING_INPUT': 'Chưa chạy kiểm tra này vì còn thiếu dữ liệu cần thiết.',
    'NOT_EVALUATED_LOW_CONFIDENCE': 'Chưa chạy kiểm tra này vì dữ liệu trích xuất chưa đủ tin cậy.',
    'NOT_EVALUATED_INVALID_EXTRACTION': 'Chưa chạy kiểm tra này vì dữ liệu trích xuất chưa hợp lệ.',
    'OUT_OF_SCOPE_FOR_SOURCE': 'Nguồn chứng từ này không cung cấp loại bằng chứng cần cho kiểm tra này.',
    'NOT_APPLICABLE': 'Kiểm tra này không áp dụng theo điều kiện đã được xác định.',
    'NOT_EVALUATED_UNKNOWN_APPLICABILITY': 'Chưa xác định được kiểm tra này có áp dụng hay không.',
    'REVIEW_REQUIRED': 'Cần đối chiếu dữ liệu hoặc căn cứ trước khi chạy kiểm tra này.',
}


def build_context(artifact, excerpts):
    report = artifact.report
    base = report.explanation
    ref = 'evaluation:' + report.evaluation_id
    facts = [Fact(fact_id='summary', variants=(base.text,), refs=(ref,)),
             Fact(fact_id='scope', variants=(base.scope,
                 f'Chỉ giải thích kết quả của bản dữ liệu {report.record_revision} trong phạm vi kiểm tra đã chọn; không tự áp dụng cho chứng từ khác.'), refs=(ref,))]
    counts = report.aggregate.counts
    coverage = {'FULL':'đầy đủ trong phạm vi', 'PARTIAL':'một phần', 'NONE':'chưa có đơn vị được đánh giá'}[report.aggregate.coverage]
    facts.append(Fact(fact_id='coverage', variants=(
        f'Đã đánh giá {counts.evaluated}/{counts.in_scope} đơn vị trong phạm vi. '
        f'Mức bao phủ: {coverage}.',), refs=(ref,)))
    for i, text in enumerate(base.notices):
        facts.append(Fact(fact_id=f'notice-{i}', variants=(text,), refs=(ref,)))
    for i, text in enumerate(base.next_actions):
        facts.append(Fact(fact_id=f'action-{i}', variants=(text,), refs=(ref,)))
    for row in artifact.rule_results:
        refs = (f'result:{row.result_id}',) + tuple(s.reference for s in row.sources)
        # Finite code-defined paraphrases, never arbitrary model-authored tax conclusions.
        alternative = RESULT_TEXT.get(row.result) if row.execution_status == 'SUCCEEDED' else (
            ELIGIBILITY_TEXT.get(row.eligibility) if row.execution_status == 'NOT_RUN' else None)
        variants = tuple(dict.fromkeys((row.explanation,) + ((alternative,) if alternative else ())))
        facts.append(Fact(fact_id=row.result_id, variants=variants, refs=refs))
    for chunk in excerpts:
        # Exact quotations are shown as quotations, never as a new legal conclusion.
        locator = chunk.provision_locator or chunk.locator
        pages = ' (trang PDF '+', '.join(str(p) for p in chunk.source_pages)+')' if chunk.source_pages else ''
        text = f'Trích nguyên văn {chunk.document_id}, {locator}{pages}: «{chunk.text}»'
        if chunk.scope_note:
            text += '\nGhi chú biên tập, không phải nguyên văn quy phạm: '+chunk.scope_note
        from ..canonicalization.derive import sha
        facts.append(Fact(fact_id='quote:'+sha(chunk.chunk_id)[:24], variants=(text,), refs=('chunk:'+chunk.chunk_id,)))
    return Context(evaluation_id=report.evaluation_id, record_revision=report.record_revision,
                   record_sha256=report.record_sha256, facts=tuple(facts), excerpts=excerpts)
