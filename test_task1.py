"""
Test suite for Task 1. Run with: pytest test_task1.py -v

These tests run against the LOCAL FALLBACK data by default (no
Salesforce/Shippo/Gmail credentials required), so they stay green
whether or not real-system setup is finished yet. Once credentials are
set as environment variables, the same functions automatically switch
to live data -- rerun the suite then to sanity-check the live path too.
"""

import pytest
from systems.crm_system import get_crm_commitments
from systems.delivery_system import get_intransit_stock
from systems.email_system import check_supplier_emails
from tools_task1_stock_position import (
    get_warehouse_stock,
    calculate_reorder_timing,
    rank_exposed_accounts,
    get_stock_position,
)


def test_crm_commitments_total_matches_sum_of_accounts():
    result = get_crm_commitments()
    assert result["total_committed_bags"] == sum(a["committed_bags"] for a in result["accounts"])
    assert len(result["accounts"]) == 50


def test_crm_reports_its_source():
    result = get_crm_commitments()
    assert result["source"] in ("salesforce_live", "local_fallback_csv")


def test_intransit_stock_is_non_negative():
    result = get_intransit_stock()
    assert result["total_intransit_bags"] >= 0


def test_intransit_shipments_each_report_a_source():
    result = get_intransit_stock()
    for shipment in result["shipments"]:
        assert shipment["source"] in ("shippo_live", "local_fallback")


def test_supplier_email_delay_flag_is_deterministic():
    result_1 = check_supplier_emails()
    result_2 = check_supplier_emails()
    assert result_1["delay_mentioned"] == result_2["delay_mentioned"]


def test_warehouse_stock_is_positive_and_matches_lot_sum():
    result = get_warehouse_stock()
    assert result["total_bags"] > 0
    assert sum(lot["bags"] for lot in result["lots"]) == result["total_bags"]


def test_warehouse_stock_has_both_hamburg_sites():
    result = get_warehouse_stock()
    assert "Hamburg Main Warehouse" in result["by_site"]
    assert "Hamburg Overflow Facility" in result["by_site"]


def test_reorder_timing_never_returns_negative_days():
    result = calculate_reorder_timing(current_stock_bags=1000)
    if result["days_until_next_order_needed"] is not None:
        assert result["days_until_next_order_needed"] >= 0


def test_reorder_timing_zero_stock_needs_immediate_reorder():
    result = calculate_reorder_timing(current_stock_bags=0)
    assert result["coverage_days"] == 0
    assert result["days_until_next_order_needed"] == 0


def test_rank_exposed_accounts_empty_when_no_shortfall():
    result = rank_exposed_accounts(shortfall_bags=0, accounts=[])
    assert result["accounts_at_risk"] == []


def test_rank_exposed_accounts_covers_the_shortfall():
    accounts = get_crm_commitments()["accounts"]
    result = rank_exposed_accounts(shortfall_bags=100, accounts=accounts)
    total_flagged = sum(a["committed_bags"] for a in result["accounts_at_risk"])
    assert total_flagged >= 100


def test_get_stock_position_status_matches_shortfall_sign():
    result = get_stock_position()
    if result["net_position_bags"] < 0:
        assert result["status"] == "short"
        assert result["shortfall_bags"] == abs(result["net_position_bags"])
    else:
        assert result["status"] == "enough"
        assert result["shortfall_bags"] == 0


def test_get_stock_position_reasoning_field_exists_and_is_a_string():
    result = get_stock_position()
    assert isinstance(result["reasoning"], str)
    assert len(result["reasoning"]) > 20


def test_get_stock_position_accounts_at_risk_empty_iff_enough_stock():
    result = get_stock_position()
    if result["status"] == "enough":
        assert result["accounts_at_risk"] == []
    else:
        assert len(result["accounts_at_risk"]) > 0


def test_get_stock_position_reports_source_for_each_swapped_system():
    result = get_stock_position()
    assert result["crm_source"] in ("salesforce_live", "local_fallback_csv")
    assert result["supplier_email_source"] in ("gmail_live", "local_fallback_csv")


def test_rank_exposed_accounts_includes_zero_bag_commitment():
    """A cafe committed to 0 bags contributes nothing to closing the
    shortfall, but the ranking logic doesn't skip it -- it still gets
    included if it's next in priority order. Documenting this as real
    behavior, not assuming it's a bug."""
    accounts = [
        {"cafe_name": "Zero Bags Cafe", "contract_priority": "Low", "committed_bags": 0, "monthly_revenue_eur": 100},
        {"cafe_name": "Real Cafe", "contract_priority": "Low", "committed_bags": 50, "monthly_revenue_eur": 200},
    ]
    result = rank_exposed_accounts(shortfall_bags=50, accounts=accounts)
    names = [a["cafe_name"] for a in result["accounts_at_risk"]]
    assert "Zero Bags Cafe" in names
    assert "Real Cafe" in names


def test_rank_exposed_accounts_handles_duplicate_cafe_names():
    """Two accounts with the identical cafe_name are treated as
    separate entries, not merged or deduplicated."""
    accounts = [
        {"cafe_name": "Duplicate Cafe", "contract_priority": "Low", "committed_bags": 30, "monthly_revenue_eur": 100},
        {"cafe_name": "Duplicate Cafe", "contract_priority": "Low", "committed_bags": 40, "monthly_revenue_eur": 150},
    ]
    result = rank_exposed_accounts(shortfall_bags=50, accounts=accounts)
    assert len(result["accounts_at_risk"]) == 2


def test_rank_exposed_accounts_shortfall_exceeds_all_available_accounts():
    """If the shortfall is bigger than every account combined could
    ever cover, the function returns every account it has rather than
    crashing or looping forever."""
    accounts = [
        {"cafe_name": "Only Cafe", "contract_priority": "Low", "committed_bags": 10, "monthly_revenue_eur": 100},
    ]
    result = rank_exposed_accounts(shortfall_bags=1000, accounts=accounts)
    assert result["accounts_at_risk"] == accounts
