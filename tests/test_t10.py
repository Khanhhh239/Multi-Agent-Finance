import numpy as np
import pandas as pd
import pytest
from agent1.models.t10 import what_if, rank_collections, scenario_library
from agent1.text.verbalize import check_numbers, verbalize


def arguments():
    inv = pd.DataFrame({'invoice_id': ['i'], 'customer_id': ['c'], 'amount_open': [100.]})
    p = np.zeros((1, 13)); p[0, 2] = 1
    return dict(open_df=inv, P=p, B0=0., known_out=np.r_[np.full(4, 20.), np.zeros(9)], rev_q=None,
                kernel=np.zeros(17), capex_rate=0., capex_sizes=[], n=100, seed=7)


def test_early_collection_and_delay_scenarios():
    args = arguments()
    ranked = rank_collections(args['open_df'], args['P'], args)
    assert ranked.delta_shortfall.iloc[0] > 0
    before = args['known_out'].copy()
    shifted = what_if(args, shift_out=(0, 1, 10.))
    np.testing.assert_array_equal(before, args['known_out'])
    assert shifted['quantiles'].shape == (13, 3)
    delayed = what_if(args, delay_customer='c')
    assert delayed['shortfall_probability'] == 1
    assert len(scenario_library(args)) == 4


def test_number_gate_rejects_invented_numbers_and_percentages():
    table = {'week': 4, 'balance_text': '1.000.000', 'risk_text': '25%'}
    assert check_numbers(verbalize(table), table)
    assert not check_numbers('Thiếu hụt 250% ở tuần 4', table)
    assert not check_numbers('Số dư 10.000.000 VND', table)
    assert not check_numbers('Tuần9999 có rủi ro',table)
    assert not check_numbers('VND9999',table)
    with pytest.raises(ValueError, match='số không'):
        verbalize(table, llm=lambda _: 'Thiếu 999 VND')
