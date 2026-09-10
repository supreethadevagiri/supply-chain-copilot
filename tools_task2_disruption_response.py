"""
Task 2 -- Disruption Response
Adds two pieces on top of the existing six-signal risk detection
(tools_task2_risk_assessment.py, unchanged): alarm the company when a
disruption is confirmed, suggest an
alternative source to cover it, and if no source is available, report
that price will rise by X%.
"""

import csv
import os
from datetime import datetime

import pandas as pd

from tools_task2_risk_assessment import get_risk_assessment

DATA_DIR = "data"
ALERTS_LOG = f"{DATA_DIR}/alerts_log.csv"
_ALERT_FIELDS = ["timestamp", "shipment_id", "num_signals_triggered", "risk_rating", "message"]


def _ensure_alerts_log_exists():
    if not os.path.exists(ALERTS_LOG):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ALERTS_LOG, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_ALERT_FIELDS).writeheader()


def alarm_company(risk_result: dict) -> dict:
    """Step 2 -- actively alerts the company once a disruption is
    confirmed. Writes a real, timestamped row to data/alerts_log.csv --
    a durable alert record the company could actually check, not just a
    console print that disappears."""
    message = (
        f"DISRUPTION ALERT -- shipment {risk_result['shipment_id']}: "
        f"{risk_result['num_signals_triggered']} of 6 signals confirmed "
        f"({risk_result['risk_rating']} risk). {risk_result['reasoning']}"
    )
    alert = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "shipment_id": risk_result["shipment_id"],
        "num_signals_triggered": risk_result["num_signals_triggered"],
        "risk_rating": risk_result["risk_rating"],
        "message": message,
    }
    _ensure_alerts_log_exists()
    with open(ALERTS_LOG, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_ALERT_FIELDS).writerow(alert)
    return alert


def find_alternative_source() -> dict | None:
    """Step 3 -- checks the supplier contract terms for a viable backup
    supplier who could cover the gap. Returns the backup's real terms
    (lead time, payment terms, contract restrictions) if one exists on
    file, or None if there's genuinely no alternative -- that's what
    triggers Step 4."""
    contracts = pd.read_csv(f"{DATA_DIR}/supplier_contracts.csv")
    backups = contracts[contracts["role"] == "backup"]
    if backups.empty:
        return None
    backup = backups.iloc[0]
    return {
        "supplier": backup["supplier"],
        "lead_time_days": int(backup["lead_time_days"]),
        "minimum_volume_clause_bags_per_quarter": int(backup["minimum_volume_clause_bags_per_quarter"]),
        "exclusivity": bool(backup["exclusivity"]),
        "payment_terms": backup["payment_terms"],
    }


def get_disruption_response(shipment_id: str) -> dict:
    """Runs the full Task 2 workflow:
    1. Detect  -- six-signal check, two-signal-agreement rule (existing)
    2. Alarm   -- if confirmed, log a real alert
    3. Suggest an alternative source -- if one exists on file
    4. If no alternative -- report the estimated price increase
    """
    risk = get_risk_assessment(shipment_id)

    if not risk["risk_confirmed"]:
        return {
            "shipment_id": shipment_id,
            "disruption_detected": False,
            "alarm": None,
            "alternative_source": None,
            "price_increase_pct": 0,
            "summary": (
                f"No disruption confirmed for {shipment_id} -- fewer than 2 of 6 "
                f"signals triggered, so no alarm or action is needed."
            ),
        }

    alert = alarm_company(risk)
    alternative = find_alternative_source()

    if alternative:
        summary = (
            f"Disruption confirmed for {shipment_id} ({risk['risk_rating']} risk). "
            f"Company alerted. Alternative source available: {alternative['supplier']} "
            f"({alternative['lead_time_days']}-day lead time, {alternative['payment_terms']})."
        )
        price_increase = 0
    else:
        summary = (
            f"Disruption confirmed for {shipment_id} ({risk['risk_rating']} risk). "
            f"Company alerted. No alternative source is available -- price is "
            f"expected to rise by {risk['cost_pct_estimate']}%."
        )
        price_increase = risk["cost_pct_estimate"]

    return {
        "shipment_id": shipment_id,
        "disruption_detected": True,
        "alarm": alert,
        "alternative_source": alternative,
        "price_increase_pct": price_increase,
        "summary": summary,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_disruption_response("SHP-2201"), indent=2, default=str))
