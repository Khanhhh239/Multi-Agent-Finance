from agent4.agent.render import render_facts
from agent4.agent.verifier import verify


def test_source_derived_footer_counts_do_not_become_financial_evidence(engine):
    result=engine.query('net_revenue','2026-Q3',group_by='customer',top_k=3)
    block=render_facts([result]);pair=(3,result['rows_total'])
    assert pair in block.allowed.renderer_counts
    assert verify(block.text,block.allowed,block.required_labels).ok
    forged=block.text.replace(f'hiển thị 3/{pair[1]} dòng',f'hiển thị 4/{pair[1]} dòng')
    assert not verify(forged,block.allowed,block.required_labels).ok
    assert not verify(block.text+' Có 999001 khách hàng.',block.allowed,block.required_labels).ok
