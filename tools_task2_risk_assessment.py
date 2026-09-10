"""
Task 2 -- Risk Assessment
Deterministic tools for the Risk Assessment Agent. Same pattern as Task 1:
every number comes from real data or pandas, never the LLM. The agent
only explains the result afterward.
"""

import pandas as pd
from datetime import datetime
from systems.email_system import check_supplier_emails
from real_data_sources import (
    get_arabica_futures_price,
    get_regional_news,
    get_brl_eur_exchange_rate,
    get_trase_deforestation_exposure,
    fetch_seasonal_benchmark_live,  # reused for export-volume drop check
)

DATA_DIR = "data"
TODAY = datetime.now()


# ---------------------------------------------------------------------
# Check 4 -- Supplier emails (reused from Task 1's data, same pattern)
# ---------------------------------------------------------------------
def check_supplier_emails_for_risk() -> dict:
    """Recent supplier emails, for an informal warning that hasn't hit
    the official systems yet. Uses the same shared Gmail integration as
    Task 1 (systems/email_system.py) -- this signal isn't task-specific
    business logic, it's the same inbox both tasks legitimately check."""
    return check_supplier_emails()


# ---------------------------------------------------------------------
# Check 5 -- Shipment's real origin municipality (from the freight
# tracker itself, not a caller-supplied guess)
# ---------------------------------------------------------------------
def get_shipment_origin_municipality(shipment_id: str) -> str | None:
    """Looks up the real growing-region municipality for a shipment from
    freight_tracker.csv. This is what makes the deforestation check
    (Trase lookup) actually grounded per-shipment -- previously
    origin_municipality was a caller-supplied argument that silently
    defaulted to the same municipality regardless of which shipment was
    being checked. Returns None if the shipment isn't on file, consistent
    with NO_GUESSING_RULE (no fabricated municipality)."""
    df = pd.read_csv(f"{DATA_DIR}/freight_tracker.csv")
    match = df[df["shipment_id"] == shipment_id]
    if match.empty:
        return None
    return str(match.iloc[0]["origin_municipality"])


# ---------------------------------------------------------------------
# Check 7 -- This shipment's own risk history (trend: worsening/stabilizing)
# ---------------------------------------------------------------------
def get_risk_trend(shipment_id: str) -> dict:
    """Compares today's check against the last time this shipment was
    checked, to show whether the situation is stabilizing or escalating."""
    df = pd.read_csv(f"{DATA_DIR}/risk_history.csv")
    history = df[df["shipment_id"] == shipment_id].sort_values("check_date")
    if history.empty:
        return {"has_history": False, "trend": "no prior checks on file"}

    last = history.iloc[-1]
    if len(history) < 2:
        return {
            "has_history": True,
            "trend": "first check on file",
            "last_rating": last["risk_rating"],
        }

    prior = history.iloc[-2]
    rating_rank = {"Low": 0, "Medium": 1, "High": 2}
    worsening = rating_rank.get(last["risk_rating"], 0) > rating_rank.get(prior["risk_rating"], 0)
    return {
        "has_history": True,
        "trend": "escalating" if worsening else "stabilizing or unchanged",
        "last_rating": last["risk_rating"],
        "prior_rating": prior["risk_rating"],
        "last_check_date": str(last["check_date"]),
    }


# ---------------------------------------------------------------------
# Check 8 -- Portfolio-wide check across every incoming shipment
# ---------------------------------------------------------------------
def get_all_incoming_shipments() -> list:
    """Every shipment on the freight tracker, for the portfolio-wide
    ranked check -- run risk assessment on all of them at once."""
    df = pd.read_csv(f"{DATA_DIR}/freight_tracker.csv")
    return df["shipment_id"].tolist()


