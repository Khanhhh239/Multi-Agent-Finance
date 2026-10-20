import sys
import unittest
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extraction_v1'))
from test_extraction import run,document
from src.explanation_v2.guide import build_guide,data_context
from src.explanation_v2.contracts import Context,Fact
from src.explanation_v2.natural import validate_draft


class GuideTests(unittest.TestCase):
    def test_present_is_not_confirmed_and_no_party_identity_leaks(self):
        record=run().record;guide=build_guide(record)
        self.assertIn('0 trường đã được người dùng xác nhận',guide.read_summary)
        self.assertNotIn(record.parties.seller.tax_id.value,guide.model_dump_json())
        self.assertTrue(any('có chữ không đồng nghĩa' in t.casefold() for t in guide.next_steps))

    def test_empty_items_abstains_from_empty_invoice_conclusion(self):
        record=run(document(['Số hóa đơn: A'])).record;guide=build_guide(record)
        self.assertTrue(any('Chưa trích được dòng hàng' in t for t in guide.missing_items))
        self.assertTrue(any('Bổ sung dòng hàng' in t for t in guide.next_steps))
        self.assertTrue(any(a.target=='data' and 'bỏ sót' in a.title for a in guide.actions))

    def test_data_only_rejects_affirmative_legal_claim_and_internal_ids(self):
        context=Context(evaluation_id='e',record_revision=1,record_sha256='a'*64,excerpts=(),facts=(
            Fact(fact_id='summary',variants=('Đã đọc 1 trường.',),refs=('evaluation:e',)),
            Fact(fact_id='scope',variants=('Chỉ giải thích dữ liệu. Chưa chứng minh hóa đơn hợp lệ.',),refs=('evaluation:e',)),
            Fact(fact_id='coverage',variants=('Chưa kiểm tra thuế.',),refs=('evaluation:e',)),
            Fact(fact_id='action-a',variants=('Bạn cần đối chiếu.',),refs=('evaluation:e',))))
        raw={'summary':{'text':'Chưa chứng minh hóa đơn hợp lệ.','fact_ids':['summary','scope','coverage']},'reasons':[{'text':'Chưa kiểm tra thuế.','fact_ids':['coverage']}],'next_actions':[{'text':'Bạn cần đối chiếu.','fact_ids':['action-a']}]}
        self.assertTrue(validate_draft(json.dumps(raw),context))
        for text in ('Hóa đơn hợp lệ.','Đã thanh toán.','evaluation-12345678'):
            raw['summary']['text']=text
            with self.assertRaises(ValueError):validate_draft(json.dumps(raw),context)


if __name__=='__main__':unittest.main()
