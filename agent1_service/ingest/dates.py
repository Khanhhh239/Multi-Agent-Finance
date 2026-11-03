"""Ngày nghiệp vụ Việt Nam: đầu ra timezone-naive, kể cả khi nguồn có offset."""
import pandas as pd
import re


def local_dates(values,dayfirst=True):
    def convert(value):
        # ISO dates in an ERP export are year-first even when other rows use
        # the Vietnamese day/month/year convention.
        iso=isinstance(value,str) and re.match(r'^\d{4}-\d{2}-\d{2}(?:\D|$)',value)
        stamp=pd.to_datetime(value,dayfirst=False if iso else dayfirst,errors='coerce')
        if pd.isna(stamp):return pd.NaT
        if stamp.tzinfo is not None:stamp=stamp.tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
        return stamp.normalize()
    return pd.to_datetime(values.map(convert))
