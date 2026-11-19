"""Natural-frequency learning curve and calibration on disjoint source firms."""
from __future__ import annotations

import gc
import numpy as np
import pandas as pd
import lightgbm as lgb

from agent1.data.world_manifest import sha256_file
from agent1.paths import ROOT
from .core import FEATURES,fit_vocabulary,encode
from .data import read_json,dataset,write_json,write_csv,write_bytes_once
from .model import TransitionModel,calibrate,guards
from .metrics import replay_classes
from .performance import MemoryMeter


def load_model(out,budget):
    directory = out/"candidates"/str(budget)
    meta = read_json(directory/"train.json")
    if sha256_file(directory/"model.txt")!=meta["model_sha256"]:
        raise ValueError("Candidate model hash mismatch")
    if "calibration_sha256" in meta and sha256_file(directory/"calibration.json")!=meta["calibration_sha256"]:
        raise ValueError("Candidate calibration hash mismatch")
    calibration = read_json(directory/"calibration.json")
    return TransitionModel(lgb.Booster(model_file=str(directory/"model.txt")),meta["vocabulary"],calibration),meta


def train_candidates(out,cohort,p):
    fx,fk,fp,fd = dataset(out,cohort,p,"calibration_fit")
    sx,sk,sp,sd = dataset(out,cohort,p,"calibration_select")
    source_anchors = pd.concat([pd.read_parquet(out/"cache"/f"calibration_select_{e['name']}_anchors.parquet")
                               for e in cohort["worlds"] if e["role"]=="train"],ignore_index=True)
    for budget in p["candidate_anchor_budgets"]:
        directory = out/"candidates"/str(budget)
        if (directory/"calibration.json").exists() and (directory/"train.json").exists():
            load_model(out,budget)
            continue
        print(f"training {budget:,} source anchors, {p['rounds']} rounds",flush=True)
        reused_from = None
        if p.get("reuse_models_from"):
            prior_root = ROOT/p["reuse_models_from"]
            old_protocol = read_json(prior_root/"protocol.lock.json")
            for name in ("source_cohort","seed","train_label_end","partial_fraction_edges","rounds","lightgbm"):
                if old_protocol[name]!=p[name]:
                    raise ValueError("Prior collection fit protocol differs")
            prior = prior_root/"candidates"/str(budget)
            old = read_json(prior/"train.json")
            if sha256_file(prior/"model.txt")!=old["model_sha256"] or old["features"]!=FEATURES:
                raise ValueError("Prior collection weights changed")
            vocabulary,rows = old["vocabulary"],old["transition_rows"]
            write_bytes_once(directory/"model.txt",(prior/"model.txt").read_bytes())
            write_bytes_once(directory/"label_support.csv",(prior/"label_support.csv").read_bytes())
            quantization = {k:v for k,v in read_json(prior/"discretization.json").items() if k.startswith("train_")}
            model = lgb.Booster(model_file=str(directory/"model.txt"))
            performance = old["performance"]
            reused_from = p["reuse_models_from"]+f"/candidates/{budget}"
        else:
            with MemoryMeter() as meter:
                x,keys,pairs,detail = dataset(out,cohort,p,"fit",budget)
                vocabulary = fit_vocabulary(keys,pairs)
                y = encode(keys,vocabulary)
                model = lgb.train({**p["lightgbm"],"num_class":len(vocabulary)},
                                  lgb.Dataset(x,y,feature_name=FEATURES),num_boost_round=p["rounds"])
                write_bytes_once(directory/"model.txt",model.model_to_string().encode("utf-8"))
                representatives = np.array([[v["cash_fraction"],v["credit_fraction"]] for v in vocabulary])[y]
                error = (representatives-pairs)*detail.opening.to_numpy()[:,None]
                support = detail.assign(outcome=y).groupby(["world","outcome"]).agg(rows=("outcome","size"),
                    invoices=("invoice_id","nunique"),firms=("firm_id","nunique")).reset_index()
                write_csv(directory/"label_support.csv",support)
                quantization = {"train_teacher_forced_cash_wape":float(np.abs(error[:,0]).sum()/max(detail.cash_actual.sum(),1)),
                                "train_teacher_forced_cash_bias":float(error[:,0].sum()/max(detail.cash_actual.sum(),1))}
                rows = len(y)
                del x,keys,pairs,detail,y,representatives,error
                gc.collect()
            performance = meter.result()
        raw = TransitionModel(model,vocabulary)
        fy,sy = encode(fk,vocabulary,allow_unknown=True),encode(sk,vocabulary,allow_unknown=True)
        calibration = calibrate((fx,fy,fd),(sx,sy,sd),raw,p["calibration"])
        write_json(directory/"calibration.json",calibration)
        selected = TransitionModel(model,vocabulary,calibration)
        probability = selected.predict(sx)
        diagnostics = []
        cash = np.array([v["cash_fraction"] for v in vocabulary])
        for world in sorted(sd.world.unique()):
            for lo,hi in ((1,1),(2,4),(5,13),(1,13)):
                take = sd.world.eq(world).to_numpy() & sd.week.between(lo,hi).to_numpy()
                diagnostics.append({"world":world,"week_low":lo,"week_high":hi,
                    **guards(probability[take],sy[take],cash,sd.opening.to_numpy()[take],sd.cash_actual.to_numpy()[take])})
        write_csv(directory/"source_conditional_diagnostics.csv",pd.DataFrame(diagnostics))
        quantization["source_recursive_class_replay"] = replay_classes(source_anchors,sk,sd,vocabulary)
        write_json(directory/"discretization.json",quantization)
        meta = {"anchor_budget":budget,"rounds":p["rounds"],"transition_rows":rows,"features":FEATURES,
                "vocabulary":vocabulary,"credit_only_learned":any(v["status"]==3 for v in vocabulary),
                "fit_roles":["train"],"class_weighting":False,"performance":performance,"weights_reused_from":reused_from,
                "model_sha256":sha256_file(directory/"model.txt"),
                "calibration_sha256":sha256_file(directory/"calibration.json"),
                "unsupported_source_calibration_rows":int((fy<0).sum()+(sy<0).sum())}
        write_json(directory/"train.json",meta)
        print(f"ready {budget:,}: {rows:,} transitions, {len(vocabulary)} classes, reused_weights={reused_from is not None}",flush=True)
        del model,raw,selected,probability
        gc.collect()
