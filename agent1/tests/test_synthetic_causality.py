"""A later realization must not change an earlier synthetic decision."""
import numpy as np
import pandas as pd

from agent1.data.accounting import BANK_FLOW_CLASS, mark_bank_balance_window
from agent1.synth.decisions import (customer_activity, next_default_after_issue,
                                    observed_credit_holds, plan_inventory_purchases, weekly_payment_dates)
from agent1.synth.world import World, WorldConfig


def test_future_order_volume_does_not_move_past_invoice_issue_dates():
    """The final date draw must not depend on how many later invoices exist."""
    cfg = WorldConfig(seed=94319, start='2023-01-01', end='2025-12-31',
                      n_firms=1, write_xml=0, rng_version=2)

    def invoices(drop_2025):
        world = World(cfg)
        world.macro()
        world.rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 0, 0]))
        firm = world.make_firm(0)
        world.rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 0, 1]))
        customers = world.make_customers(firm)
        activity = np.ones((len(customers), world.W), dtype=bool)
        if drop_2025:
            activity[:, world.weeks.year == 2025] = False
        world.rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 0, 3]))
        frame = world.make_invoices(firm, customers, activity=activity)
        cutoff = int(world.cal.idx(np.datetime64('2025-01-01')))
        return frame.loc[frame.issue_i < cutoff, ['ci', 'issue_i', 'net']].reset_index(drop=True)

    pd.testing.assert_frame_equal(invoices(False), invoices(True))


def test_future_invoice_volume_does_not_change_past_credit_notes():
    """Settlement field draws must keep their prefix when future volume grows."""
    cfg = WorldConfig(seed=94319, start='2023-01-01', end='2025-12-31',
                      n_firms=1, write_xml=0, rng_version=3)
    customer = pd.DataFrame({'term_days': [30], 'ontime_logit': [-1.],
                             'early_p': [0.], 'late_med': [35.],
                             'late_sig': [.5], 'ultra_p': [0.],
                             'break_day': [-1], 'break_shift': [0.],
                             'dispute_p': [.2], 'payrun': ['adhoc'],
                             'tet_settle_p': [0.], 'partial_p': [.2]})
    firm = {'firm_id': 'F000', 'industry': 'services'}

    def settle(extra_future):
        world = World(cfg)
        early = int(world.cal.idx(np.datetime64('2023-01-09')))
        late = int(world.cal.idx(np.datetime64('2025-01-09')))
        n = 120 + extra_future
        invoice = pd.DataFrame({'ci': np.zeros(n, dtype=int),
                                'issue_i': np.r_[np.full(120, early),
                                                 np.full(extra_future, late)],
                                'net': np.full(n, 1_000_000.)})
        result, _ = world.settle(firm, customer, invoice, np.zeros((1, world.W)),
                                 np.array([-1]), np.zeros(world.W))
        return result.loc[:119, ['credit_note', 'credit_note_i', 'dispute',
                                  'amount_gross']].reset_index(drop=True)

    pd.testing.assert_frame_equal(settle(0), settle(80))


def test_rng_v3_keeps_v2_macro_and_invoice_issuance_streams(tmp_path):
    """The settlement fix must retain v2's per-firm generation stages."""
    worlds = {}
    for version in (2, 3):
        cfg = WorldConfig(seed=94319, start='2024-01-01', end='2024-12-31',
                          n_firms=1, write_xml=0, rng_version=version)
        path = tmp_path / f'rng_v{version}'
        World(cfg).run(path, verbose=False)
        worlds[version] = path

    cols = ['firm_id', 'customer_id', 'issue_date', 'due_date', 'amount_net']
    for table, fields in [('macro.parquet', ['week', 'common_factor']),
                          ('invoices.parquet', cols)]:
        before = pd.read_parquet(worlds[2] / table, columns=fields)
        after = pd.read_parquet(worlds[3] / table, columns=fields)
        pd.testing.assert_frame_equal(before, after)


def test_future_orders_do_not_change_past_purchases_or_inventory():
    orders = np.array([100., 150., 80., 120.])
    baseline = plan_inventory_purchases(orders, .7, 90.)
    changed = plan_inventory_purchases(np.array([100., 150., 8000., 120.]), .7, 90.)
    pd.testing.assert_frame_equal(baseline.iloc[:2], changed.iloc[:2])
    np.testing.assert_allclose(baseline.opening_inventory.iloc[1:], baseline.closing_inventory.iloc[:-1])


