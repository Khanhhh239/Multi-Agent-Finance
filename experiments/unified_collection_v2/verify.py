"""Oracle accounting regression. Future values here never enter forecasting."""
import numpy as np
import pandas as pd
from pathlib import Path

from agent1.data.world_manifest import sha256_file
from .cash import bank_paths_from_daily,draw_policy,future_dates,truth_from_daily
from .randomness import generator
from .data import write_json,read_json


def regression_audit(out):
    file = out/"accounting_regression.json"
    if file.exists():
        return read_json(file)
    rows = []
    fixture = Path(__file__).resolve().parent/"fixtures/accounting_regression"
    manifest = read_json(fixture/"manifest.json")
    for name,digest in manifest["hashes"].items():
        if sha256_file(fixture/name)!=digest:
            raise ValueError("Accounting regression fixture changed")
    world = manifest["case_id"]
    daily = pd.read_parquet(fixture/"daily_cash.parquet")
    bank = pd.read_parquet(fixture/"bank_txns.parquet")
    pay = pd.read_parquet(fixture/"payments.parquet")
    for fid in ("F000","F003"):
        cutoff = pd.Timestamp("2024-10-07")
        dates = future_dates(cutoff)
        company = daily[daily.firm_id.eq(fid)]
        actual = company.set_index("date").reindex(dates)
        b0,truth = truth_from_daily(company,cutoff)
        inflow = (actual.inflow_ar+actual.inflow_other).to_numpy()[None,:]
        outflow = actual.outflow.to_numpy()[None,:]
        policy,audit = draw_policy(company,cutoff,1,generator(7,fid,"audit"))
        chronology = bank_paths_from_daily(b0,inflow,outflow,dates,policy)
        full = bank_paths_from_daily(b0,inflow,outflow+actual.owner_draw.to_numpy()[None,:],dates,None)
        customer_bank = bank[bank.firm_id.eq(fid)&bank.cash_flow_class.eq("ar")]
        gross = pay[pay.firm_id.eq(fid)].groupby("pay_date_true").amount.sum().reindex(dates,fill_value=0)
        net = customer_bank.groupby("value_date").balance_effect.sum().reindex(dates,fill_value=0)
        fees = customer_bank.groupby("value_date").fee_deducted.sum().reindex(dates,fill_value=0)
        row = {"world":world,"firm_id":fid,"cutoff":str(cutoff.date()),
               "fee_bridge_max_error_vnd":float(np.abs(gross-net-fees).max()),
               "complete_actual_ledger_max_error_vnd":float(np.abs(full["balance"][0]-truth).max()),
               "oracle_daily_policy_max_error_vnd":float(np.abs(chronology["balance"][0]-truth).max()),
               "oracle_week13_balance":float(chronology["balance"][0,-1]),"true_week13_balance":float(truth[-1]),
               "oracle_detects_actual_shortfall":bool((chronology["balance"][0]<0).any() and (truth<0).any())}
        rows.append(row)
    passed = all(r["fee_bridge_max_error_vnd"]<=1 and r["complete_actual_ledger_max_error_vnd"]<=1 and
                 r["oracle_daily_policy_max_error_vnd"]<=1 and r["oracle_detects_actual_shortfall"] for r in rows)
    result = {"passed":passed,"cases":rows,"scope":"accounting regression with known future raw flows only; never a forecast score"}
    write_json(file,result)
    if not passed:
        raise ValueError("Daily ledger or timing regression failed")
    return result
