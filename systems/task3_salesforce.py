"""
Task 3 -- Salesforce connection for Sourcing Decision.
Deliberately independent from systems/crm_system.py (Task 1's file) --
each task owns its own connection code, per the project's
one-task-one-tool-set rule, even though both ultimately reach the same
Salesforce org and reuse the OAuth pattern.

SETUP: same Connected App and .env variables as Task 1
(SF_CLIENT_ID, SF_CLIENT_SECRET, SF_DOMAIN) -- one org, multiple
independent integrations, the way a real company's Salesforce would be
used by more than one internal tool.
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


def get_supplier_contracts() -> dict:
    """Contract terms for every supplier on file -- current and backup.
    Pulls live from Salesforce's Supplier_Contract__c object if
    credentials are configured; otherwise falls back to the local CSV."""
    token, instance_url = _get_sf_access_token()

    if token:
        query = (
            "SELECT Name, Lead_Time_Days__c, "
            "Minimum_Volume_Clause_Bags__c, Exclusivity__c, "
            "Payment_Terms__c FROM Supplier_Contract__c"
        )
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/query",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query},
        )
        resp.raise_for_status()
        records = resp.json()["records"]
        contracts = [
            {
                "supplier": r["Name"],
                "lead_time_days": int(r["Lead_Time_Days__c"] or 0),
                "minimum_volume_clause_bags_per_quarter": int(r["Minimum_Volume_Clause_Bags__c"] or 0),
                "exclusivity": bool(r["Exclusivity__c"]),
                "payment_terms": r["Payment_Terms__c"] or "",
            }
            for r in records
        ]
        return {"contracts": contracts, "source": "salesforce_live"}

    df = pd.read_csv(f"{DATA_DIR}/supplier_contracts.csv")
    contracts = [
        {
            "supplier": row["supplier"],
            "lead_time_days": int(row["lead_time_days"]),
            "minimum_volume_clause_bags_per_quarter": int(row["minimum_volume_clause_bags_per_quarter"]),
            "exclusivity": bool(row["exclusivity"]),
            "payment_terms": row["payment_terms"] if pd.notna(row["payment_terms"]) else "",
        }
        for _, row in df.iterrows()
    ]
    return {"contracts": contracts, "source": "local_fallback_csv"}


def get_purchase_history() -> dict:
    """Purchase records by origin region -- used to check sourcing
    concentration. Pulls live from Salesforce's Purchase_Record__c
    object if credentials are configured; otherwise falls back to a
    small local synthetic list matching what was entered in Salesforce."""
    token, instance_url = _get_sf_access_token()

    if token:
        query = (
            "SELECT Name, Origin_Region__c, Bags_Purchased__c, "
            "Purchase_Date__c FROM Purchase_Record__c"
        )
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/query",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query},
        )
        resp.raise_for_status()
        records = resp.json()["records"]
        purchases = [
            {
                "purchase_id": r["Name"],
                "origin_region": r["Origin_Region__c"],
                "bags_purchased": int(r["Bags_Purchased__c"] or 0),
                "purchase_date": r["Purchase_Date__c"],
            }
            for r in records
        ]
        return {"purchases": purchases, "source": "salesforce_live"}

    purchases = [
        {"purchase_id": "PUR-0001", "origin_region": "Minas Gerais", "bags_purchased": 1200, "purchase_date": "2026-01-15"},
        {"purchase_id": "PUR-0002", "origin_region": "Minas Gerais", "bags_purchased": 950, "purchase_date": "2026-02-10"},
        {"purchase_id": "PUR-0003", "origin_region": "Minas Gerais", "bags_purchased": 1100, "purchase_date": "2026-03-05"},
        {"purchase_id": "PUR-0004", "origin_region": "Sao Paulo", "bags_purchased": 300, "purchase_date": "2026-03-12"},
        {"purchase_id": "PUR-0005", "origin_region": "Minas Gerais", "bags_purchased": 1050, "purchase_date": "2026-04-01"},
    ]
    return {"purchases": purchases, "source": "local_fallback_synthetic"}


if __name__ == "__main__":
    import json
    print(json.dumps(get_supplier_contracts(), indent=2, default=str))
    print(json.dumps(get_purchase_history(), indent=2, default=str))
