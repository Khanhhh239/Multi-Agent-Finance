"""Real record availability and tenant boundaries for the B2B input adapter."""
import pandas as pd
import pytest

from experiments.t1_credit_context.practical import PRACTICAL_CONTEXT_FEATURES, practical_context_features


def keys():
    return pd.DataFrame({"firm_id": ["seller-a", "seller-b", "seller-a"],
                         "customer_id": ["same-tax-id"] * 3,
                         "cutoff": ["2024-04-01", "2024-05-01", "2024-05-01"]}, index=[8, 3, 20])


def buyer():
    return pd.DataFrame({"firm_id": ["seller-a"], "customer_id": ["same-tax-id"],
                         "industry": ["services"], "known_at": ["2024-04-15"],
                         "source_kind": ["customer_master"], "source_ref": ["crm/customer/17/version/1"]})


def test_no_sources_means_unknown_and_no_invented_macro():
    result = practical_context_features(keys())
    assert list(result) == PRACTICAL_CONTEXT_FEATURES
    assert len(result.columns) == 14
    assert not any(name.startswith("macro_") for name in result)
    assert result.buyer_industry_unknown.eq(1).all()
    assert result.seller_industry_unknown.eq(1).all()
    assert result.index.tolist() == [8, 3, 20]


def test_actual_knowledge_date_and_tenant_scope_are_both_required():
    result = practical_context_features(keys(), buyer_observations=buyer())
    assert result.buyer_industry_services.tolist() == [0, 0, 1]
    assert result.buyer_industry_unknown.tolist() == [1, 1, 0]


def test_later_reclassification_does_not_change_past_features():
    revision = buyer().assign(industry="wholesale", known_at="2024-04-28", source_ref="crm/customer/17/version/2")
    records = pd.concat([buyer(), revision], ignore_index=True)
    query = keys().iloc[[0, 2]].copy()
    query["cutoff"] = ["2024-04-20", "2024-05-01"]
    result = practical_context_features(query, buyer_observations=records)
    assert result.buyer_industry_services.tolist() == [1, 0]
    assert result.buyer_industry_wholesale.tolist() == [0, 1]


@pytest.mark.parametrize("change", ["missing_date", "missing_ref", "synthetic", "extra_truth", "duplicate"])
def test_unsubstantiated_or_latent_records_are_rejected(change):
    records = buyer()
    if change == "missing_date":
        records["known_at"] = None
    elif change == "missing_ref":
        records["source_ref"] = ""
    elif change == "synthetic":
        records["source_kind"] = "synthetic_world"
    elif change == "extra_truth":
        records["credit_exposure"] = 2.
    else:
        records = pd.concat([records, records], ignore_index=True)
    with pytest.raises(ValueError):
        practical_context_features(keys(), buyer_observations=records)


def test_unmapped_industry_stays_unknown_and_seller_is_own_profile():
    records = buyer().assign(industry="unmapped-vsic-code")
    seller = pd.DataFrame({"firm_id": ["seller-a"], "industry": ["steel_metals"],
                           "known_at": ["2024-01-01"], "source_kind": ["own_company_profile"],
                           "source_ref": ["onboarding/profile/version/1"]})
    result = practical_context_features(keys(), buyer_observations=records, seller_observations=seller)
    assert result.buyer_industry_unknown.eq(1).all()
    assert result.seller_industry_steel_metals.tolist() == [1, 0, 1]
    for side in ("buyer", "seller"):
        assert result.filter(like=f"{side}_industry_").sum(axis=1).eq(1).all()


def test_import_date_is_not_assumed_to_be_first_invoice_date():
    records = buyer().assign(known_at="2026-11-05")
    result = practical_context_features(keys(), buyer_observations=records)
    assert result.buyer_industry_unknown.eq(1).all()
