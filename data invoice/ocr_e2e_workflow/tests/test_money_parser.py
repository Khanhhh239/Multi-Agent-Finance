import pytest

from src.postprocess.money_parser import parse_money


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("150.000đ", 150000),
        ("150,000 VND", 150000),
        ("150 000", 150000),
        ("Tổng thanh toán: 1.234.567đ", 1234567),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected

