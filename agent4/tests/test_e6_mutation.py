import pytest
from agent4.agent.render import render_facts
from agent4.agent.verifier import verify
from eval.gen.build_e6_e7 import mutate_answer,KINDS


@pytest.mark.parametrize('metric',['net_revenue','gross_margin_pct','unbalanced_journals'])
@pytest.mark.parametrize('kind',KINDS)
def test_mutations_have_valid_base_and_changed_semantics(engine,metric,kind):
    source=engine.query(metric,'2026-Q3');other=engine.query('cash_and_equivalents','2026-Q3')
    block=render_facts([source,other]);assert verify(block.text,block.allowed,block.required_labels).ok
    answer=mutate_answer(block,source,other,kind,1)
    assert answer!=block.text
    assert verify(answer,block.allowed,block.required_labels).ok==(kind=='faithful')
