"""Versioned correction of cash-calendar target times; preserve every feature/key."""
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from agent1.adaptive.compact_t1 import sha256
from experiments.t1_compact.aligned_data import correct_labels,write
from experiments.t1_compact.refit_landmark import ROOT,SOURCE,protocol
from experiments.t1_compact.train import world_ledgers

PARENT=ROOT/"outputs/t1/aligned_refit_20261112"
CORRECTED=ROOT/"outputs/t1/aligned_cashcalendar_20261113"


def initialize(output=CORRECTED):
    output.mkdir(parents=True,exist_ok=True)
    contract=dict(version="cash-calendar-full-settlement-v2",baseline_cache=str(PARENT.resolve()),
        target="First actual cash date with cumulative receipts known by label_end covering original gross claim; noncash credits excluded.",
        unchanged="Features, invoice keys, eligibility, cash amounts, World seeds, splits, candidates, budgets and selection thresholds.",
        reason="Model-independent check found posting-order Paid times earlier than full cash recovery; repair target before final aggregate reporting.",
        original_frozen_sha256=sha256(PARENT/"frozen.json"),
        holdout_scope="Same new-seed Worlds after mechanical label correction, not newly unseen seeds after correction. No aggregate test scores used to alter hyperparameters.")
    path=output/"target_contract.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8"))!=contract:
        raise ValueError("Target correction contract changed")
    if not path.exists():write(path,contract)
    inventory=json.loads((PARENT/"fresh_inventory.json").read_text(encoding="utf-8"))
    for entry in inventory:
        entry["directory"]=str((PARENT/entry["directory"]).resolve())
    write(output/"fresh_inventory.json",inventory)
    for name in ("fresh_world_design.json","onboarding_design.json","comparison_amendment.json"):
        shutil.copyfile(PARENT/name,output/name)
    protocol(output)
    return output


def copy_role(output,role):
    paths=[]
    old_inventory=json.loads((SOURCE/"inventory.json").read_text(encoding="utf-8"))
    fresh_inventory=json.loads((output/"fresh_inventory.json").read_text(encoding="utf-8"))
    label_end={"train":"2023-12-31","validation":"2024-06-30","weight_validation":"2025-03-31",
               "audit":"2025-12-31","fresh_test":"2025-12-31"}[role]
    for receipt_path in sorted((PARENT/"prepared").glob("*.json")):
        receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt["role"]!=role:continue
        old_path=receipt_path.with_suffix(".parquet")
        path=output/"prepared"/old_path.name
        if not path.exists():
            old=pd.read_parquet(old_path)
            new=old.copy()
            world=str(old.world.iloc[0])
            entry=next((e for e in old_inventory if e["name"]==world),None)
            directory=SOURCE/entry["directory"] if entry else Path(next(e for e in fresh_inventory if e["name"]==world)["directory"])
            for firm,ledger in world_ledgers(directory):
                part=old[old.firm==firm]
                if len(part):new.loc[part.index,"paid_days"]=correct_labels(part,ledger,label_end).paid_days
            changes=int((new.paid_days!=old.paid_days).sum())
            pd.testing.assert_frame_equal(new.drop(columns="paid_days"),old.drop(columns="paid_days"))
            path.parent.mkdir(parents=True,exist_ok=True)
            new.to_parquet(path,index=False)
            write(path.with_suffix(".json"),dict(world=world,role=role,rows=len(new),sha256=sha256(path),
                parent_prepared_sha256=sha256(old_path),label_changed_rows=changes,
                target_contract_sha256=sha256(output/"target_contract.json")))
            print(f"Corrected {world}: {changes}/{len(new)} target days",flush=True)
        record=json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if sha256(path)!=record["sha256"]:raise ValueError("Corrected data cache changed")
        paths.append(path)
    return pd.concat([pd.read_parquet(p) for p in paths],ignore_index=True)


def copy_local(output):
    inventory=json.loads((output/"fresh_inventory.json").read_text(encoding="utf-8"))
    audit=[]
    for entry in inventory:
        if entry["role"]!="fresh_test":continue
        for firm,ledger in world_ledgers(Path(entry["directory"])):
            for old_path in sorted((PARENT/"local_rows"/entry["name"]/firm).glob("*.parquet")):
                path=output/"local_rows"/entry["name"]/firm/old_path.name
                if path.exists():continue
                old=pd.read_parquet(old_path)
                new=old.copy()
                origin=pd.Timestamp(old_path.stem)
                for role,offset in (("fit",210),("validation",91),("audit",0)):
                    part=old[old.role==role]
                    if len(part):new.loc[part.index,"paid_days"]=correct_labels(part,ledger,origin-pd.Timedelta(days=offset)).paid_days
                pd.testing.assert_frame_equal(new.drop(columns="paid_days"),old.drop(columns="paid_days"))
                path.parent.mkdir(parents=True,exist_ok=True)
                new.to_parquet(path,index=False)
                audit.append(dict(world=entry["name"],firm=firm,origin=str(origin.date()),
                                  rows=len(new),changed_days=int((new.paid_days!=old.paid_days).sum()),sha256=sha256(path)))
    write(output/"local_target_corrections.json",audit)

