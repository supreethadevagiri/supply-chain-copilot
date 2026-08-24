"""
Generates synthetic data standing in for Elbhafen Coffee Traders' internal
systems -- warehouse management system, CRM, freight tracker, supplier
emails, supplier contract terms, and order history.

Run once: `python generate_data.py` -- writes CSVs into this folder.
Re-run any time to regenerate (seeded, so it's reproducible).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)
TODAY = datetime(2026, 8, 6)

# ---------------------------------------------------------------------
# 1. Warehouse management system -- LOT-LEVEL tracking, not one number
# ---------------------------------------------------------------------
# Real importers hold specific lots (origin municipality, grade, harvest
# date), not one undifferentiated blob of "coffee" -- this also directly
# supports the EUDR municipality-level traceability story used in Task 2/3.
warehouse_lots = pd.DataFrame([
    # -- Hamburg Main Warehouse --
    {"lot_id": "LOT-2601", "site": "Hamburg Main Warehouse", "origin_municipality": "Poco Fundo, Minas Gerais",
     "grade": "Screen 17/18, Fine Cup", "harvest_date": "2026-05-14", "bags": 416},
    {"lot_id": "LOT-2602", "site": "Hamburg Main Warehouse", "origin_municipality": "Carmo de Minas, Minas Gerais",
     "grade": "Screen 16/17, Fine Cup", "harvest_date": "2026-05-22", "bags": 352},
    {"lot_id": "LOT-2603", "site": "Hamburg Main Warehouse", "origin_municipality": "Poco Fundo, Minas Gerais",
     "grade": "Screen 18, Strictly Soft", "harvest_date": "2026-06-02", "bags": 384},
    {"lot_id": "LOT-2604", "site": "Hamburg Main Warehouse", "origin_municipality": "Manhuacu, Minas Gerais",
     "grade": "Screen 16, Fine Cup", "harvest_date": "2026-06-10", "bags": 208},
    {"lot_id": "LOT-2605", "site": "Hamburg Main Warehouse", "origin_municipality": "Carmo de Minas, Minas Gerais",
     "grade": "Screen 17, Strictly Soft", "harvest_date": "2026-06-18", "bags": 176},
    # -- Hamburg Overflow Facility --
    {"lot_id": "LOT-2606", "site": "Hamburg Overflow Facility", "origin_municipality": "Manhuacu, Minas Gerais",
     "grade": "Screen 15/16, Fine Cup", "harvest_date": "2026-06-05", "bags": 280},
    {"lot_id": "LOT-2607", "site": "Hamburg Overflow Facility", "origin_municipality": "Poco Fundo, Minas Gerais",
     "grade": "Screen 17, Fine Cup", "harvest_date": "2026-06-20", "bags": 224},
])
warehouse_lots.to_csv("warehouse_stock.csv", index=False)

# ---------------------------------------------------------------------
# 2. CRM -- 50 cafe accounts, standing commitments, contract priority
# ---------------------------------------------------------------------
_hamburg_districts = [
    "Elbufer", "Speicherstadt", "Alster", "Blankenese", "Ottensen", "Winterhude",
    "Barmbek", "Altona", "Eppendorf", "Wandsbek", "Harburg", "Bergedorf",
    "Poppenbuettel", "Volksdorf", "Niendorf", "Bahrenfeld", "Hoheluft", "Grindel",
    "Eimsbuettel", "Finkenwerder", "St. Pauli", "Sternschanze", "Rotherbaum",
    "Uhlenhorst", "St. Georg",
]
_name_templates = ["{} Kaffeehaus", "{} Roastery", "{} Espresso Bar", "Kaffee {}", "{} Bruehwerk"]
cafe_names = []
for i in range(50):
    district = _hamburg_districts[i % len(_hamburg_districts)]
    template = _name_templates[i // len(_hamburg_districts) % len(_name_templates)]
    cafe_names.append(template.format(district))
# Two anchor accounts kept explicitly named/low-tier, matching the "smaller
# accounts get flagged first" story used in the project brief and script
cafe_names[0], cafe_names[1] = "Nordlicht Kaffee", "Sternschanze Roasters"

priority_weights = [0.2, 0.45, 0.35]  # High, Medium, Low
priorities = list(np.random.choice(["High", "Medium", "Low"], size=50, p=priority_weights))
priorities[0], priorities[1] = "Low", "Low"  # keep the two anchor accounts Low-priority

committed_bags = np.random.randint(20, 100, size=50)
committed_bags[0], committed_bags[1] = 60, 70  # anchor accounts, unchanged from before

monthly_revenue_eur = (committed_bags * np.random.randint(70, 130, size=50)).astype(int)
monthly_revenue_eur[0], monthly_revenue_eur[1] = 3200, 3900  # anchor accounts, unchanged

crm_commitments = pd.DataFrame({
    "cafe_account_id": [f"CAFE-{i+1:03d}" for i in range(50)],
    "cafe_name": cafe_names,
    "contract_priority": priorities,
    "committed_bags": committed_bags,
    "monthly_revenue_eur": monthly_revenue_eur,
})
crm_commitments.to_csv("crm_commitments.csv", index=False)

# ---------------------------------------------------------------------
# 2b. Order history -- 6 months of real per-cafe order volume, so the
# burn rate calculation is a genuine historical average instead of a
# same-month snapshot divided by 30.
# ---------------------------------------------------------------------
months_back = pd.date_range(end=TODAY, periods=6, freq="MS").strftime("%Y-%m")
order_history_rows = []
for _, row in crm_commitments.iterrows():
    base = row["committed_bags"]
    for m in months_back:
        # +/- 15% natural month-to-month variation around the current
        # committed level, so the average is realistic but not identical
        # to this month's snapshot
        noise = np.random.uniform(0.85, 1.15)
        order_history_rows.append({
            "cafe_account_id": row["cafe_account_id"],
            "month": m,
            "bags_ordered": max(0, round(base * noise)),
        })
order_history = pd.DataFrame(order_history_rows)
order_history.to_csv("order_history.csv", index=False)

# ---------------------------------------------------------------------
# 3. Freight tracker -- shipments already dispatched, not yet landed
# ---------------------------------------------------------------------
freight_tracker = pd.DataFrame([
    # origin_municipality is the growing-region municipality (used by Task 2's
    # Trase deforestation lookup) -- distinct from "origin", which is the
    # export port. Both values are real municipalities present in
    # trase_brazil_coffee.csv, matching the naming Trase uses so the
    # substring lookup in get_trase_deforestation_exposure() resolves.
    # easypost_tracker_id is optional -- fill in with a real EasyPost test
    # tracking code (see systems/delivery_system.py) to see the live path
    # work; left blank, the row just uses these dispatch/arrival dates.
    {"shipment_id": "SHP-2201", "origin": "Santos, Brazil", "origin_municipality": "Poco Fundo",
     "bags_in_transit": 432, "dispatch_date": (TODAY - timedelta(days=18)).date(),
     "expected_arrival_date": (TODAY + timedelta(days=4)).date(), "status": "In transit",
     "easypost_tracker_id": ""},
    {"shipment_id": "SHP-2202", "origin": "Santos, Brazil", "origin_municipality": "Carmo de Minas",
     "bags_in_transit": 229, "dispatch_date": (TODAY - timedelta(days=9)).date(),
     "expected_arrival_date": (TODAY + timedelta(days=13)).date(), "status": "In transit",
     "easypost_tracker_id": ""},
])
freight_tracker.to_csv("freight_tracker.csv", index=False)

# ---------------------------------------------------------------------
# 4. Supplier emails -- informal signals that haven't hit official systems
# ---------------------------------------------------------------------
supplier_emails = pd.DataFrame([
    {"email_id": "EM-5001", "date": (TODAY - timedelta(days=2)).date(),
     "supplier": "Minas Gerais Cooperative", "subject": "Re: August dispatch schedule",
     "mentions_delay": False,
     "note": "Confirms dispatch on schedule for the next shipment."},
    {"email_id": "EM-5002", "date": (TODAY - timedelta(days=1)).date(),
     "supplier": "Minas Gerais Cooperative", "subject": "Heads up on drying yard capacity",
     "mentions_delay": True,
     "note": "Mentions the drying yard is running behind after recent rain; next lot 'may slip a few days.'"},
])
supplier_emails.to_csv("supplier_emails.csv", index=False)

# ---------------------------------------------------------------------
# 5. Supplier contract terms -- lead time, volume commitments, payment
# ---------------------------------------------------------------------
supplier_contracts = pd.DataFrame([
    {"supplier": "Minas Gerais Cooperative", "role": "current", "lead_time_days": 21,
     "minimum_volume_clause_bags_per_quarter": 450, "exclusivity": False,
     "payment_terms": "30 days after delivery"},
    {"supplier": "Sao Paulo Cooperative (backup)", "role": "backup", "lead_time_days": 10,
     "minimum_volume_clause_bags_per_quarter": 0, "exclusivity": False,
     "payment_terms": "50% upfront, 50% on delivery"},
])
supplier_contracts.to_csv("supplier_contracts.csv", index=False)

print("Generated: warehouse_stock.csv (7 lots), crm_commitments.csv (50 accounts),")
print("           order_history.csv (300 rows, 6mo x 50 accounts), freight_tracker.csv,")
print("           supplier_emails.csv, supplier_contracts.csv")

# ---------------------------------------------------------------------
# 6. Risk assessment log -- Task 2's history of past risk checks, so the
# "is this getting worse or better" trend check has something real to
# compare against.
# ---------------------------------------------------------------------
risk_history = pd.DataFrame([
    {"shipment_id": "SHP-2201", "check_date": (TODAY - timedelta(days=14)).date(),
     "risk_rating": "Low", "cost_pct_estimate": 0, "delay_weeks_estimate": 0},
    {"shipment_id": "SHP-2201", "check_date": (TODAY - timedelta(days=7)).date(),
     "risk_rating": "Medium", "cost_pct_estimate": 8, "delay_weeks_estimate": 1},
    {"shipment_id": "SHP-2202", "check_date": (TODAY - timedelta(days=10)).date(),
     "risk_rating": "Low", "cost_pct_estimate": 0, "delay_weeks_estimate": 0},
])
risk_history.to_csv("risk_history.csv", index=False)
print("           risk_history.csv (3 rows)")