# ---------------------------------------------------------------------
# Combined -- assembles all 7 signals + the two-signal-agreement rule
# ---------------------------------------------------------------------
def get_risk_assessment(shipment_id: str, origin_municipality: str = None) -> dict:
    """Runs all 6 signals for one shipment. Only commits to a risk rating
    once at least 2 of the signals agree that something is wrong -- this
    is the deterministic safeguard against a single noisy signal causing
    a false alarm.

    origin_municipality is looked up from freight_tracker.csv by default
    (see get_shipment_origin_municipality) -- pass it explicitly only to
    override that lookup. If the shipment isn't on file, both the news
    and deforestation signals fall back to their "not found" state rather
    than guessing a municipality, per NO_GUESSING_RULE."""
    if origin_municipality is None:
        origin_municipality = get_shipment_origin_municipality(shipment_id) or "unknown"

    def _safe(call, fallback, label):
        """Defense in depth: every one of the 6 signal functions
        already has its own try/except with a safe fallback -- this is
        a second layer, so even a future bug that made one of them
        raise unexpectedly still can't crash the whole answer."""
        try:
            return call()
        except Exception as e:
            print(f"[Task 2] {label} raised unexpectedly ({e}); using safe fallback.")
            return fallback

    futures = _safe(
        get_arabica_futures_price,
        {"latest_close_cents_per_lb": None, "avg_last_30d_cents_per_lb": None,
         "pct_vs_30d_avg": 0.0, "is_spike": False, "source": "unavailable (unexpected error)"},
        "Arabica futures",
    )
    news = _safe(
        lambda: get_regional_news(f"{origin_municipality} coffee"),
        {"article_count_last_week": 0, "headlines": [], "signal_triggered": False,
         "source": "unavailable (unexpected error)"},
        "Regional news",
    )
    deforestation = _safe(
        lambda: get_trase_deforestation_exposure(origin_municipality),
        {"municipality": origin_municipality, "found_in_dataset": False,
         "deforestation_risk_flag": None, "source": "unavailable (unexpected error)"},
        "Trase deforestation",
    )
    export_data = _safe(
        lambda: fetch_seasonal_benchmark_live(TODAY.strftime("%m")),
        {"month": TODAY.strftime("%m"), "germany_national_import_tons_this_period": None,
         "germany_data_source": "unavailable (unexpected error)",
         "brazil_national_export_thousand_bags_this_period": None,
         "brazil_pct_of_typical_year": None,
         "brazil_data_source": "unavailable (unexpected error)",
         "below_seasonal_norm": False},
        "Seasonal benchmark",
    )
    fx = _safe(
        get_brl_eur_exchange_rate,
        {"brl_eur_rate": None, "avg_30d_rate": None, "pct_move_vs_30d_avg": 0.0,
         "significant_move": False, "source": "unavailable (unexpected error)"},
        "FX rate",
    )
    emails = _safe(
        check_supplier_emails_for_risk,
        {"delay_mentioned": False, "flagged_emails": [], "source": "unavailable (unexpected error)"},
        "Supplier emails",
    )
    trend = _safe(
        lambda: get_risk_trend(shipment_id),
        {"has_history": False, "trend": "unavailable (unexpected error)"},
        "Risk trend",
    )

    signals_triggered = {
        "futures_price_spike": futures["is_spike"],
        "regional_news": news["signal_triggered"],
        "deforestation_exposure": bool(deforestation.get("deforestation_risk_flag")),
        "export_volume_drop": export_data["below_seasonal_norm"],
        "currency_move": fx["significant_move"],
        "supplier_email_warning": emails["delay_mentioned"],
    }
    num_triggered = sum(1 for v in signals_triggered.values() if v)
    risk_confirmed = num_triggered >= 2  # the two-signal-agreement rule

    if risk_confirmed:
        # Simple deterministic cost/delay estimate scaled by how many
        # signals agree -- a real implementation would pull the closest
        # historical precedent via ChromaDB (see Task 1's pattern);
        # this is a placeholder rule until that's wired in.
        cost_pct_estimate = min(25, num_triggered * 5)
        delay_weeks_estimate = min(4, num_triggered)
        rating = "High" if num_triggered >= 4 else "Medium"
    else:
        cost_pct_estimate = 0
        delay_weeks_estimate = 0
        rating = "Low"

    reasoning = (
        f"{num_triggered} of 6 signals triggered for shipment {shipment_id} "
        f"(origin: {origin_municipality}): "
        f"{', '.join(k for k, v in signals_triggered.items() if v) or 'none'}. "
        + (
            f"Risk confirmed (rule: at least 2 signals must agree) -- rated {rating}, "
            f"with an estimated {cost_pct_estimate}% cost increase and "
            f"{delay_weeks_estimate}-week delay."
            if risk_confirmed else
            "Fewer than 2 signals agree, so no risk rating is issued -- avoids a false "
            "alarm from a single noisy signal."
        )
    )

    return {
        "shipment_id": shipment_id,
        "origin_municipality": origin_municipality,
        "signals_triggered": signals_triggered,
        "num_signals_triggered": num_triggered,
        "risk_confirmed": risk_confirmed,
        "risk_rating": rating,
        "cost_pct_estimate": cost_pct_estimate,
        "delay_weeks_estimate": delay_weeks_estimate,
        "trend": trend,
        "reasoning": reasoning,
        "signal_details": {
            "futures": futures,
            "news": news,
            "deforestation": deforestation,
            "export_data": export_data,
            "fx": fx,
            "emails": emails,
        },
    }


