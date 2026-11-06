"""Immutable source/cache lifecycle. Existing Worlds and model versions are read-only."""
from __future__ import annotations

import gc
import importlib.metadata
import json
from pathlib import Path
import platform
import zipfile

import numpy as np
import pandas as pd

from agent1.paths import ROOT,SYNTH
from agent1.data.world_manifest import load_cohort,sha256_file
from experiments.t1_competing_v6.run import write_json,write_csv,write_bytes_once,write_parquet
from .lifecycle import protected_files as old_protected
from .core import LabelIndex,observed_rows
from .features import SnapshotBuilder,model_view
from .randomness import generator

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE/"protocol.json"


def source_hashes():
    files = list(HERE.glob("*.py"))+[PROTOCOL,HERE/"README.md"]
    files += [ROOT/"tests"/name for name in ("test_unified_collection_v2.py", "test_unified_collection_core.py", "test_unified_collection_artifacts.py")]
    for base in ("agent1","experiments/t1_competing_v6","experiments/t1_competing_v5"):
        files += list((ROOT/base).rglob("*.py"))
    files += list((HERE/"fixtures").rglob("*"))
    files = [f for f in files if f.is_file() and "__pycache__" not in f.parts]
    return {f.relative_to(ROOT).as_posix():sha256_file(f) for f in sorted(set(files))}


def protected_files(exclude=None):
    before = old_protected()
    current = (Path(exclude) if exclude is not None else ROOT/read_json(PROTOCOL)["output_directory"]).resolve()
    directories = list((ROOT/"outputs/data").glob("unified_collection_v2_*"))
    for directory in directories:
        if directory.resolve()==current:
            continue
        for f in directory.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                before[f.relative_to(ROOT).as_posix()] = sha256_file(f)
    return dict(sorted(before.items()))


def prepare(p):
    out = (ROOT/p["output_directory"]).resolve()
    if out.parent!=(ROOT/"outputs/data").resolve() or not out.name.startswith("unified_collection_v2_"):
        raise ValueError("v2 must have its own versioned output")
    if (out/"source_hashes.json").exists() and source_hashes()!=read_json(out/"source_hashes.json"):
        raise ValueError("Frozen run source differs; use --stage saved to inspect it or choose a new output/version")
    cohort = load_cohort(ROOT/p["source_cohort"])
    validate_timeline(p,read_json(ROOT/p["v6_directory"]/"protocol.lock.json"))
    raw = json.loads((ROOT/"data/raw/MANIFEST.json").read_text(encoding="utf-8"))
    for value in raw.values():
        for file in value["files"]:
            if sha256_file(ROOT/"data/raw"/file["path"])!=file["sha256"]:
                raise ValueError("Changed raw input")
    write_json(out/"protocol.lock.json",p)
    write_json(out/"source_hashes.json",source_hashes())
    write_json(out/"preservation_before.json",protected_files(out))
    write_json(out/"environment.json",{"python":platform.python_version(),"packages":{n:importlib.metadata.version(n) for n in ("numpy","pandas","lightgbm","scipy","pyarrow","pytest")}})
    if not (out/"source_snapshot.zip").exists():
        with zipfile.ZipFile(out/"source_snapshot.zip","x",compression=zipfile.ZIP_DEFLATED) as z:
            for name in source_hashes():
                z.write(ROOT/name,name)
    if p.get("reuse_expanded_cache_from"):
        prior = (ROOT/p["reuse_expanded_cache_from"]).resolve()
        if prior.parent!=(ROOT/"outputs/data").resolve() or prior==out or not prior.name.startswith("unified_collection_v2_"):
            raise ValueError("Cache reuse must name a different versioned v2 output")
        old = read_json(prior/"protocol.lock.json")
        for name in ("source_cohort","seed","train_label_end","calibration_fit_cutoffs","partial_fraction_edges"):
            if old[name]!=p[name]:
                raise ValueError("Expanded cache protocol differs")
        reused = {}
        if not (out/"cache_reuse.json").exists():
            for manifest in sorted((prior/"cache").glob("*.json")):
                if p.get("cache_reuse_partitions") and not any(manifest.name.startswith(name+"_") for name in p["cache_reuse_partitions"]):
                    continue
                detail = read_json(manifest)
                for name,digest in detail["hashes"].items():
                    source = prior/"cache"/name
                    if sha256_file(source)!=digest:
                        raise ValueError("Prior expanded cache changed")
                    write_bytes_once(out/"cache"/name,source.read_bytes())
                write_bytes_once(out/"cache"/manifest.name,manifest.read_bytes())
                reused[manifest.name] = sha256_file(manifest)
            write_json(out/"cache_reuse.json",{"source":p["reuse_expanded_cache_from"],"source_protocol_sha256":sha256_file(prior/"protocol.lock.json"),
                                               "manifests":reused,"scope":"immutable labeled input caches only; model weights refitted"})
    return out,cohort


