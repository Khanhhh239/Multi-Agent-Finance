from decimal import Decimal

import pytest

from agent4.text2sql.models import make_query_request


def scalar(service, auth, question, metric):
    response = service.query(make_query_request(question), auth)
    assert response.status == "ready", response
    return Decimal(response.data.rows[0][metric])


def test_f01_net_revenue_excludes_opening_and_closing(finance_service, auth):
    assert scalar(finance_service, auth, "Doanh thu thuần tháng 10/2026", "net_revenue") == Decimal(
        90
    )


@pytest.mark.parametrize(
    ("question", "metric", "expected"),
    [
        ("Doanh thu trước giảm trừ tháng 10/2026", "gross_revenue", Decimal(100)),
        ("Giảm trừ doanh thu tháng 10/2026", "revenue_deductions", Decimal(10)),
        ("Giá vốn tháng 10/2026", "cogs", Decimal(60)),
        ("Chi phí hoạt động tháng 10/2026", "operating_expenses", Decimal(15)),
        ("Lợi nhuận hoạt động tháng 10/2026", "operating_profit", Decimal(15)),
        ("Lợi nhuận trước thuế tháng 10/2026", "profit_before_tax", Decimal(15)),
        ("Chi phí thuế TNDN tháng 10/2026", "income_tax_expense", Decimal(4)),
        ("Biên lợi nhuận ròng tháng 10/2026", "net_margin_pct", Decimal("12.2222222222")),
        ("Dòng tiền thuần tháng 10/2026", "net_cash_flow", Decimal(45)),
    ],
)
def test_finance_catalog_values(finance_service, auth, question, metric, expected):
    assert scalar(finance_service, auth, question, metric) == expected


def test_f04_gross_profit(finance_service, auth):
    assert scalar(finance_service, auth, "Lợi nhuận gộp tháng 10/2026", "gross_profit") == Decimal(
        30
    )


def test_f05_gross_margin_is_ratio_of_sums(finance_service, auth):
    actual = scalar(finance_service, auth, "Biên lợi nhuận gộp tháng 10/2026", "gross_margin_pct")
    assert actual == Decimal("33.3333333333")


def test_f07_net_profit(finance_service, auth):
    assert scalar(
        finance_service, auth, "Lợi nhuận sau thuế tháng 10/2026", "net_profit"
    ) == Decimal(11)


def test_f09_cash_snapshot_includes_opening(finance_service, auth):
    assert scalar(
        finance_service, auth, "Số dư tiền cuối tháng 10/2026", "cash_and_equivalents"
    ) == Decimal(1045)


def test_f10_ar_snapshot(finance_service, auth):
    assert scalar(finance_service, auth, "Phải thu ngày 31/10/2026", "ar_balance") == Decimal(10)


def test_zero_denominator_returns_null_with_warning(finance_service, auth):
    response = finance_service.query(make_query_request("Biên lợi nhuận gộp tháng 9/2026"), auth)
    assert response.status == "ready"
    assert response.data.rows[0]["gross_margin_pct"] is None
    assert any("mẫu số" in warning for warning in response.warnings)


def test_no_eligible_rows_is_no_data_not_fabricated_zero(finance_service, auth):
    response = finance_service.query(make_query_request("Doanh thu thuần tháng 9/2026"), auth)
    assert response.status == "no_data"
    assert response.data is None
    assert "Không có dữ liệu" in response.answer


def test_verified_month_grouping_uses_additive_flow(finance_service, auth):
    response = finance_service.query(
        make_query_request("Doanh thu thuần theo tháng quý 4/2026"), auth
    )
    assert response.status == "ready"
    assert response.data.rows == [{"month": "2026-10", "net_revenue": "90.00"}]
