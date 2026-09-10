"""
Test suite for Task 2's disruption response workflow. Run with:
pytest test_task2_disruption_response.py -v
"""

import os
import csv
from tools_task2_disruption_response import (
    alarm_company,
    find_alternative_source,
    get_disruption_response,
    ALERTS_LOG,
)


def test_find_alternative_source_returns_the_backup_supplier():
    result = find_alternative_source()
    assert result is not None
    assert result["supplier"] != ""
    assert result["lead_time_days"] > 0


def test_alarm_company_writes_a_real_row_to_the_alerts_log():
    fake_risk = {
        "shipment_id": "TEST-0000",
        "num_signals_triggered": 3,
        "risk_rating": "Medium",
        "reasoning": "test reasoning",
    }
    alert = alarm_company(fake_risk)
    assert alert["shipment_id"] == "TEST-0000"
    assert os.path.exists(ALERTS_LOG)
    with open(ALERTS_LOG) as f:
        rows = list(csv.DictReader(f))
    assert any(r["shipment_id"] == "TEST-0000" for r in rows)


def test_disruption_response_has_all_required_fields():
    result = get_disruption_response("SHP-2201")
    for field in ("shipment_id", "disruption_detected", "alarm",
                  "alternative_source", "price_increase_pct", "summary"):
        assert field in result


def test_no_disruption_means_no_alarm_and_no_price_change():
    result = get_disruption_response("SHP-2201")
    if not result["disruption_detected"]:
        assert result["alarm"] is None
        assert result["price_increase_pct"] == 0


def test_disruption_confirmed_always_produces_an_alarm():
    result = get_disruption_response("SHP-2201")
    if result["disruption_detected"]:
        assert result["alarm"] is not None
        assert result["alarm"]["shipment_id"] == "SHP-2201"


def test_price_increase_only_applies_when_no_alternative_source():
    result = get_disruption_response("SHP-2201")
    if result["disruption_detected"]:
        if result["alternative_source"] is not None:
            assert result["price_increase_pct"] == 0
        else:
            assert result["price_increase_pct"] >= 0


def test_price_increase_is_never_negative():
    result = get_disruption_response("SHP-2201")
    assert result["price_increase_pct"] >= 0


def test_summary_is_a_non_empty_string():
    result = get_disruption_response("SHP-2201")
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 20


from unittest.mock import patch


def test_no_alternative_source_forces_price_increase_path():
    """The existing test only checks this branch IF it happens to occur
    naturally -- but supplier_contracts.csv always has a real backup on
    file, so that branch never actually runs in practice. This forces
    it directly: disruption confirmed, no backup available, must fall
    through to reporting the price increase."""
    fake_risk = {
        "shipment_id": "SHP-TEST",
        "risk_confirmed": True,
        "risk_rating": "Medium",
        "num_signals_triggered": 3,
        "cost_pct_estimate": 15,
        "reasoning": "test: forced disruption for edge case coverage",
    }
    with patch("tools_task2_disruption_response.get_risk_assessment", return_value=fake_risk), \
         patch("tools_task2_disruption_response.find_alternative_source", return_value=None):
        result = get_disruption_response("SHP-TEST")

    assert result["disruption_detected"] is True
    assert result["alternative_source"] is None
    assert result["price_increase_pct"] == 15
    assert "No alternative source" in result["summary"]
    assert result["alarm"] is not None
