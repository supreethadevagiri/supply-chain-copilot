"""
Task 1 -- Stock Position (real systems version)
CRM, in-transit delivery tracking, supplier email, and warehouse
stock all come from real systems (Salesforce, Shippo, Gmail) instead
of CSV files -- see systems/. Each falls back to a local CSV
automatically if the live system is unavailable. Order history and
supplier contracts stay as local records since those weren't part of
the system-swap requirement.
"""

import pandas as pd
from datetime import datetime

from systems.crm_system import get_crm_commitments
from systems.delivery_system import get_intransit_stock
from systems.email_system import check_supplier_emails
from systems.warehouse_system import get_warehouse_lots

DATA_DIR = "data"
TODAY = datetime.now()


def get_warehouse_stock() -> dict:
    """Current stock balance, reconciled across both Hamburg storage
    sites. Now reads live from Salesforce's Warehouse_Lot__c object
    (systems/warehouse_system.py), with the original local CSV kept
    as an automatic fallback -- same live-then-fallback pattern as
    CRM, Shippo, and Gmail elsewhere in this project."""
    return get_warehouse_lots()


def calculate_reorder_timing(current_stock_bags: int) -> dict:
    """Burn rate from 6 months of order history, checked against the
    supplier's lead time. Unchanged from the original."""
    history = pd.read_csv(f"{DATA_DIR}/order_history.csv")
    contracts = pd.read_csv(f"{DATA_DIR}/supplier_contracts.csv")

    monthly_totals = history.groupby("month")["bags_ordered"].sum()
    avg_monthly_bags = monthly_totals.mean()
    daily_burn_rate = avg_monthly_bags / 30
    coverage_days = round(current_stock_bags / daily_burn_rate, 1) if daily_burn_rate else None

    current_supplier = contracts[contracts["role"] == "current"].iloc[0]
    lead_time_days = int(current_supplier["lead_time_days"])

    days_until_reorder = (
        max(0, round(coverage_days - lead_time_days, 1)) if coverage_days is not None else None
    )
    reorder_by_date = (
        (TODAY + pd.Timedelta(days=days_until_reorder)).date()
        if days_until_reorder is not None else None
    )

    return {
        "daily_burn_rate_bags": round(daily_burn_rate, 1),
        "avg_monthly_bags_last_6mo": round(avg_monthly_bags, 1),
        "coverage_days": coverage_days,
        "supplier_lead_time_days": lead_time_days,
        "days_until_next_order_needed": days_until_reorder,
        "reorder_by_date": str(reorder_by_date) if reorder_by_date else None,
    }


def rank_exposed_accounts(shortfall_bags: int, accounts: list) -> dict:
    """If stock is short, which specific cafe accounts would be
    affected first, ranked by contract priority then revenue. Now takes
    accounts as an argument (from whichever CRM source responded) rather
    than re-reading the CSV directly."""
    if shortfall_bags <= 0:
        return {"accounts_at_risk": []}

    priority_rank = {"Low": 0, "Medium": 1, "High": 2}
    sorted_accounts = sorted(
        accounts,
        key=lambda a: (priority_rank.get(a["contract_priority"], 1), a["monthly_revenue_eur"]),
    )

    at_risk = []
    remaining = shortfall_bags
    for a in sorted_accounts:
        if remaining <= 0:
            break
        at_risk.append(a)
        remaining -= a["committed_bags"]

    return {"accounts_at_risk": at_risk}