def validate_timeline(p,baseline_protocol):
    source_start = pd.Timestamp(min(p["source_selection_cutoffs"]))
    source_end = pd.Timestamp(max(p["source_selection_cutoffs"]))+pd.Timedelta(days=91)
    if pd.Timestamp(baseline_protocol["train_label_end"])>source_start:
        raise ValueError("Fixed baseline was trained on outcomes after source-selection origin")
    if source_end>pd.Timestamp(min(p["evaluation_cutoffs"])) or source_end>pd.Timestamp(p["source_label_end"]):
        raise ValueError("Source selection outcomes are unavailable at the first confirmatory origin")
    if pd.Timestamp(p["t4"]["fit_end"])>pd.Timestamp(min(p["evaluation_cutoffs"]+p["bank_diagnostic_cutoffs"])):
        raise ValueError("T4 training extends beyond a bank forecast origin")
    if pd.Timestamp(max(p["calibration_fit_cutoffs"]))+pd.Timedelta(days=91)>source_start:
        raise ValueError("Calibration outcomes overlap source selection")


def read_json(file):
    return json.loads(Path(file).read_text(encoding="utf-8"))


def world_tables(world):
    return {name:pd.read_parquet(SYNTH/world/f"{name}.parquet") for name in
            ("invoices","payments","promises","bank_txns","outflows","daily_cash")}


def old_source(entry,p):
    if entry["role"]!="train":
        raise ValueError("Only train Worlds can supply fit/calibration data")
    file = ROOT/p["v6_directory"]/"cache"/f"train_{entry['name']}.parquet"
    if sha256_file(file)!=read_json(file.with_suffix(".json"))["cache_sha256"]:
        raise ValueError("Changed v6 source anchor cache")
    return pd.read_parquet(file)


def nested_sample(frame,cap,seed,world):
    groups = list(frame.groupby("firm_id",sort=True))
    if len(frame)<=cap:
        return frame.reset_index(drop=True)
    ids,ranks,firm_order = [],[],[]
    for number,(fid,g) in enumerate(groups):
        order = generator(seed,world,f"anchor_order:{fid}").permutation(g.index.to_numpy())
        ids.append(order)
        ranks.append(np.arange(len(order)))
        firm_order.append(np.full(len(order),number))
    ids,ranks,firm_order = map(np.concatenate,(ids,ranks,firm_order))
    chosen = ids[np.lexsort((firm_order,ranks))[:cap]]
    return frame.loc[chosen].sort_index().reset_index(drop=True)


def save_expanded(base,result):
    x,keys,pairs,detail = result
    base.parent.mkdir(parents=True,exist_ok=True)
    hashes = {}
    anchors = base.with_name(base.name+"_anchors.parquet")
    hashes[anchors.name] = sha256_file(anchors)
    for name,value in (("x",x),("keys",keys),("pairs",pairs)):
        file = base.with_name(base.name+f"_{name}.npy")
        with file.open("xb") as stream:
            np.save(stream,value,allow_pickle=False)
        hashes[file.name] = sha256_file(file)
    file = base.with_name(base.name+"_detail.parquet")
    write_parquet(file,detail)
    hashes[file.name] = sha256_file(file)
    write_json(base.with_suffix(".json"),{"rows":len(x),"hashes":hashes})


