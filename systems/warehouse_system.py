"""
Warehouse System -- Salesforce integration for Task 1's warehouse
stock check. Uses the exact same OAuth Client Credentials flow as
systems/crm_system.py -- same SF_CLIENT_ID/SF_CLIENT_SECRET/SF_DOMAIN
env vars, same External Client App, no separate setup needed if
crm_system.py already works.

Falls back to the local synthetic CSV (data/warehouse_stock.csv) if
credentials aren't set or the live call fails for any reason -- same
live-then-fallback pattern already used by CRM, Shippo, and Gmail.
"""

import os
import requests
import pandas as pd

DATA_DIR = "data"


def _get_sf_access_token():
    client_id = os.environ.get("SF_CLIENT_ID")
    client_secret = os.environ.get("SF_CLIENT_SECRET")
    domain = os.environ.get("SF_DOMAIN")
    if not (client_id and client_secret and domain):
        return None, None

    url = f"https://{domain}/services/oauth2/token"
    resp = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["instance_url"]


def get_warehouse_lots() -> dict:
    """Current stock balance, reconciled across both Hamburg storage
    sites. Pulls live from Salesforce's Warehouse_Lot__c object if
    credentials are configured; otherwise falls back to the local
    synthetic CSV. Never raises -- any live failure falls back safely,
    consistent with the rest of the project."""
    token, instance_url = None, None
    try:
        token, instance_url = _get_sf_access_token()
    except Exception as e:
        print(f"[Warehouse] Live Salesforce login failed ({e}); falling back to CSV.")

    if token:
        try:
            query = (
                "SELECT Name, Site__c, Origin_Municipality__c, Grade__c, "
                "Harvest_Date__c, Bags__c FROM Warehouse_Lot__c"
            )
            resp = requests.get(
                f"{instance_url}/services/data/v59.0/query",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query},
            )
            resp.raise_for_status()
            records = resp.json()["records"]
            lots = [
                {
                    "lot_id": r["Name"],
                    "site": r["Site__c"],
                    "origin_municipality": r["Origin_Municipality__c"],
                    "grade": r["Grade__c"],
                    "harvest_date": r["Harvest_Date__c"],
                    "bags": int(r["Bags__c"] or 0),
                }
                for r in records
            ]
            by_site = {}
            for lot in lots:
                by_site[lot["site"]] = by_site.get(lot["site"], 0) + lot["bags"]
            return {
                "total_bags": sum(lot["bags"] for lot in lots),
                "by_site": by_site,
                "lots": lots,
                "source": "salesforce_live",
            }
        except Exception as e:
            print(f"[Warehouse] Live Salesforce query failed ({e}); falling back to CSV.")

    df = pd.read_csv(f"{DATA_DIR}/warehouse_stock.csv")
    by_site = df.groupby("site")["bags"].sum().to_dict()
    return {
        "total_bags": int(df["bags"].sum()),
        "by_site": {k: int(v) for k, v in by_site.items()},
        "lots": df.to_dict(orient="records"),
        "source": "local_fallback_csv",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_warehouse_lots(), indent=2, default=str))
