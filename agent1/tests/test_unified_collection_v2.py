import numpy as np
import pandas as pd
import pytest
from scipy.special import ndtri

from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.unified_collection_v2.core import OPEN,PAID,PathState,advance
from experiments.unified_collection_v2.copula import conditional_uniforms
from experiments.unified_collection_v2.randomness import generator,seed_for
from experiments.unified_collection_v2.cash import (
    OTHER,allocate_weekly,bank_paths_from_daily,build_context,fee_rate,future_dates,
    history_blocks,net_bank_cash,revenue_history,weekly_sum,
)
from experiments.unified_collection_v2.features import SnapshotBuilder
from experiments.unified_collection_v2.rollout import simulate_receipts
from experiments.unified_collection_v2.data import nested_sample,validate_timeline,read_json,PROTOCOL
from experiments.unified_collection_v2.performance import MemoryMeter
from experiments.unified_collection_v2.metrics import score_ar


def origin(m=13):
    f = pd.DataFrame(np.zeros((m,len(V6_FEATURES))),columns=V6_FEATURES)
    f["invoice_id"] = [f"I{i}" for i in range(m)]
    f["firm_id"],f["customer_id"] = "F",[f"C{i//2}" for i in range(m)]
    f["cutoff"] = pd.Timestamp("2024-10-07")
    f["amount_open"] = 100.
    f["days_to_due"] = 30
    f["top1"],f["top2"] = np.nan,np.nan
    return f


class Constant:
    vocabulary = [{"cash_fraction":0.,"credit_fraction":0.,"status":OPEN},
                  {"cash_fraction":.5,"credit_fraction":0.,"status":OPEN},
                  {"cash_fraction":1.,"credit_fraction":0.,"status":PAID}]
    def __init__(self):
        self.max_batch = 0
    def predict(self,x,week=None):
        self.max_batch = max(self.max_batch,len(x))
        return np.tile([.7,.1,.2],(len(x),1))


class ZeroRevenue:
    def predict(self,x,num_threads=4):
        return np.zeros(len(x))


def revenue_models():
    return {q:ZeroRevenue() for q in (.1,.5,.9)}


def inputs():
    cutoff = pd.Timestamp("2024-10-07")
    dates = pd.date_range("2022-01-01","2025-01-06")
    daily = pd.DataFrame({"date":dates,"balance":100.,"owner_draw":0.,"inflow_ar":1.,"outflow":.5,
                          "inflow_other":2.,**{c:0. for c in OTHER}})
    daily["inflow_internal"] = 2.
    invoices = pd.DataFrame({"invoice_id":["old"],"issue_date":pd.to_datetime(["2023-01-01"]),"amount_gross":[100.]})
    payments = pd.DataFrame({"invoice_id":["old"],"pay_date_true":pd.to_datetime(["2023-01-10"]),"amount":[100.]})
    bank = pd.DataFrame({"value_date":pd.to_datetime(["2023-01-10"]),"cash_flow_class":["ar"],
                         "balance_effect":[99.],"fee_deducted":[1.]})
    out = pd.DataFrame({"date":pd.to_datetime(["2023-10-15","2024-10-15"]),
                        "category":["rent","rent"],"amount":[3.,999999.]})
    return invoices,payments,bank,out,daily,cutoff


def test_named_streams_fix_thirteen_invoice_counterexample():
    seed,case,n = 11,"F:2024-10-07",30000
    revenue = generator(seed,case,"new_revenue").standard_normal((n,13))
    u = conditional_uniforms(generator(seed,case,"collection_week_1"),n,np.zeros(13,int),np.arange(13),.15,.15)
    assert abs(np.corrcoef(revenue.ravel(),ndtri(u).ravel())[0,1]) < .015
    np.testing.assert_array_equal(revenue,generator(seed,case,"new_revenue").standard_normal((n,13)))
    assert seed_for(seed,case,"new_revenue")!=seed_for(seed,case,"collection_week_1")
    generator(seed,case,"collection_week_1").standard_normal((5,900))
    np.testing.assert_array_equal(revenue,generator(seed,case,"new_revenue").standard_normal((n,13)))


