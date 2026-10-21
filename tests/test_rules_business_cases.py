import pytest
from agent1.rules.regression_cases import cases,calculate,coverage


@pytest.mark.parametrize('case',cases(),ids=lambda case:case['case'])
def test_configured_business_outcome(case):
    actual=calculate(case)
    if isinstance(case['expected'],str):assert actual==case['expected']
    else:assert actual==pytest.approx(case['expected'])


def test_all_registered_versions_have_two_business_cases():
    assert min(coverage().values())>=2
