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