@pytest.mark.parametrize("cutoff,draw_date",[("2024-10-07","2024-12-31"),("2024-01-01","2024-03-31"),("2024-07-01","2024-09-30")])
def test_owner_draw_occurs_on_exact_day_with_post_draw_cash_preserved(cutoff,draw_date):
    dates = future_dates(cutoff)
    inflow,outflow = np.zeros((1,91)),np.zeros((1,91))
    position = dates.get_loc(pd.Timestamp(draw_date))
    inflow[0,position] = 20.
    if position+1<91:
        outflow[0,position+1] = 3.
    result = bank_paths_from_daily(2.,inflow,outflow,dates,{"cap":np.array([10.]),"target":np.array([1.5])})
    assert result["daily_balance"][0,position] == 1.5
    assert result["balance"][0,-1] == (1.5 if position==90 else -1.5)
    assert result["max_ledger_error_vnd"] < 1e-9


def test_full_ar_closes_while_bank_receipt_is_net_of_fee():
    s = PathState.start(1)
    applied,_,_ = advance(s,[0],[1.],[0.],[PAID])
    net,fee = net_bank_cash(applied*100,.01)
    assert net[0]==99 and fee[0]==1
    assert s.remaining[0]==0 and s.status[0]==PAID
    assert applied[0]*100==net[0]+fee[0]


def test_daily_allocation_preserves_every_week():
    cash = np.arange(26).reshape(2,13).astype(float)
    shares = np.broadcast_to(np.array([.1,.2,.1,.1,.2,.1,.2]),(2,13,7))
    np.testing.assert_allclose(weekly_sum(allocate_weekly(cash,shares)),cash)


def test_t4_week_boundary_includes_cutoff_in_history_and_excludes_it_from_future():
    inv = pd.DataFrame({"issue_date":pd.to_datetime(["2024-07-01","2024-07-02","2024-07-08"]),"amount_gross":[10.,20.,30.]})
    s = revenue_history(inv,"2024-07-01")
    assert s.sum()==10 and s.index[-1]==pd.Timestamp("2024-06-25")
    dates = future_dates("2024-07-01")
    assert dates[0]==pd.Timestamp("2024-07-02") and dates[6]==pd.Timestamp("2024-07-08")


def test_future_rows_and_amounts_cannot_change_forecast_context():
    inv,pay,bank,out,daily,cutoff = inputs()
    first = build_context(inv,pay,bank,out,daily,cutoff,revenue_models(),n=12,seed=7,case="test")
    changed = daily.copy()
    changed.loc[changed.date.gt(cutoff),changed.columns.difference(["date"])] = 9e15
    out.loc[out.date.gt(cutoff),"amount"] = 7e15
    bank = pd.concat([bank,pd.DataFrame({"value_date":[cutoff+pd.Timedelta(days=1)],"cash_flow_class":["ar"],"balance_effect":[9e15],"fee_deducted":[1e15]})])
    pay = pd.concat([pay,pd.DataFrame({"invoice_id":["old"],"pay_date_true":[cutoff+pd.Timedelta(days=1)],"amount":[9e15]})])
    inv = pd.concat([inv,pd.DataFrame({"invoice_id":["future"],"issue_date":[cutoff+pd.Timedelta(days=1)],"amount_gross":[9e15]})])
    second = build_context(inv,pay,bank,out,changed,cutoff,revenue_models(),n=12,seed=7,case="test")
    for key in ("open_profiles","new_bank_daily","other_daily","outflow_daily","new_fee_daily"):
        np.testing.assert_array_equal(first[key],second[key])
    assert first["fee_rate"]==second["fee_rate"]==.01
    assert "truth" not in first


def test_non_ar_scope_is_present_and_classified():
    inv,pay,bank,out,daily,cutoff = inputs()
    context = build_context(inv,pay,bank,out,daily,cutoff,revenue_models(),n=4,seed=8,case="test")
    assert context["scope"]=="operating_bank_account"
    np.testing.assert_allclose(context["other_daily"],context["other_by_class_daily"].sum(2))
    assert context["other_daily"].sum()==4*91*2
    assert context["new_bank_daily"].sum()==0


def test_known_supplier_and_capex_replace_same_category_day_without_double_counting():
    inv,pay,bank,out,daily,cutoff = inputs()
    future = pd.DataFrame({"date":[cutoff+pd.Timedelta(days=1)]*2,"category":["supplier","capex"],
                           "amount":[11.,3.],"known_at":[cutoff-pd.Timedelta(days=1)]*2})
    out["known_at"] = pd.NaT
    out = pd.concat([out,future],ignore_index=True)
    context = build_context(inv,pay,bank,out,daily,cutoff,revenue_models(),n=12,seed=4,case="test")
    np.testing.assert_array_equal(context["outflow_daily"][:,0],np.full(12,14.))
    out.loc[out.category.isin(["supplier","capex"]),"known_at"] = cutoff+pd.Timedelta(days=1)
    unknown = build_context(inv,pay,bank,out,daily,cutoff,revenue_models(),n=12,seed=4,case="test")
    np.testing.assert_array_equal(unknown["outflow_daily"][:,0],np.zeros(12))


