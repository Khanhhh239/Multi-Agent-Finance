import pytest
from eval.gen.period_phrases import check_phrases,PHRASES
from eval.gen.split import assert_disjoint
from eval.gen.noise import perturb


def test_every_period_has_four_verified_phrases():
    assert all(len(p)>=4 for p in PHRASES.values())
    check_phrases()


def test_template_and_normalized_question_leakage_detected():
    with pytest.raises(ValueError,match='template'):
        assert_disjoint({'train':[{'template_id':'a','question':'A'}], 'val':[{'template_id':'a','question':'B'}]})
    with pytest.raises(ValueError,match='duplicate'):
        assert_disjoint({'train':[{'template_id':'a','question':'Lãi gộp?'}], 'val':[{'template_id':'b','question':'lai gop!'}]})


def test_noise_always_changes_text_and_is_reproducible():
    q='Doanh thu thuần tháng này?'
    for i in range(5):
        a=perturb(q,i);assert a==perturb(q,i) and a[0]!=q

def test_synonyms_actually_vary_in_small_generated_training_corpus(monkeypatch):
    from eval.gen import build_e1_e2 as generator
    from agent4.engine.metrics import REGISTRY
    subset={k:REGISTRY[k] for k in ('net_revenue','cogs')}
    monkeypatch.setattr(generator,'REGISTRY',subset)
    monkeypatch.setitem(generator.SPLITS,'train',(20251,'unused',18))
    monkeypatch.setattr(generator,'expected_value',lambda con,call:{})
    rows=generator.make_cases('e1','train',None,set())
    for metric in subset:
        assert len({r['metric_synonym'] for r in rows if r['expected']['args']['metric']==metric})>=2

def test_explicit_tax_profit_term_from_train_is_not_ambiguous(engine):
    from agent4.agent.preprocess import analyze
    hints=analyze('Lợi nhuận tính thuế tháng này',engine)
    assert hints.view_hint=='tax' and 'needs_clarification' not in hints.cues
