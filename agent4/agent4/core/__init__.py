"""Core configuration and trust-boundary contracts for Agent 4."""

from .catalog import DEFAULT_METRICS_DEFINITIONS, MetricCatalog
from .config import AppConfig
from .context import build_auth_context, build_runtime_context, query_intake
from .errors import ContractError, enforce_exact_keys

__all__ = [
    "DEFAULT_METRICS_DEFINITIONS",
    "AppConfig",
    "ContractError",
    "MetricCatalog",
    "build_auth_context",
    "build_runtime_context",
    "enforce_exact_keys",
    "query_intake",
]