def get_stock_position() -> dict:
    """Runs all checks and returns the full Task 1 answer. Reports which
    source (live system or local fallback) each of the three swapped
    systems actually came from, so it's never ambiguous during testing."""
    warehouse = get_warehouse_stock()
    crm = get_crm_commitments()          # Salesforce, or fallback
    intransit = get_intransit_stock()    # EasyPost, or fallback
    emails = check_supplier_emails()     # Gmail, or fallback

    total_available = warehouse["total_bags"] + intransit["total_intransit_bags"]
    net_position_bags = total_available - crm["total_committed_bags"]
    is_short = net_position_bags < 0
    shortfall_bags = abs(net_position_bags) if is_short else 0

    reorder_info = calculate_reorder_timing(warehouse["total_bags"])
    exposure = rank_exposed_accounts(shortfall_bags, crm["accounts"])

    if is_short:
        reasoning = (
            f"Warehouse stock ({warehouse['total_bags']} bags across both Hamburg "
            f"sites) plus in-transit stock ({intransit['total_intransit_bags']} bags) "
            f"totals {total_available} bags. CRM commitments total "
            f"{crm['total_committed_bags']} bags. That's a shortfall of "
            f"{shortfall_bags} bags. At the current burn rate, warehouse stock "
            f"covers {reorder_info['coverage_days']} days, against a "
            f"{reorder_info['supplier_lead_time_days']}-day supplier lead time -- "
            f"the next order needs to go out by {reorder_info['reorder_by_date']}."
        )
    else:
        reasoning = (
            f"Warehouse stock ({warehouse['total_bags']} bags across both Hamburg "
            f"sites) plus in-transit stock ({intransit['total_intransit_bags']} bags) "
            f"totals {total_available} bags, against {crm['total_committed_bags']} bags "
            f"committed -- a surplus of {abs(net_position_bags)} bags. Coverage at "
            f"the current burn rate is {reorder_info['coverage_days']} days."
        )

    return {
        "warehouse_stock_bags": warehouse["total_bags"],
        "warehouse_source": warehouse.get("source"),
        "stock_by_site": warehouse["by_site"],
        "crm_committed_bags": crm["total_committed_bags"],
        "crm_source": crm.get("source"),
        "intransit_bags": intransit["total_intransit_bags"],
        "net_position_bags": net_position_bags,
        "status": "short" if is_short else "enough",
        "shortfall_bags": shortfall_bags,
        "reasoning": reasoning,
        "supplier_email_delay_flag": emails["delay_mentioned"],
        "supplier_email_source": emails.get("source"),
        "flagged_emails": emails["flagged_emails"],
        "coverage_days": reorder_info["coverage_days"],
        "reorder_by_date": reorder_info["reorder_by_date"],
        "supplier_lead_time_days": reorder_info["supplier_lead_time_days"],
        "accounts_at_risk": exposure["accounts_at_risk"],
    }




def get_stock_position_hypothetical(warehouse_bag_delta: int = 0, cafe_bag_delta: int = 0) -> dict:
    """Answers a 'what if' question WITHOUT touching any real data --
    takes the real current numbers, applies ONE named change in
    memory only, and recalculates using the exact same real formulas
    as get_stock_position(). Nothing is written anywhere; calling this
    twice in a row always gives the same result, since it starts from
    whatever the real current numbers actually are right now."""
    warehouse = get_warehouse_stock()
    crm = get_crm_commitments()
    intransit = get_intransit_stock()

    real_warehouse_bags = warehouse["total_bags"]
    real_committed_bags = crm["total_committed_bags"]

    hypothetical_warehouse_bags = real_warehouse_bags + warehouse_bag_delta
    hypothetical_committed_bags = real_committed_bags + cafe_bag_delta

    hypothetical_total_available = hypothetical_warehouse_bags + intransit["total_intransit_bags"]
    hypothetical_net_position = hypothetical_total_available - hypothetical_committed_bags
    hypothetical_is_short = hypothetical_net_position < 0
    hypothetical_shortfall = abs(hypothetical_net_position) if hypothetical_is_short else 0
    hypothetical_reorder_info = calculate_reorder_timing(hypothetical_warehouse_bags)

    real_total_available = real_warehouse_bags + intransit["total_intransit_bags"]
    real_net_position = real_total_available - real_committed_bags

    return {
        "scenario": (
            f"Hypothetical: warehouse stock changed by {warehouse_bag_delta:+d} bags, "
            f"cafe commitments changed by {cafe_bag_delta:+d} bags."
        ),
        "real_current_status": "short" if real_net_position < 0 else "enough",
        "real_current_net_position_bags": real_net_position,
        "hypothetical_status": "short" if hypothetical_is_short else "enough",
        "hypothetical_warehouse_stock_bags": hypothetical_warehouse_bags,
        "hypothetical_crm_committed_bags": hypothetical_committed_bags,
        "hypothetical_net_position_bags": hypothetical_net_position,
        "hypothetical_shortfall_bags": hypothetical_shortfall,
        "hypothetical_coverage_days": hypothetical_reorder_info["coverage_days"],
        "hypothetical_reorder_by_date": hypothetical_reorder_info["reorder_by_date"],
        "note": "This is a hypothetical calculation only -- no real data was changed.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_stock_position(), indent=2, default=str))
