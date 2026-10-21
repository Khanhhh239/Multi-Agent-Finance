"""Ngày nghiệp vụ Việt Nam: đầu ra timezone-naive, kể cả khi nguồn có offset."""
import pandas as pd


def local_dates(values,dayfirst=True):
    def convert(value):
        stamp=pd.to_datetime(value,dayfirst=dayfirst,errors='coerce')
        if pd.isna(stamp):return pd.NaT
        if stamp.tzinfo is not None:stamp=stamp.tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
        return stamp.normalize()
    return pd.to_datetime(values.map(convert))
