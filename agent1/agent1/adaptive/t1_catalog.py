"""Portable, hash-verified global T1 models. No implicit local-from-scratch fit."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .compact_t1 import CompactT1, sha256
from .landmark_features import FEATURES, SCHEMA, LandmarkHazard
from .cash_adapter import LABEL_CONTRACT, VERSION as ADAPTER_VERSION, PartialModel, bundle_version
from .bundle_metadata import serving_manifest

DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "outputs/t1/settlement_partial_catalog_v2_20261113/catalog.json"
)
CATALOG_VERSION = "t1-partial-catalog-v2"
CATALOG = [
    ("global_default", "global", "Mô hình nền", "Phiên bản dự phòng có sẵn"),
    ("global_neural", "global", "Neural toàn cục", "Không cập nhật tham số"),
    ("global_lightgbm", "global", "LightGBM toàn cục", "Không cập nhật tham số"),
    ("global_xgboost", "global", "XGBoost toàn cục", "Không cập nhật tham số"),
    ("neural_local", "adaptation", "Neural thích nghi", "Học tiếp từ mô hình nền"),
    ("lightgbm_local", "adaptation", "LightGBM thích nghi", "Học tiếp từ mô hình nền"),
    ("xgboost_local", "adaptation", "XGBoost thích nghi", "Học tiếp từ mô hình nền"),
]


class GlobalCatalog:
    def __init__(self, path=None):
        self.path = Path(
            path or os.environ.get("AGENT1_T1_GLOBAL_CATALOG") or DEFAULT
        ).resolve()
        if not self.path.is_file():
            raise ValueError(
                "Chưa có gói global T1. Cấu hình AGENT1_T1_GLOBAL_CATALOG hoặc chạy scripts/package_t1_global_catalog.py."
            )
        self.metadata = json.loads(self.path.read_text(encoding="utf-8"))
        meta = self.metadata
        if meta.get("label_contract") != LABEL_CONTRACT:
            raise ValueError("Contract nhãn global chưa xác nhận cash-full theo ngày thực thu; đóng gói lại catalog v2")
        if (
            meta.get("version") != CATALOG_VERSION
            or meta.get("feature_schema") != SCHEMA
            or meta.get("features") != list(FEATURES)
        ):
            raise ValueError("Schema gói global T1 không tương thích")
        self.digest = sha256(self.path)
        self.models = {}
        for name in ("default", "neural", "lightgbm", "xgboost"):
            spec = meta["models"][name]
            directory = self.file(spec["directory"])
            if sha256(directory / "metadata.json") != spec["metadata_sha256"]:
                raise ValueError("Hash global T1 không khớp")
            model = CompactT1.load(directory)
            if model.metadata.get("label_contract") != LABEL_CONTRACT:
                raise ValueError("Contract nhãn model global không khớp catalog")
            if model.feature_schema != SCHEMA or tuple(model.feature_names) != FEATURES:
                raise ValueError("Global T1 phải có đủ 18 feature landmark")
            if name != "default" and (
                not isinstance(model, LandmarkHazard) or model.name != name
            ):
                raise ValueError("Sai họ mô hình trong gói global T1")
            self.models[name] = model
        replay = self.file(meta["replay"]["file"])
        if sha256(replay) != meta["replay"]["sha256"]:
            raise ValueError("Replay global T1 đã thay đổi")
        with np.load(replay, allow_pickle=False) as saved:
            self.replay = tuple(saved[k] for k in ("x", "y", "weights"))
        x, y, w = self.replay
        if (
            x.ndim != 2
            or x.shape[1] != 19
            or y.shape != (len(x),)
            or w.shape != y.shape
            or not len(x)
            or not np.isfinite(x).all()
            or not np.isfinite(w).all()
            or (w <= 0).any()
            or not set(np.unique(y)) <= {0, 1}
        ):
            raise ValueError("Replay T1 không hợp lệ")
        spec = meta["partial"]
        path = self.file(spec["file"])
        if sha256(path) != spec["sha256"]:
            raise ValueError("Hash prior partial không khớp")
        self.partial = PartialModel.from_record(json.loads(path.read_text(encoding="utf-8")))
        if (self.partial.version != ADAPTER_VERSION
                or self.partial.evidence.get("label_contract") != LABEL_CONTRACT
                or pd.Timestamp(self.partial.fitted_through) > pd.Timestamp(spec["available_asof"])):
            raise ValueError("Contract/thời điểm prior partial không hợp lệ")

    def file(self, relative):
        candidate = (self.path.parent / relative).resolve()
        if not candidate.is_relative_to(self.path.parent):
            raise ValueError("Đường dẫn global T1 vượt ngoài gói")
        return candidate

    def ready(self, cutoff):
        return max(
            pd.Timestamp(self.metadata["models"][n]["available_asof"])
            for n in self.models
        ) <= pd.Timestamp(cutoff) and pd.Timestamp(
            self.metadata["replay"]["available_asof"]
        ) <= pd.Timestamp(cutoff) and pd.Timestamp(
            self.metadata["partial"]["available_asof"]
        ) <= pd.Timestamp(cutoff)

    def default_bundle(self, cutoff, *, auxiliary=None):
        available = max(self.metadata["models"]["default"]["available_asof"],
                        self.metadata["partial"]["available_asof"])
        if pd.Timestamp(available) > pd.Timestamp(cutoff):
            raise ValueError("Global T1 chưa tồn tại tại ngày dự báo")
        model = self.models["default"]
        version = "global:" + bundle_version(model, self.partial).split(":")[1]
        result = {
            k: auxiliary[k]
            for k in ("risk", "operating", "collection_policy", "collection_evaluation")
            if auxiliary and k in auxiliary
        }
        result.update(
            model=model,
            anchor=model,
            weight=1.0,
            asof=available,
            selected_method="global_default",
            serving_method="global_default",
            selected_weight=0.0,
            algorithm_version="t1-partial-bundle-v2",
            partial=self.partial,
            partial_version=self.partial.digest,
            adapter_version=ADAPTER_VERSION,
            feature_schema=SCHEMA,
            feature_names=list(FEATURES),
            dataset_hash=None,
            t1_version=version,
            t1_parameter_asof=self.metadata["models"]["default"]["available_asof"],
            catalog_sha256=self.digest,
            synthetic_sandbox=bool(self.metadata.get("synthetic")),
            t1_provenance={
                "source": "global_catalog",
                "catalog_sha256": self.digest,
                "metadata_sha256": self.metadata["models"]["default"][
                    "metadata_sha256"
                ],
                "local_adaptation": False,
                "synthetic": bool(self.metadata.get("synthetic")),
            },
            limitation="Global có provenance; chưa có bằng chứng local để thay model. Dải T6 vẫn cần kiểm định riêng.",
        )
        result["serving_manifest"] = serving_manifest(
            result, data_version=self.digest,
            policy={"method": "frozen_global", "catalog_sha256": self.digest}, ready_on=available,
        )
        return result
