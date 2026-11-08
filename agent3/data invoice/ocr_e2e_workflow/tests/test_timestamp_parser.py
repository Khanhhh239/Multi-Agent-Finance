import pytest

from src.postprocess.timestamp_parser import parse_timestamp


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15/08/2020 10:44:08", "2020-08-15T10:44:08"),
        ("10:44:08-15/08/2020", "2020-08-15T10:44:08"),
        ("Ngày 1-2-24", "2024-02-01T00:00:00"),
    ],
)
def test_parse_timestamp(text, expected):
    assert parse_timestamp(text) == expected

