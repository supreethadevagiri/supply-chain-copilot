"""
Test suite for Task 2's deterministic risk logic. Run with:
pytest test_tools_task2.py -v
"""

from tools_task2_risk_assessment import get_risk_assessment, get_risk_trend, get_portfolio_risk_ranking


def test_risk_not_confirmed_with_fewer_than_2_signals():
    # In this sandboxed test environment, live APIs are unreachable, so
    # only the supplier-email signal can trigger -- exactly 1, which
    # must NOT be enough to confirm a risk rating on its own.
    result = get_risk_assessment("SHP-2201")
    if result["num_signals_triggered"] < 2:
        assert result["risk_confirmed"] is False
        assert result["risk_rating"] == "Low"
        assert result["cost_pct_estimate"] == 0


def test_risk_confirmed_requires_at_least_2_signals_by_construction():
    result = get_risk_assessment("SHP-2201")
    assert result["risk_confirmed"] == (result["num_signals_triggered"] >= 2)


def test_reasoning_field_exists_and_is_a_string():
    result = get_risk_assessment("SHP-2201")
    assert isinstance(result["reasoning"], str)
    assert len(result["reasoning"]) > 20


def test_risk_trend_no_history_for_unknown_shipment():
    result = get_risk_trend("SHP-9999-DOES-NOT-EXIST")
    assert result["has_history"] is False


def test_risk_trend_detects_escalation():
    # SHP-2201 in risk_history.csv goes Low -> Medium, which is escalation
    result = get_risk_trend("SHP-2201")
    assert result["has_history"] is True
    assert result["trend"] == "escalating"


def test_portfolio_ranking_returns_all_shipments_sorted_by_severity():
    results = get_portfolio_risk_ranking()
    assert len(results) >= 1
    triggered_counts = [r["num_signals_triggered"] for r in results]
    assert triggered_counts == sorted(triggered_counts, reverse=True)


def test_cost_and_delay_estimates_never_negative():
    result = get_risk_assessment("SHP-2201")
    assert result["cost_pct_estimate"] >= 0
    assert result["delay_weeks_estimate"] >= 0
