"""Reproducible diagnostics before promoting a synthetic cohort to training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import sha256_file, verify_world_manifest
from agent1.synth.fidelity import value_outcomes


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else None


def audit_world(directory: Path) -> dict:
    directory = Path(directory)
    manifest = verify_world_manifest(directory, validate=True)
    inv = pd.read_parquet(directory / 'invoices.parquet')
    firms = pd.read_parquet(directory / 'firms.parquet')
    customers = pd.read_parquet(directory / 'customers.parquet')
    cash = pd.read_parquet(directory / 'daily_cash.parquet')
    events = pd.read_parquet(directory / 'events.parquet')
    macro = pd.read_parquet(directory / 'macro.parquet')
    with_industry = inv.merge(firms[['firm_id', 'industry']], on='firm_id')
    outcomes = value_outcomes(with_industry).to_dict('index')
    nominal = float(firms.revenue_annual.sum())
    years = {}
    for year, group in inv.groupby(inv.issue_date.dt.year):
        credit = group[group.term_days > 0]
        censored = credit[credit.outcome_status_at_end.eq('censored')]
        years[str(year)] = {
            'invoices': int(len(group)),
            'active_customers': int(group.customer_id.nunique()),
            'invoice_net_to_nominal_revenue': _ratio(group.amount_net.sum(), nominal),
            'credit_value_share': _ratio(credit.amount_gross.sum(), group.amount_gross.sum()),
            'credit_count_share': _ratio(len(credit), len(group)),
            'censored_credit_value_share': _ratio(censored.amount_gross.sum(),
                                                   credit.amount_gross.sum()),
            'negative_balance_firm_day_share': float((cash.loc[cash.date.dt.year.eq(year),
                                                         'balance'] < 0).mean()),
        }
    credit = inv[inv.term_days > 0]
    count_2019 = years.get('2019', {}).get('invoices')
    count_2025 = years.get('2025', {}).get('invoices')
    ratio_2019 = years.get('2019', {}).get('invoice_net_to_nominal_revenue')
    ratio_2025 = years.get('2025', {}).get('invoice_net_to_nominal_revenue')
    return {
        'world': directory.name,
        'manifest_sha256': sha256_file(directory / 'manifest.json'),
        'firms': int(len(firms)),
        'customers': int(len(customers)),
        'invoices': int(len(inv)),
        'source_data_sha256': manifest['source_data_sha256'],
        'macro_source_counts': macro.covid_source.value_counts().to_dict(),
        'all_year_credit_value_share': _ratio(credit.amount_gross.sum(), inv.amount_gross.sum()),
        'all_year_outcomes_on_known_credit': outcomes['ALL'],
        'negative_balance_firm_day_share': float(cash.balance.lt(0).mean()),
        'customer_default_events': int(events.type.eq('customer_default').sum()),
        'invoice_count_2025_to_2019': _ratio(count_2025, count_2019),
        'net_revenue_ratio_2025_to_2019': _ratio(ratio_2025, ratio_2019),
        'years': years,
        'industry_outcomes_on_known_credit': {key: value for key, value in outcomes.items()
                                               if key != 'ALL'},
    }


def compare_control(stressed: Path, control: Path) -> dict:
    truth = pd.read_parquet(stressed / 'shock_truth.parquet')
    active = truth[truth.strength.gt(0)]
    if active.empty:
        raise ValueError('Stressed world has no active episode')
    first = active.week.min()
    a = pd.read_parquet(stressed / 'inventory_weekly.parquet')
    b = pd.read_parquet(control / 'inventory_weekly.parquet')
    joined = a.merge(b, on=['firm_id', 'week'], suffixes=('_stress', '_control'),
                     validate='one_to_one')
    before = joined[joined.week.lt(first)]
    columns = ('booked_orders', 'purchase_net', 'sale_price_index', 'input_cost_index')
    discrepancy = {column: float(np.max(np.abs(before[f'{column}_stress'] -
                                                before[f'{column}_control'])))
                   for column in columns}
    families = {}
    for family, group in active.groupby('family'):
        during = joined[joined.week.isin(group.week)]
        families[family] = {'first_active_week': str(group.week.min().date()),
                            'last_active_week': str(group.week.max().date()),
                            'active_weeks': int(group.week.nunique()),
                            'peak_strength': float(group.strength.max()),
                            'booked_orders_stress_to_control': _ratio(
                                during.booked_orders_stress.sum(),
                                during.booked_orders_control.sum()),
                            'purchase_net_stress_to_control': _ratio(
                                during.purchase_net_stress.sum(),
                                during.purchase_net_control.sum()),
                            'mean_supply_capacity': float(during.supply_capacity_stress.mean()),
                            'mean_sale_price_index': float(during.sale_price_index_stress.mean()),
                            'mean_input_cost_index': float(during.input_cost_index_stress.mean())}
    return {'first_episode_week': str(first.date()),
            'pre_episode_max_absolute_difference': discrepancy,
            'pre_episode_identical': all(value == 0 for value in discrepancy.values()),
            'episode_families': families}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('world', type=Path)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'stressed': audit_world(args.world)}
    if args.control:
        result['control'] = audit_world(args.control)
        result['matched_comparison'] = compare_control(args.world, args.control)
    stressed = result['stressed']
    control = result.get('control')
    result['readiness_checks'] = {
        'world_contracts_and_hashes': True,
        'external_macro_inputs_present': all(stressed['source_data_sha256'].get(key)
                                             for key in ('oxcgrt', 'wdi')),
        'no_structural_revenue_collapse_in_control': bool(control and
            control['net_revenue_ratio_2025_to_2019'] is not None and
            control['net_revenue_ratio_2025_to_2019'] >= .6),
        'matched_pre_episode_history': bool(result.get('matched_comparison', {}).get(
            'pre_episode_identical')),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                               encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
