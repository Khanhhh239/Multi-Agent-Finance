import pandas as pd
import pytest

from agent2.eval_v4 import CANDIDATES, POLICIES
from agent2.select_v4 import LABEL_FREE, pick, table


def results():
    names = list(CANDIDATES) + [p[0] for p in POLICIES]
    metric = {"recall": .3, "case_recall": .4, "hard_neg_alert_rate": .1}
    return [{"P1": {n: dict(metric) for n in names},
             "P2": {b: {n: dict(metric) for n in names} for b in ("a", "b")},
             "P3": {n: dict(metric) for n in names}} for _ in range(3)]


def test_score_uses_all_three_worlds_and_macro_branch_mean():
    r = results()
    r[0]["P2"]["a"]["L3"]["recall"] = .9
    t = table(r).set_index("config")
    assert t.loc["L3", "P2"] == pytest.approx(.4)
    assert t.loc["L3", "score"] == pytest.approx(1 / 3)


def test_false_alert_constraint_excludes_highest_score():
    t = pd.DataFrame({"config": ["a", "b"], "score": [.9, .5], "eligible": [False, True]})
    assert pick(t) == "b"


def test_near_tie_chooses_first_but_exact_boundary_does_not():
    t = pd.DataFrame({"config": ["a", "b"], "score": [.5, .509], "eligible": [True, True]})
    assert pick(t) == "a"
    t.loc[1, "score"] = .51
    assert pick(t) == "b"


def test_cold_start_selected_only_among_label_free_candidates():
    t = table(results())
    t.loc[t.config == "L3", "score"] = .99
    assert pick(t) == "L3"
    assert pick(t, LABEL_FREE) == LABEL_FREE[0]


def test_no_eligible_candidates_fails_explicitly():
    t = pd.DataFrame({"config": ["a"], "score": [.9], "eligible": [False]})
    with pytest.raises(ValueError, match="eligible"):
        pick(t)