def test_future_spending_does_not_set_initial_cash():
    world = World(WorldConfig(start='2024-01-01', end='2024-01-04', n_firms=1, write_xml=0))
    bank = pd.DataFrame({'firm_id': ['F000'], 'value_date': [pd.Timestamp('2024-01-02')],
                         'amount': [0.], 'direction': ['in'], 'txn_type': ['interest']})
    bank['cash_flow_class'] = bank.txn_type.map(BANK_FLOW_CLASS)
    bank = mark_bank_balance_window(bank, world.start, world.end)
    firm = pd.DataFrame({'firm_id': ['F000'], 'buffer_days': [10.], 'opening_daily_outflow': [100.]})
    out = pd.DataFrame({'firm_id': ['F000'], 'date': [pd.Timestamp('2024-01-04')], 'amount': [20.]})
    base = world.cash_paths(firm, bank, out)
    changed = world.cash_paths(firm, bank, out.assign(amount=1_000_000.))
    assert base.opening_balance.eq(1000.).all()
    pd.testing.assert_frame_equal(base.iloc[:3], changed.iloc[:3])


def test_future_payment_date_cannot_set_promise_date():
    world = World(WorldConfig(start='2024-01-01', end='2024-04-30', n_firms=1, write_xml=0))
    cal = world.cal
    due = int(cal.idx(np.datetime64('2024-01-10')))
    invoice = pd.DataFrame({'ci': [0], 'term_days': [30], 'due_i': [due],
                            'amount_gross': [1000.], 'credit_note': [0.],
                            'credit_note_i': [-1], 'writeoff_i': [-1]})
    customer = pd.DataFrame({'reliability': [.65], 'late_med': [18.]})
    firm = {'firm_id': 'F000', 'collect_intensity': 1.}
    payments = pd.DataFrame({'k': [0], 'day_i': [due + 45], 'amount': [1000.]})
    first = world.promises(firm, customer, invoice, payments)
    later = World(world.cfg).promises(firm, customer, invoice, payments.assign(day_i=due + 80))
    assert len(first) and len(later)
    assert first.iloc[0].made_i == later.iloc[0].made_i
    assert first.iloc[0].promised_i == later.iloc[0].promised_i
    already_paid = payments.assign(day_i=due + 2)
    assert World(world.cfg).promises(firm, customer, invoice, already_paid).empty


def test_credit_hold_uses_current_and_previous_observed_signal_only():
    past = np.array([[-2., -2., -2., 0., 0.]])
    changed_future = past.copy()
    changed_future[:, 3:] = 9.
    before, decisions = observed_credit_holds(past, np.random.default_rng(4))
    after, changed_decisions = observed_credit_holds(changed_future, np.random.default_rng(4))
    np.testing.assert_array_equal(before[:, :3], after[:, :3])
    assert decisions[0] == changed_decisions[0]
    assert decisions[0][2] == 'seller_credit_hold'
    assert decisions[0][3] < -1.4 and decisions[0][4] < -1.4


def test_observed_default_stops_new_orders_only_from_its_week():
    liquidity = np.zeros((1, 7))
    ordinary, _ = observed_credit_holds(liquidity, np.random.default_rng(9))
    defaulted, decisions = observed_credit_holds(
        liquidity, np.random.default_rng(9), default_week=np.array([3]))
    np.testing.assert_array_equal(defaulted[:, :4], ordinary[:, :4])
    assert defaulted[:, 4:].all()
    assert any(row[2] == 'seller_default_hold' and row[1] == 4 for row in decisions)


def test_default_hold_expires_and_new_credit_can_be_granted():
    held, decisions = observed_credit_holds(
        np.zeros((1, 8)), np.random.default_rng(9),
        default_week=np.array([2]), default_cooldown_weeks=2)
    assert held[0, 3:5].all()
    assert not held[0, 5:].any()
    assert any(row[2] == 'seller_default_release' and row[1] == 5 for row in decisions)


def test_recurrent_default_holds_and_new_invoice_exposure():
    events = np.zeros((1, 11), dtype=bool)
    events[0, [2, 6]] = True
    held, changes = observed_credit_holds(
        np.zeros((1, 11)), np.random.default_rng(9),
        default_events=events, default_cooldown_weeks=2)
    np.testing.assert_array_equal(np.flatnonzero(held[0]), [3, 4, 7, 8])
    assert [row[2] for row in changes] == [
        'seller_default_hold', 'seller_default_release',
        'seller_default_hold', 'seller_default_release']
    issue = np.array([0, 20, 35, 60])
    expected = [17, 45, 45, 10 ** 9]
    np.testing.assert_array_equal(
        next_default_after_issue(issue, np.zeros(4, dtype=int), events, 0), expected)


def test_customer_lifecycle_uses_only_current_and_past_conditions():
    liquidity = np.zeros((1000, 365))
    initially_active = np.arange(1000) < 720
    baseline, events = customer_activity(liquidity, initially_active, np.random.default_rng(44))
    changed = liquidity.copy()
    changed[:, 180:] = -3.
    stressed, changed_events = customer_activity(changed, initially_active, np.random.default_rng(44))
    np.testing.assert_array_equal(baseline[:, :180], stressed[:, :180])
    assert [e for e in events if e[1] < 180] == [e for e in changed_events if e[1] < 180]
    assert .55 < baseline[:, -1].mean() < .85
    assert {e[2] for e in events} == {'customer_acquired', 'customer_churned', 'customer_returned'}
    assert stressed[:, -1].mean() < baseline[:, -1].mean()


