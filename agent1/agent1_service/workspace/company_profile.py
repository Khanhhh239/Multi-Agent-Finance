"""Read the portal's per-firm import settings without accepting another firm's profile."""

import json
import os
from pathlib import Path

from fastapi import HTTPException


DATE_FORMATS = {"dmy": "%d/%m/%Y", "iso": "%Y-%m-%d"}


def company_profile(firm):
    profile = dict(code=firm, date_format="dmy", number_format="vi-VN", managed=False)
    filename = os.environ.get("AGENT1_COMPANY_PROFILE_FILE")
    if not filename:
        return profile
    try:
        data = json.loads(Path(filename).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Profile must be an object")
        if data.get("code") != firm:
            raise HTTPException(409, "Hồ sơ không khớp mã doanh nghiệp đã kết nối. Mở lại Agent 1 từ workspace tổng.")
        if data.get("date_format") not in DATE_FORMATS or data.get("number_format") not in ("vi-VN", "plain"):
            raise ValueError("Unsupported import format")
        return dict(code=firm, date_format=data["date_format"], number_format=data["number_format"], managed=True)
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "Không đọc được cấu hình doanh nghiệp. Kiểm tra lại hồ sơ ở workspace tổng.") from None


def import_formats(profile, date_format=None, number_format=None):
    expected_date = DATE_FORMATS[profile["date_format"]]
    expected_number = profile["number_format"]
    date_format = expected_date if date_format is None else date_format
    number_format = expected_number if number_format is None else number_format
    if profile["managed"] and (date_format != expected_date or number_format != expected_number):
        raise HTTPException(409, "Định dạng tệp không khớp hồ sơ doanh nghiệp. Tải lại cấu hình rồi kiểm tra file lại.")
    if date_format not in (*DATE_FORMATS.values(), "%d-%m-%y") or number_format not in ("vi-VN", "plain"):
        raise HTTPException(422, "Định dạng ngày hoặc số tiền không hợp lệ.")
    return date_format, number_format
