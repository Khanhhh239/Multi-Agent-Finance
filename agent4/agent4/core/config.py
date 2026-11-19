"""Deterministic application configuration for the core pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_WAREHOUSE_DIR = Path("data/enterprise-x10-v3")


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _selection_config_path() -> Path:
    return Path(
        os.getenv("AGENT4_SELECTION_CONFIG")
        or os.getenv("AGENT4_METRIC_SELECTION_CONFIG")
        or "config/selection.yaml"
    )


@dataclass(frozen=True)
class AppConfig:
    """Server-owned configuration shared by deterministic pipeline stages."""

    db_path: Path = field(
        default_factory=lambda: _env_path("AGENT4_DB", str(_WAREHOUSE_DIR / "warehouse.duckdb"))
    )
    ground_truth_path: Path = field(
        default_factory=lambda: _env_path(
            "AGENT4_GROUND_TRUTH", str(_WAREHOUSE_DIR / "warehouse_ground_truth.json")
        )
    )
    selection_config_path: Path = field(default_factory=_selection_config_path)
    max_question_length: int = field(
        default_factory=lambda: _env_int("AGENT4_MAX_QUESTION_LENGTH", 500)
    )
    default_row_cap: int = field(default_factory=lambda: _env_int("AGENT4_DEFAULT_ROW_CAP", 1000))
    query_timeout_ms: int = field(default_factory=lambda: _env_int("AGENT4_QUERY_TIMEOUT_MS", 5000))
    reporting_data_watermark: str | None = field(
        default_factory=lambda: os.getenv("AGENT4_REPORTING_DATA_WATERMARK")
    )
    reporting_last_closed_month: str | None = field(
        default_factory=lambda: os.getenv("AGENT4_REPORTING_LAST_CLOSED_MONTH")
    )

    def __post_init__(self) -> None:
        if self.max_question_length <= 0:
            raise ValueError("max_question_length must be positive")
        if self.default_row_cap <= 0:
            raise ValueError("default_row_cap must be positive")
        if self.query_timeout_ms <= 0:
            raise ValueError("query_timeout_ms must be positive")
