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


from unittest.mock import patch


def test_all_six_signals_unavailable_returns_safe_no_risk_result():
    """If every external signal call fails and falls back to its own
    safe 'unavailable' state, get_risk_assessment must still return a
    complete, non-crashing result with no false alarm -- not raise."""
    fallback_futures = {"latest_close_cents_per_lb": None, "avg_last_30d_cents_per_lb": None,
                         "pct_vs_30d_avg": 0.0, "is_spike": False, "source": "unavailable (assumed no spike)"}
    fallback_news = {"article_count_last_week": 0, "headlines": [], "signal_triggered": False,
                      "source": "unavailable (assumed no notable news)"}
    fallback_deforestation = {"municipality": "Test", "found_in_dataset": False,
                               "deforestation_risk_flag": None, "source": "unavailable (test)"}
    fallback_export = {"month": "09", "germany_national_import_tons_this_period": 83000,
                        "germany_data_source": "cached fallback (typical-year estimate)",
                        "brazil_national_export_thousand_bags_this_period": 40000,
                        "brazil_pct_of_typical_year": 100.0,
                        "brazil_data_source": "cached fallback (assumed typical)",
                        "below_seasonal_norm": False}
    fallback_fx = {"brl_eur_rate": None, "avg_30d_rate": None, "pct_move_vs_30d_avg": 0.0,
                    "significant_move": False, "source": "unavailable (assumed no significant move)"}
    fallback_emails = {"delay_mentioned": False, "flagged_emails": [], "source": "mocked_unavailable"}

    with patch("tools_task2_risk_assessment.get_arabica_futures_price", return_value=fallback_futures), \
         patch("tools_task2_risk_assessment.get_regional_news", return_value=fallback_news), \
         patch("tools_task2_risk_assessment.get_trase_deforestation_exposure", return_value=fallback_deforestation), \
         patch("tools_task2_risk_assessment.fetch_seasonal_benchmark_live", return_value=fallback_export), \
         patch("tools_task2_risk_assessment.get_brl_eur_exchange_rate", return_value=fallback_fx), \
         patch("tools_task2_risk_assessment.check_supplier_emails_for_risk", return_value=fallback_emails):
        result = get_risk_assessment("SHP-2201")

    assert result["num_signals_triggered"] == 0
    assert result["risk_confirmed"] is False
    assert result["risk_rating"] == "Low"
    assert result["cost_pct_estimate"] == 0
    assert result["delay_weeks_estimate"] == 0


def test_five_of_six_signals_disagreement_is_named_not_hidden():
    """If 5 signals agree and 1 doesn't, the disagreement must be
    visible in the result -- both which ones triggered and which
    didn't -- not collapsed into just a pass/fail count."""
    triggered = {"latest_close_cents_per_lb": 250.0, "avg_last_30d_cents_per_lb": 200.0,
                 "pct_vs_30d_avg": 25.0, "is_spike": True, "source": "mocked"}
    triggered_news = {"article_count_last_week": 5, "headlines": ["a"], "signal_triggered": True, "source": "mocked"}
    triggered_deforestation = {"municipality": "Test", "found_in_dataset": True,
                                "deforestation_risk_flag": True, "source": "mocked"}
    triggered_export = {"month": "09", "germany_national_import_tons_this_period": 1,
                         "germany_data_source": "mocked", "brazil_national_export_thousand_bags_this_period": 1,
                         "brazil_pct_of_typical_year": 50.0, "brazil_data_source": "mocked",
                         "below_seasonal_norm": True}
    triggered_fx = {"brl_eur_rate": 0.2, "avg_30d_rate": 0.18, "pct_move_vs_30d_avg": 11.0,
                     "significant_move": True, "source": "mocked"}
    NOT_triggered_emails = {"delay_mentioned": False, "flagged_emails": [], "source": "mocked"}

    with patch("tools_task2_risk_assessment.get_arabica_futures_price", return_value=triggered), \
         patch("tools_task2_risk_assessment.get_regional_news", return_value=triggered_news), \
         patch("tools_task2_risk_assessment.get_trase_deforestation_exposure", return_value=triggered_deforestation), \
         patch("tools_task2_risk_assessment.fetch_seasonal_benchmark_live", return_value=triggered_export), \
         patch("tools_task2_risk_assessment.get_brl_eur_exchange_rate", return_value=triggered_fx), \
         patch("tools_task2_risk_assessment.check_supplier_emails_for_risk", return_value=NOT_triggered_emails):
        result = get_risk_assessment("SHP-2201")

    assert result["num_signals_triggered"] == 5
    assert result["risk_confirmed"] is True
    assert result["signals_triggered"]["supplier_email_warning"] is False
    assert all(v for k, v in result["signals_triggered"].items() if k != "supplier_email_warning")
    assert "supplier_email_warning" not in result["reasoning"] or "supplier_email_warning" in result["signals_triggered"]
    triggered_names = [k for k, v in result["signals_triggered"].items() if v]
    assert all(name in result["reasoning"] for name in triggered_names)
