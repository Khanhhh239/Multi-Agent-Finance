"""Cổng đối chiếu mọi token số, kể cả số phần trăm; không gọi LLM trong CI."""
import math
import numbers
import re

NUMBER = re.compile(r'[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?%?')


def _allowed_tokens(value):
    if hasattr(value, 'to_dict'):
        value = value.to_dict()
    if isinstance(value, dict):
        return set().union(*(_allowed_tokens(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_allowed_tokens(v) for v in value)) if value else set()
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        if not math.isfinite(value):
            return set()
        forms = {str(value), format(value, 'g')}
        if float(value).is_integer():
            forms |= {str(int(value)), format(int(value), ','), format(int(value), ',').replace(',', '.')}
        return forms
    return set(NUMBER.findall(str(value)))


def check_numbers(text, table):
    """Đúng khi mọi token số xuất hiện nguyên vẹn trong bảng; không chấp nhận khớp chuỗi con."""
    allowed = _allowed_tokens(table)
    return all(token in allowed for token in NUMBER.findall(text))


def verbalize(table, llm=None):
    """Đầu vào đã có chuỗi hiển thị để tránh tự ý làm tròn/sinh đơn vị."""
    if llm is not None:
        text = llm(table)
    else:
        text = f"Tuần {table['week']}: số dư trung vị {table['balance_text']} VND; xác suất thiếu hụt {table['risk_text']}."
    if not check_numbers(text, table):
        raise ValueError('Văn bản có số không nằm trong bảng tính toán')
    return text