def get_portfolio_risk_ranking() -> list:
    """On request: runs the same check across every incoming shipment
    and ranks by severity, so the analyst can ask what needs attention
    this week without naming a shipment first."""
    results = []
    for shipment_id in get_all_incoming_shipments():
        results.append(get_risk_assessment(shipment_id))
    results.sort(key=lambda r: r["num_signals_triggered"], reverse=True)
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(get_risk_assessment("SHP-2201"), indent=2, default=str))


def get_risk_assessment_hypothetical(shipment_id: str, extra_signal_name: str) -> dict:
    """Answers a 'what if this signal also triggered' question WITHOUT
    changing any real data -- takes the real current signals for this
    shipment, hypothetically flips ONE named signal to triggered, and
    recalculates the real 2-of-6 rule and cost/delay formulas exactly
    as get_risk_assessment() does. Nothing is written anywhere."""
    real = get_risk_assessment(shipment_id)
    real_signals = dict(real["signals_triggered"])

    if extra_signal_name not in real_signals:
        return {
            "error": f"'{extra_signal_name}' isn't one of the six real signals.",
            "valid_signal_names": list(real_signals.keys()),
        }

    hypothetical_signals = dict(real_signals)
    hypothetical_signals[extra_signal_name] = True
    hypothetical_num_triggered = sum(1 for v in hypothetical_signals.values() if v)
    hypothetical_risk_confirmed = hypothetical_num_triggered >= 2

    if hypothetical_risk_confirmed:
        hypothetical_cost_pct = min(25, hypothetical_num_triggered * 5)
        hypothetical_delay_weeks = min(4, hypothetical_num_triggered)
    else:
        hypothetical_cost_pct = 0
        hypothetical_delay_weeks = 0

    return {
        "scenario": f"Hypothetical: '{extra_signal_name}' also triggered for {shipment_id}.",
        "real_current_num_signals_triggered": real["num_signals_triggered"],
        "real_current_risk_confirmed": real["risk_confirmed"],
        "hypothetical_signals_triggered": hypothetical_signals,
        "hypothetical_num_signals_triggered": hypothetical_num_triggered,
        "hypothetical_risk_confirmed": hypothetical_risk_confirmed,
        "hypothetical_cost_pct_estimate": hypothetical_cost_pct,
        "hypothetical_delay_weeks_estimate": hypothetical_delay_weeks,
        "note": "This is a hypothetical calculation only -- no real data was changed.",
    }
