"""The controlled AI layer: whatever the model says, only verified output reaches the user. A fake model plays both
the honest and the careless model."""
import json

from src.assistant import ai


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, system, user, schema=None, num_predict=900):
        self.calls += 1
        return json.dumps(self.replies.pop(0), ensure_ascii=False), dict(prompt_tokens=10)


def model(tmp_path, replies):
    return ai.AI(FakeLLM(replies), tmp_path / 'cache.sqlite3')


ITEM = dict(title='Hóa đơn từ ngưỡng thanh toán không dùng tiền mặt chưa có chứng từ chuyển khoản', amount='3000000',
            detail='Tổng thanh toán 33.000.000 đồng, ngưỡng 5.000.000 đồng', action='Đính kèm chứng từ chuyển khoản')
INV = dict(display='1K26TGG/340', seller_name='Công ty TNHH Điện máy Thành Công', issue_date='2026-07-21', gross='33000000', vat='3000000')


def test_explanation_keeps_numbers_or_falls_back(tmp_path):
    good = model(tmp_path, [dict(text='Hóa đơn 33.000.000 đồng chưa thấy chuyển khoản nên 3.000.000 đồng thuế có thể bị loại. Hãy đính kèm ủy nhiệm chi.')])
    e = ai.explain(good, ITEM, INV)
    assert e.mode == 'AI_VERIFIED'
    bad = model(tmp_path / 'b', [dict(text='Bạn có thể bị phạt 20% tức 600.000 đồng trong 10 ngày.')])
    e = ai.explain(bad, ITEM, INV)
    assert e.mode == 'TEMPLATE' and '600' in e.note
    cached = ai.AI(FakeLLM([]), tmp_path / 'cache.sqlite3')
    assert ai.explain(cached, ITEM, INV).mode == 'AI_VERIFIED'           # second run served from the cache, no model call


def test_line_labels_are_verified_and_only_flags_become_findings(tmp_path):
    inv = dict(seller_name='Điện máy Thành Công', descriptions=['Điện thoại di động iPhone 16 Pro Max', 'Máy khoan bê tông Bosch', 'Hàng hóa'])
    reply = dict(lines=[dict(index=0, category='CA_NHAN', business_use='KHONG', reason='Điện thoại cao cấp không liên quan bán vật liệu'),
                        dict(index=1, category='CONG_CU_TAI_SAN', business_use='CO', reason='Máy khoan dùng thi công'),
                        dict(index=2, category='CA_NHAN', business_use='KHONG', reason='không rõ'),       # reason does not name the item
                        dict(index=9, category='CA_NHAN', business_use='KHONG', reason='dòng không tồn tại')])
    out = ai.classify_lines(model(tmp_path, [reply]), inv, ['4663 Bán buôn vật liệu xây dựng'])
    assert [x['verified'] for x in out['labels']] == [True, True, False]
    assert [x['line'] for x in ai.flagged(out['labels'])] == ['Điện thoại di động iPhone 16 Pro Max']


def test_bank_proposal_needs_the_name_in_the_bank_text(tmp_path):
    txns = [dict(txn_id='t1', direction='OUT', amount='66000000', booked='2026-09-27', description='CK tien thep cty Hung Phat', counterparty_name=None, source='A dòng 9'),
            dict(txn_id='t2', direction='OUT', amount='66000000', booked='2026-09-28', description='Chuyen tien', counterparty_name=None, source='A dòng 10')]
    invs = [dict(key='k1', seller_name='Công ty TNHH Thương mại Dịch vụ Hưng Phát', number='3', gross='66000000', issue_date='2026-09-24')]
    m = model(tmp_path, [dict(candidate=0, name_in_text='Hung Phat', reason='nhắc tên người bán'),
                         dict(candidate=0, name_in_text='Hưng Phát', reason='đoán')])     # second: name not in that text
    props = ai.bank_proposals(m, txns, invs, used_txns=set(), settled=set())
    assert [(p['txn_id'], p['invoice_key']) for p in props] == [('t1', 'k1')]


def test_letter_drops_paragraphs_with_unknown_ids_or_new_numbers(tmp_path):
    facts = [dict(id='F1', kind='invoice', text='Hóa đơn số 340 ngày 2026-07-21, tổng thanh toán 33.000.000 đồng'),
             dict(id='F2', kind='payment', text='Giao dịch ngày 2026-07-25, số tiền 33.000.000 đồng')]
    reply = dict(paragraphs=[dict(text='Hóa đơn số 340 đã được thanh toán 33.000.000 đồng bằng chuyển khoản.', fact_ids=['F1', 'F2'], passage_ids=[], quote=''),
                             dict(text='Doanh nghiệp đã nộp đủ 5.000.000 đồng tiền phạt.', fact_ids=['F1'], passage_ids=[]),
                             dict(text='Theo hợp đồng số 12.', fact_ids=['F9'], passage_ids=[])])
    out = ai.draft_letter(model(tmp_path, [reply]), dict(legal_name='Công ty A', tax_code='0109999982'), facts, [], 'Công văn số 1234/CT')
    assert out['mode'] == 'AI_VERIFIED' and len(out['paragraphs']) == 1 and len(out['dropped']) == 2
    none = ai.draft_letter(None, dict(legal_name='Công ty A', tax_code='0109999982'), facts, [], '')
    assert none['mode'] == 'TEMPLATE' and any('33.000.000' in p['text'] for p in none['paragraphs'])


def test_letter_paragraph_citing_law_needs_a_verbatim_quote(tmp_path):
    facts = [dict(id='F1', kind='invoice', text='Hóa đơn số 340, tổng thanh toán 33.000.000 đồng')]
    passages = [dict(pid='P1', path='Luật 48/2024/QH15 > Điều 14 > Khoản 2', doc_num='48/2024/QH15', url='u',
                     text='b) Có chứng từ thanh toán không dùng tiền mặt đối với hàng hóa, dịch vụ mua vào, trừ một số trường hợp đặc thù.')]
    reply = dict(paragraphs=[dict(text='Doanh nghiệp đã có chứng từ thanh toán không dùng tiền mặt.', fact_ids=['F1'], passage_ids=['P1'],
                                  quote='Có chứng từ thanh toán không dùng tiền mặt đối với hàng hóa, dịch vụ mua vào'),
                             dict(text='Việc kê khai là hoàn toàn đúng quy định.', fact_ids=['F1'], passage_ids=['P1'], quote='được khấu trừ toàn bộ')])
    out = ai.draft_letter(model(tmp_path, [reply]), dict(legal_name='A', tax_code='0109999982'), facts, passages, '')
    assert [p['text'] for p in out['paragraphs']] == ['Doanh nghiệp đã có chứng từ thanh toán không dùng tiền mặt.']
    assert 'nguyên văn' in out['dropped'][0]['reason']