def load_expanded(base):
    meta = read_json(base.with_suffix(".json"))
    if any(sha256_file(base.parent/name)!=value for name,value in meta["hashes"].items()):
        raise ValueError("Expanded cache hash mismatch")
    values = [np.load(base.with_name(base.name+f"_{n}.npy"),mmap_mode="r",allow_pickle=False) for n in ("x","keys","pairs")]
    return (*values,pd.read_parquet(base.with_name(base.name+"_detail.parquet")))


def build_caches(out,cohort,p):
    for entry in cohort["worlds"]:
        if entry["role"]!="train":
            continue
        world = entry["name"]
        bases = [out/"cache"/f"{name}_{world}" for name in ("fit","calibration_fit","calibration_select")]
        if all(base.with_suffix(".json").exists() for base in bases):
            continue
        old = old_source(entry,p)
        tables = world_tables(world)
        inv,pay = tables["invoices"],tables["payments"]
        label = LabelIndex(inv,pay)
        builder = SnapshotBuilder(inv,pay,tables["promises"])
        for name,base in zip(("fit","calibration_fit","calibration_select"),bases):
            if base.with_suffix(".json").exists():
                continue
            if name=="fit":
                frame = old[old.partition.eq("fit")].copy().reset_index(drop=True)
                if frame.cutoff.max()+pd.Timedelta(days=91)>=pd.Timestamp(min(p["calibration_fit_cutoffs"])):
                    raise ValueError("Training outcomes overlap calibration origin")
            else:
                firms = old.loc[old.partition.eq(name),"firm_id"].unique()
                cutoffs = p["calibration_fit_cutoffs"] if name=="calibration_fit" else p["source_selection_cutoffs"]
                frames = []
                for cutoff in map(pd.Timestamp,cutoffs):
                    snap = builder.snapshot(cutoff,firms=firms)
                    if len(snap):
                        frames.append(model_view(snap,cutoff))
                frame = pd.concat(frames,ignore_index=True)
                frame["partition"] = name
                frame["world"] = world
            write_parquet(base.with_name(base.name+"_anchors.parquet"),frame)
            label_end = p["source_label_end"] if name=="calibration_select" else p["train_label_end"]
            result = observed_rows(frame,label,label_end,p["partial_fraction_edges"])
            save_expanded(base,result)
            print(f"cache {name} {world}: {len(frame):,} anchors, {len(result[0]):,} transitions",flush=True)
            del result,frame
            gc.collect()
        del tables,builder,label,old
        gc.collect()


def dataset(out,cohort,p,partition,budget=None):
    parts = [[],[],[],[]]
    for entry in cohort["worlds"]:
        if entry["role"]!="train":
            continue
        base = out/"cache"/f"{partition}_{entry['name']}"
        values = load_expanded(base)
        if partition=="fit":
            frame = pd.read_parquet(base.with_name(base.name+"_anchors.parquet"))
            selected = nested_sample(frame,budget//4,p["seed"],entry["name"])
            lookup = pd.MultiIndex.from_frame(selected[["invoice_id","cutoff"]])
            keep = pd.MultiIndex.from_frame(values[3][["invoice_id","cutoff"]]).isin(lookup)
        else:
            keep = np.ones(len(values[0]),dtype=bool)
        for i,value in enumerate(values):
            parts[i].append(value.loc[keep].copy() if i==3 else np.asarray(value[keep]))
    return tuple(pd.concat(v,ignore_index=True) if i==3 else np.concatenate(v) for i,v in enumerate(parts))


def verify_preserved(out):
    after = protected_files(out)
    if after!=read_json(out/"preservation_before.json") or source_hashes()!=read_json(out/"source_hashes.json"):
        raise ValueError("Protected artifacts or locked source changed")
    write_json(out/"preservation_after.json",after)
    return {"protected_files":len(after),"protected_files_unchanged":True,"locked_source_unchanged":True}
