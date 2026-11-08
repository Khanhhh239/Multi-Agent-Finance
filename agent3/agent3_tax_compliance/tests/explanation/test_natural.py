import json
import unittest
from src.explanation_v2.contracts import Context,Fact,ExplanationArtifact,Policy
from src.explanation_v2.natural import request_data,validate_draft


class NaturalDraftTests(unittest.TestCase):
    def context(self):
        return Context(evaluation_id='e',record_revision=2,record_sha256='a'*64,excerpts=(),facts=(
            Fact(fact_id='summary',variants=('Chưa đủ căn cứ kết luận.',),refs=('evaluation:e',)),
            Fact(fact_id='scope',variants=('Chỉ kiểm tra bản đã lưu.',),refs=('evaluation:e',)),
            Fact(fact_id='coverage',variants=('Đã chạy 0/2 kiểm tra.',),refs=('evaluation:e',)),
            Fact(fact_id='notice-0',variants=('Luật còn chờ duyệt.',),refs=('evaluation:e',)),
            Fact(fact_id='action-0',variants=('Cần đối chiếu dữ liệu.',),refs=('evaluation:e',))))

    def valid(self):
        return {'summary':{'text':'Chưa đủ căn cứ kết luận cho bản đã lưu.','fact_ids':['summary','scope']},
            'reasons':[{'text':'Đã chạy 0/2 kiểm tra. Luật còn chờ duyệt.','fact_ids':['coverage','notice-0']}],
            'next_actions':[{'text':'Bạn cần đối chiếu dữ liệu.','fact_ids':['action-0']}]}

    def test_natural_text_has_schema_and_explicit_refs(self):
        text,schema=request_data(self.context());self.assertNotIn('record_sha256',text)
        wire=json.loads(text)
        self.assertEqual({f['fact_id'] for f in wire['section_inputs']['summary']},{'summary','scope','coverage'})
        self.assertNotIn('Luật còn chờ duyệt',json.dumps(wire['section_inputs']['summary'],ensure_ascii=False))
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(validate_draft(json.dumps(self.valid()),self.context()).summary.fact_ids,('summary','scope'))
        self.assertEqual(Policy().style,'CONTROLLED_SELECTION')

    def test_numeric_legal_conclusion_markup_unknown_and_omission_rejected(self):
        for text in ('Tổng tiền 999 đồng.','Theo Điều 999.','Hóa đơn hợp lệ.',
                     'Bạn được khấu trừ toàn bộ.','<script>alert(1)</script>','Xem https://evil.test'):
            raw=self.valid();raw['summary']['text']=text
            with self.subTest(text=text),self.assertRaises(ValueError):validate_draft(json.dumps(raw),self.context())
        for ids in (['unknown'],['summary','summary'],['summary']):
            raw=self.valid();raw['summary']['fact_ids']=ids
            with self.subTest(ids=ids),self.assertRaises(ValueError):validate_draft(json.dumps(raw),self.context())

    def test_valid_json_is_not_a_semantic_approval(self):
        # Mechanical checks cannot establish general entailment. The service
        # must ALWAYS mark this mode as a draft requiring semantic review.
        self.assertIn('semantic_review_required',ExplanationArtifact.model_fields)
        raw=self.valid();raw['summary']['text']='Câu diễn đạt chưa được con người đánh giá.'
        self.assertTrue(validate_draft(json.dumps(raw),self.context()))

