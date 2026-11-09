"""Lossless, fail-closed readers for T0 uploads."""
import csv
import hashlib
import io
import json
import math

import pandas as pd


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Khóa JSON trùng: {key}')
        result[key] = value
    return result


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'Số JSON không hữu hạn: {value}')
    return number


def _constant(value):
    raise ValueError(f'Số JSON không hữu hạn: {value}')


def loads_json(value):
    return json.loads(value, object_pairs_hook=_object, parse_float=_number,
                      parse_constant=_constant)


def source_hash(content):
    return hashlib.sha256(content).hexdigest()


def read_csv(content, filename, *, delimiter=','):
    try:
        stream = io.StringIO(content.decode('utf-8-sig'), newline='')
    except UnicodeDecodeError as exc:
        raise ValueError(f'{filename}: mã hóa CSV phải là UTF-8') from exc
    reader = csv.DictReader(stream, strict=True, delimiter=delimiter)
    try:
        fields = reader.fieldnames
        if not fields or any(not f or not f.strip() for f in fields) or len(fields) != len(set(fields)):
            raise ValueError(f'{filename}: dòng 1: header CSV thiếu, rỗng hoặc trùng')
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()) or list(row.values()) == fields:
                raise ValueError(f'{filename}: dòng {reader.line_num}: số cột sai hoặc lặp header')
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(f'{filename}: dòng {reader.line_num}: CSV không hợp lệ: {exc}') from exc
    frame = pd.DataFrame(rows, columns=fields)
    frame.attrs['source_rows'] = list(range(2, len(frame) + 2))
    return frame


def read_excel(content, filename, *, sheet_name=0):
    # Preserve numeric cell types: converting a binary float to text here would
    # falsely make it look like an exact decimal source amount.
    raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=None, dtype=object, keep_default_na=False)
    if raw.empty:
        raise ValueError(f'{filename}: dòng 1: workbook trống')
    headers = [str(value).strip() for value in raw.iloc[0]]
    if any(not value for value in headers) or len(headers) != len(set(headers)):
        raise ValueError(f'{filename}: dòng 1: header Excel thiếu, rỗng hoặc trùng')
    body = raw.iloc[1:].copy().reset_index(drop=True)
    body.columns = headers
    for index, row in body.iterrows():
        if row.tolist() == headers:
            raise ValueError(f'{filename}: dòng {index + 2}: lặp header')
    body.attrs['source_rows'] = list(range(2, len(body) + 2))
    return body
