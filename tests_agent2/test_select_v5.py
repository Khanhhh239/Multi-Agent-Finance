import copy

import numpy as np
import pytest

from agent2.select_v5 import (COLD, SUPERVISED, advance, branch_macro, candidate_summary,
                             choose_cold, final_choice, pre_seal_gate, selection_roster, world_summary)

BRANCHES = tuple(f'b{i}' for i in range(10))


def test_branch_pool_matches_literal_micro_calculation():
    ns = [10,20,10,15,9,1,5,0,2,3]
    tps = [5,10,10,3,9,0,2,0,1,2]
    protocols = {b:dict(branch_positives=n,branch_tp=tp) for b,n,tp in zip(BRANCHES,ns,tps)}
    result=branch_macro(protocols,BRANCHES)
    assert result['B'] == pytest.approx(np.mean([.5,.5,1,.2,14/20]))
    assert result['small_group']['positives']==20 and result['averaging_terms']==5
    del protocols['b7']
    with pytest.raises(ValueError): branch_macro(protocols,BRANCHES)


@pytest.mark.parametrize('tier,n,tail', [('screening',8,2),('selection',20,4)])
def test_J_uses_registered_lowest_world_counts_and_requires_every_world(tier,n,tail):
    worlds={1001+i:dict(R=i/n,B=i/n,Q=i/n,eligible=True) for i in range(n)}
    result=candidate_summary(worlds,tier)
    assert result['J']==pytest.approx(np.mean(np.arange(tail)/n))
    assert result['tail_worlds']==list(range(1001,1001+tail))
    del worlds[1001]
    with pytest.raises(ValueError): candidate_summary(worlds,tier)


def test_hard_negative_limit_is_per_protocol_not_pooled():
    protocols={b:dict(branch_positives=10,branch_tp=5,hard_negatives=100,hard_negative_alerts=0) for b in BRANCHES}
    protocols['S2']=dict(tp=65,positives=100,hard_negatives=100,hard_negative_alerts=15)
    assert world_summary(protocols,BRANCHES)['eligible']
    protocols['b4']['hard_negative_alerts']=16
    assert not world_summary(protocols,BRANCHES)['eligible']


def test_advancement_and_final_choice_have_distinct_registered_ties():
    values=[.6,.609,.6,.61]
    candidates={name:dict(J=value,eligible=True) for name,value in zip(SUPERVISED,values)}
    assert advance(candidates)==[SUPERVISED[3],SUPERVISED[1],SUPERVISED[0]]
    assert final_choice(candidates,SUPERVISED)==SUPERVISED[1]
    candidates[SUPERVISED[3]]['eligible']=False
    assert SUPERVISED[3] not in advance(candidates)


@pytest.mark.parametrize('cold,values', [(False,(.65,.40,.50)),(True,(.40,.33,.30))])
def test_pre_seal_all_thresholds_inclusive_and_failure_prevents_seal(cold,values):
    summary=dict(tier='selection',eligible=True,**dict(zip(('R_mean','B_mean','R_min'),values)))
    assert pre_seal_gate(summary,cold)['passed']
    for key in ('R_mean','B_mean','R_min'):
        bad=copy.deepcopy(summary); bad[key]-=.000001
        gate=pre_seal_gate(bad,cold)
        assert not gate['passed']
        assert gate['decision']==('drop_cold' if cold else 'stop_without_generating_sealed_worlds')
    summary['tier']='screening'
    with pytest.raises(ValueError): pre_seal_gate(summary,cold)


def test_both_cold_controls_run_twenty_worlds_outside_supervised_slots():
    supervised={name:dict(J=.8-i*.03,eligible=True) for i,name in enumerate(SUPERVISED)}
    roster=selection_roster(supervised)
    assert roster['supervised']==list(SUPERVISED[:3])
    assert roster['cold']==list(COLD)
    worlds={seed:dict(R=.5,B=.4,Q=.45,eligible=True) for seed in range(1001,1021)}
    cold={name:candidate_summary(copy.deepcopy(worlds),'selection') for name in COLD}
    assert choose_cold(cold)==COLD[0]
    # The higher-ranked Cold cannot win if it violates the per-world ceiling.
    cold[COLD[0]]['eligible']=False
    assert choose_cold(cold)==COLD[1]
    del cold[COLD[0]]['worlds'][1020]
    with pytest.raises(ValueError): choose_cold(cold)
    del cold[COLD[0]]
    with pytest.raises(ValueError): choose_cold(cold)
