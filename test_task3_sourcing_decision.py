"""
Test suite for Task 3's sourcing decision workflow. Run with:
pytest test_task3_sourcing_decision.py -v
"""

from tools_task3_sourcing_decision import (
    check_contract_compliance,
    check_backup_compliance,
    check_payment_timing,
    check_sourcing_concentration,
    get_sourcing_decision,
)


def test_contract_compliance_flags_minimum_volume_clause():
    result = check_contract_compliance("Minas Gerais Cooperative", "Sao Paulo Cooperative (backup)")
    assert result["can_switch"] is False
    assert "minimum" in result["reasoning"].lower()


def test_contract_compliance_none_for_unknown_supplier():
    result = check_contract_compliance("Nonexistent Supplier", "Sao Paulo Cooperative (backup)")
    assert result["can_switch"] is None


def test_backup_compliance_has_required_fields():
    result = check_backup_compliance("Sao Paulo Cooperative (backup)")
    assert "origin_region" in result
    assert "compliant" in result
    assert "reasoning" in result


def test_backup_compliance_unknown_supplier():
    result = check_backup_compliance("Some Random Supplier")
    assert result["origin_region"] is None
    assert result["compliant"] is None


def test_payment_timing_detects_upfront_requirement():
    result = check_payment_timing("Sao Paulo Cooperative (backup)")
    assert result["requires_upfront_cash"] is True


def test_payment_timing_no_upfront_for_delayed_terms():
    result = check_payment_timing("Minas Gerais Cooperative")
    assert result["requires_upfront_cash"] is False


def test_sourcing_concentration_percentages_sum_to_100():
    result = check_sourcing_concentration()
    total_pct = sum(result["concentration_by_region"].values())
    assert abs(total_pct - 100) < 0.5


def test_sourcing_concentration_flags_high_reliance():
    result = check_sourcing_concentration()
    if result["top_region_pct"] >= 70:
        assert result["high_concentration_risk"] is True
    else:
        assert result["high_concentration_risk"] is False


def test_get_sourcing_decision_has_all_required_fields():
    result = get_sourcing_decision()
    for field in ("current_supplier", "backup_supplier", "contract_compliance",
                  "backup_compliance", "payment_timing", "sourcing_concentration",
                  "recommend_switch", "summary"):
        assert field in result


def test_recommend_switch_is_boolean():
    result = get_sourcing_decision()
    assert isinstance(result["recommend_switch"], bool)


def test_summary_is_a_non_empty_string():
    result = get_sourcing_decision()
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 20


def test_recommend_switch_false_when_contract_blocks_it():
    result = get_sourcing_decision("Minas Gerais Cooperative", "Sao Paulo Cooperative (backup)")
    if result["contract_compliance"]["can_switch"] is False:
        assert result["recommend_switch"] is False


from unittest.mock import patch


def test_sourcing_concentration_exactly_at_70_percent_boundary():
    """high_concentration_risk uses >= 70, not > 70 -- exactly 70% must
    still be flagged as high concentration, not treated as just under
    the line."""
    fake_purchases = {"purchases": [
        {"origin_region": "Minas Gerais", "bags_purchased": 700},
        {"origin_region": "Sao Paulo", "bags_purchased": 300},
    ]}
    with patch("tools_task3_sourcing_decision.get_purchase_history", return_value=fake_purchases):
        result = check_sourcing_concentration()

    assert result["top_region_pct"] == 70.0
    assert result["high_concentration_risk"] is True


def test_sourcing_concentration_just_under_70_percent_not_flagged():
    """One bag below the 70% line should NOT be flagged -- confirms
    the boundary is exact, not fuzzy in either direction."""
    fake_purchases = {"purchases": [
        {"origin_region": "Minas Gerais", "bags_purchased": 699},
        {"origin_region": "Sao Paulo", "bags_purchased": 301},
    ]}
    with patch("tools_task3_sourcing_decision.get_purchase_history", return_value=fake_purchases):
        result = check_sourcing_concentration()

    assert result["top_region_pct"] < 70.0
    assert result["high_concentration_risk"] is False


def test_contract_compliance_zero_minimum_volume_clause_allows_switch():
    """The blocker check is `> 0`, not `>= some threshold` -- a
    minimum-volume clause of exactly 0 must NOT block switching,
    confirming the true zero/nonzero boundary."""
    fake_contracts = {"contracts": [
        {"supplier": "Minas Gerais Cooperative", "exclusivity": False,
         "minimum_volume_clause_bags_per_quarter": 0, "payment_terms": "30 days"},
        {"supplier": "Sao Paulo Cooperative (backup)", "exclusivity": False,
         "minimum_volume_clause_bags_per_quarter": 0, "payment_terms": "50% upfront"},
    ]}
    with patch("tools_task3_sourcing_decision.get_supplier_contracts", return_value=fake_contracts):
        result = check_contract_compliance("Minas Gerais Cooperative", "Sao Paulo Cooperative (backup)")

    assert result["can_switch"] is True


def test_contract_compliance_one_bag_minimum_volume_clause_blocks_switch():
    """The smallest possible nonzero clause (1 bag/quarter) must still
    block switching, confirming the boundary sits exactly at 0, not
    some rounded-up threshold."""
    fake_contracts = {"contracts": [
        {"supplier": "Minas Gerais Cooperative", "exclusivity": False,
         "minimum_volume_clause_bags_per_quarter": 1, "payment_terms": "30 days"},
        {"supplier": "Sao Paulo Cooperative (backup)", "exclusivity": False,
         "minimum_volume_clause_bags_per_quarter": 0, "payment_terms": "50% upfront"},
    ]}
    with patch("tools_task3_sourcing_decision.get_supplier_contracts", return_value=fake_contracts):
        result = check_contract_compliance("Minas Gerais Cooperative", "Sao Paulo Cooperative (backup)")

    assert result["can_switch"] is False
