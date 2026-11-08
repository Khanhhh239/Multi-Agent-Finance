from src.smoke_test import CHARSET_TEXT, create_fixtures


def test_charset_fixture_contains_required_characters():
    for character in "ăâêôơưĂÂÊÔƠƯấầẩẫậớờởỡợứừửữự":
        assert character in CHARSET_TEXT


def test_fixture_generation_stays_in_workflow():
    records = create_fixtures(blank_count=1)
    assert records[0]["fixture_type"] == "charset"
    assert records[1]["fixture_type"] == "blank"

