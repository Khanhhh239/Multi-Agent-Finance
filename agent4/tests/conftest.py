"""Shared immutable warehouse; never uses the held-out val/test seeds."""
from pathlib import Path
import pytest
from agent4.datagen.build import build
from agent4.engine.engine import ExecutionEngine

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="session")
def warehouse():
    path = ROOT / "data" / "cfo_warehouse.duckdb"
    if not path.exists():
        build(path, seed=20251, quiet=True)
    return path

@pytest.fixture(scope="session")
def engine(warehouse):
    instance = ExecutionEngine(warehouse)
    yield instance
    instance.close()
