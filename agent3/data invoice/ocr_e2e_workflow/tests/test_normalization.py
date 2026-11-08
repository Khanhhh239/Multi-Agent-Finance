from src.postprocess.text_normalizer import accent_insensitive, normalize_text


def test_unicode_and_whitespace_normalization():
    assert normalize_text("  Tổng   tiền  ") == "Tổng tiền"


def test_accent_insensitive_is_diagnostic():
    assert accent_insensitive("Địa chỉ") == "đia chi"