def test_rollout_batches_before_feature_assembly_and_matches_analytic_mean():
    model = Constant()
    result = simulate_receipts(model,origin(2),n=20000,seed=9,case="test",rho_firm=0,rho_customer=0,batch_rows=7)
    # Cash expectation .25 * opening; expected next remaining .75 * opening.
    np.testing.assert_allclose(result["cash"].mean(0),.25*.75**np.arange(13)*200,atol=.65)
    assert model.max_batch <= 7
    assert max(a["max_feature_batch_rows"] for a in result["audit"])<=7


def test_rollout_reproducible_across_batch_sizes():
    a = simulate_receipts(Constant(),origin(13),n=100,seed=3,case="test",batch_rows=5)
    b = simulate_receipts(Constant(),origin(13),n=100,seed=3,case="test",batch_rows=10000)
    np.testing.assert_array_equal(a["cash"],b["cash"])


def test_empty_receivables_and_empty_history_edge():
    r = simulate_receipts(Constant(),pd.DataFrame(),n=5)
    assert r["cash"].shape==(5,13) and r["cash"].sum()==0
    inv = pd.DataFrame({"invoice_id":["I"],"firm_id":["F"],"customer_id":["C"],
        "issue_date":pd.to_datetime(["2023-12-01"]),"due_date":pd.to_datetime(["2024-01-31"]),
        "term_days":[61],"amount_gross":[100.],"paid_date_true":pd.to_datetime(["2024-01-02"]),
        "writeoff_date":pd.to_datetime([None]),"credit_note_date":pd.to_datetime([None]),"credit_note":[0.],"closure_type":["paid"]})
    pay = pd.DataFrame({"invoice_id":["I"],"pay_date_true":pd.to_datetime(["2024-01-02"]),"amount":[100.]})
    snapshot = SnapshotBuilder(inv,pay).snapshot("2024-01-01")
    assert snapshot.paid_frac_so_far.iloc[0]==0 and snapshot.amount_open.iloc[0]==100


def test_learning_curve_anchor_samples_are_nested_and_not_label_selected():
    f = pd.DataFrame({"firm_id":np.repeat(["A","B","C"],100),"label":np.arange(300)%2})
    a,b = nested_sample(f,31,1,"W"),nested_sample(f,79,1,"W")
    assert set(a.index)==set(range(len(a)))
    # Recover unique identity independent of the reset output index.
    f["id"] = np.arange(300)
    a,b = nested_sample(f,31,1,"W"),nested_sample(f,79,1,"W")
    assert set(a.id)<=set(b.id)
    f.label = 1-f.label
    np.testing.assert_array_equal(a.id,nested_sample(f,31,1,"W").id)


def test_rss_is_measured_and_ar_score_is_separate_from_bank_balance():
    with MemoryMeter() as meter:
        a = np.ones(100000)
    assert meter.result()["rss_peak_sampled_mib"]>0
    scores = score_ar(np.ones((10,13))*2,np.ones(13)*2,100)
    assert scores["ar_crps_normalized"]==0 and scores["ar_coverage80"]==1


def test_selection_and_confirmation_respect_baseline_and_label_availability():
    import copy
    p = read_json(PROTOCOL)
    baseline = {"train_label_end":"2024-07-01"}
    validate_timeline(p,baseline)
    before = copy.deepcopy(p)
    before["source_selection_cutoffs"][0] = "2024-04-01"
    with pytest.raises(ValueError,match="baseline"):
        validate_timeline(before,baseline)
    early = copy.deepcopy(p)
    early["evaluation_cutoffs"][0] = "2024-12-30"
    with pytest.raises(ValueError,match="selection outcomes"):
        validate_timeline(early,baseline)
    late_t4 = copy.deepcopy(p)
    late_t4["t4"]["fit_end"] = "2025-01-13"
    with pytest.raises(ValueError,match="T4"):
        validate_timeline(late_t4,baseline)
