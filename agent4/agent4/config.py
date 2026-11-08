"""Central configuration for Agent 4 (CFO ảo).

Everything that changes between a developer laptop, the eval harness and a
demo is read from environment variables here, so that no module hard-codes a
path, a model name or "today".
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = Path(os.getenv("AGENT4_DATA_DIR", PROJECT_DIR / "data"))

# The synthetic company's books run from DATA_START to AS_OF_DATE (inclusive).
# AS_OF_DATE is the "data cut-off" the agent reasons from ("tháng này", "hiện
# tại"...).  It is fixed rather than date.today() so the eval set is
# reproducible; override with AGENT4_AS_OF for a live demo.
DATA_START = date(2025, 1, 1)
AS_OF_DATE = date.fromisoformat(os.getenv("AGENT4_AS_OF", "2026-10-14"))
# Months up to and including this one have been closed (khóa sổ).  Later
# months are "chưa khóa sổ" and every answer about them is labelled tạm tính.
LAST_CLOSED_MONTH = os.getenv("AGENT4_LAST_CLOSED_MONTH", "2026-08")


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = os.getenv("AGENT4_LLM_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("AGENT4_LLM_MODEL", "qwen3:8b")
    temperature: float = float(os.getenv("AGENT4_LLM_TEMPERATURE", "0"))
    num_ctx: int = int(os.getenv("AGENT4_LLM_NUM_CTX", "8192"))
    # Qwen3 hybrid thinking: off by default — tool routing is narrowed by the
    # retriever so the extra latency of <think> rarely pays off (see eval).
    think: bool = os.getenv("AGENT4_LLM_THINK", "0") == "1"
    timeout_s: float = float(os.getenv("AGENT4_LLM_TIMEOUT", "180"))
    max_steps: int = int(os.getenv("AGENT4_MAX_STEPS", "5"))


@dataclass(frozen=True)
class Settings:
    warehouse_path: Path = Path(os.getenv("AGENT4_DB", DATA_DIR / "cfo_warehouse.duckdb"))
    ops_path: Path = Path(os.getenv("AGENT4_OPS_DB", DATA_DIR / "cfo_ops.duckdb"))
    as_of: date = AS_OF_DATE
    last_closed_month: str = LAST_CLOSED_MONTH
    llm: LLMConfig = field(default_factory=LLMConfig)


def get_settings() -> Settings:
    return Settings()