def test_customer_default_is_not_used_to_backdate_seller_stop():
    world = World(WorldConfig(seed=31, start='2023-01-01', end='2024-12-31', n_firms=1, write_xml=0))
    world.macro()
    firm = world.make_firm(0)
    customers = world.make_customers(firm)
    end_days = customers.end_day.copy()
    world.customer_paths(firm, customers)
    pd.testing.assert_series_equal(customers.end_day, end_days)


def test_post_due_liquidity_shock_delays_already_open_invoices():
    world = World(WorldConfig(start='2023-01-01', end='2023-06-30', n_firms=1, write_xml=0))
    n = 4000
    start = int(world.cal.idx(np.datetime64('2023-01-09')))
    end = int(world.cal.idx(np.datetime64('2023-06-30')))
    shock_week = 5
    shock_day = world.week0_i + 7 * shock_week
    base = np.zeros((1, world.W))
    shocked = base.copy()
    shocked[:, shock_week:] = -3.
    args = (world.cal, world.week0_i, np.zeros(n, dtype=int), np.full(n, start),
            np.zeros(world.W), np.full(n, 35.), np.full(n, 'adhoc'),
            np.full(n, 10 ** 9), end)
    before = weekly_payment_dates(args[0], args[1], args[2], args[3], base, *args[4:],
                                  np.random.default_rng(7))
    after = weekly_payment_dates(args[0], args[1], args[2], args[3], shocked, *args[4:],
                                 np.random.default_rng(7))
    np.testing.assert_array_equal(before[(before >= 0) & (before < shock_day)],
                                  after[(after >= 0) & (after < shock_day)])
    horizon = shock_day + 49
    paid_before = (before >= 0) & (before <= horizon)
    paid_after = (after >= 0) & (after <= horizon)
    assert paid_after.sum() < paid_before.sum() - 300


def test_world_settlement_keeps_pre_shock_payments_and_delays_open_ar():
    config = WorldConfig(seed=44, start='2023-01-01', end='2023-12-31', n_firms=1, write_xml=0)
    baseline, stressed = World(config), World(config)
    issue = int(baseline.cal.idx(np.datetime64('2023-01-02')))
    n = 2500
    invoices = pd.DataFrame({'ci': np.zeros(n, dtype=int), 'issue_i': np.full(n, issue),
                             'net': np.full(n, 1_000_000.)})
    customer = pd.DataFrame({'term_days': [14], 'ontime_logit': [-2.], 'early_p': [0.],
                             'late_med': [35.], 'late_sig': [.5], 'ultra_p': [0.],
                             'break_day': [-1], 'break_shift': [0.], 'dispute_p': [0.],
                             'payrun': ['adhoc'], 'tet_settle_p': [0.], 'partial_p': [.2]})
    zero = np.zeros((1, baseline.W))
    shock_day = int(baseline.cal.idx(np.datetime64('2023-01-30')))
    shock_week = int(baseline.week_of(shock_day))
    shock = zero.copy()
    shock[:, shock_week:] = -3.
    stress = np.zeros(baseline.W)
    _, pay_base = baseline.settle({'industry': 'services'}, customer, invoices.copy(),
                                  zero, np.array([-1]), stress)
    _, pay_shock = stressed.settle({'industry': 'services'}, customer, invoices.copy(),
                                   shock, np.array([-1]), stress)
    cols = ['k', 'day_i', 'amount', 'kind']
    pd.testing.assert_frame_equal(pay_base.loc[pay_base.day_i < shock_day, cols].reset_index(drop=True),
                                  pay_shock.loc[pay_shock.day_i < shock_day, cols].reset_index(drop=True))
    horizon = shock_day + 42
    n_base = pay_base.loc[pay_base.day_i <= horizon, 'k'].nunique()
    n_shock = pay_shock.loc[pay_shock.day_i <= horizon, 'k'].nunique()
    assert n_shock < n_base - 150


def test_unresolved_invoice_is_censored_instead_of_bad_debt():
    from agent1.data.accounting import mark_observed_outcomes
    from agent1.models.features import add_labels

    invoices = pd.DataFrame({
        'closure_type': ['open', 'writeoff', 'paid'],
        'closed_date_true': pd.to_datetime([None, '2025-02-01', '2024-09-01']),
        'is_bad_debt': [True, True, False],
    })
    observed = mark_observed_outcomes(invoices, '2024-12-31')
    assert observed.outcome_status_at_end.tolist() == ['censored', 'censored', 'paid']
    assert not observed.is_bad_debt.any()
    frame = pd.DataFrame({'cutoff': pd.to_datetime(['2024-06-01']),
                          'label_date': pd.to_datetime([None]),
                          'writeoff_date': pd.to_datetime(['2025-02-01'])})
    labels = add_labels(frame, '2024-12-31').iloc[0]
    assert labels.event == 0 and labels.bad_known == 0
    assert labels.time_obs == (pd.Timestamp('2024-12-31') - pd.Timestamp('2024-06-01')).days
