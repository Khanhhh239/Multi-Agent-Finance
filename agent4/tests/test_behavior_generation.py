from eval.gen.build_behavior import AMBIGUITIES,AMBIGUOUS_VAL,AMBIGUOUS_TEST,REFUSALS


def test_origins_have_different_authored_bodies_between_splits():
    # Renaming a template_id or adding only a wrapper is insufficient isolation.
    train={r[1] for r in AMBIGUITIES};val=set(AMBIGUOUS_VAL);test=set(AMBIGUOUS_TEST)
    assert not train&val and not train&test and not val&test
    for _,variants in REFUSALS:
        assert len(set(variants))==3
