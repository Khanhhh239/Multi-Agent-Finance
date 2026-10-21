"""Bộ quy tắc có ngày hiệu lực và trạng thái xác minh tách khỏi phép tính."""
from functools import lru_cache
import json
from pathlib import Path
import pandas as pd


@lru_cache(maxsize=1)
def all_rules():
    return json.loads((Path(__file__).parent / 'rules_history.json').read_text(encoding='utf-8'))


def load_rules(date, strict=False):
    date = pd.Timestamp(date)
    active = [r for r in all_rules() if date >= pd.Timestamp(r['effective_from']) and
              (r['effective_to'] is None or date <= pd.Timestamp(r['effective_to']))]
    if strict and any(not r['verified'] for r in active):
        raise ValueError('Quy tắc chưa được chuyên gia xác minh')
    result = {r['kind']: r['value'] for r in active}
    result['unverified_rules'] = [r['kind'] for r in active if not r['verified']]
    return result
