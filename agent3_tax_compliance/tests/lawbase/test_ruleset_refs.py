"""Every legal basis of the assistant ruleset opens a provision that is in force on the days the rule is used.
Runs against the synced corpus; skipped on a machine that has not synced it."""
from datetime import date

import pytest

from src.lawbase.check_refs import check
from src.lawbase.sync import DEFAULT_DB, DEFAULT_RULESET


@pytest.mark.skipif(not DEFAULT_DB.exists(), reason='kho luật chưa đồng bộ trên máy này')
def test_ruleset_references_resolve_in_the_corpus():
    rows = check(DEFAULT_RULESET, DEFAULT_DB, date(2026, 11, 5))
    broken = [r for r in rows if r['ok'] is False]
    assert not broken, broken
    assert sum(r['ok'] is True for r in rows) >= 10
