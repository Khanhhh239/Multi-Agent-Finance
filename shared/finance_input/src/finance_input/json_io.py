"""Strict JSON transport parsing, shared by backend policy and input adapters."""
import json


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("JSON có khóa lặp; xuất lại dữ liệu với mỗi trường đúng một lần.")
        value[key] = item
    return value


def _constant(_value):
    raise ValueError("JSON không được chứa NaN hoặc Infinity; dùng null cho dữ liệu chưa biết.")


def loads(raw):
    """Keep integers exact; do not accept duplicate keys or non-JSON constants."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    return json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
