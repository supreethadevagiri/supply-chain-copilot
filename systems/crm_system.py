"""
CRM System -- Salesforce integration for Task 1.
Uses OAuth Client Credentials flow (Consumer Key + Consumer Secret from
an External Client App) instead of username/password -- required since
this org has SOAP API login disabled.

SETUP:
1. In Salesforce: Setup -> App Manager -> New External Client App
   -> enable OAuth, add scope "Full access (full)" and
   "Perform requests at any time (refresh_token, offline_access)",
   enable Client Credentials Flow.
2. Under the app's Settings tab -> OAuth Settings -> Consumer Key and
   Secret -- copy both.
3. Set environment variables:
     SF_CLIENT_ID=<Consumer Key>
     SF_CLIENT_SECRET=<Consumer Secret>
     SF_DOMAIN=<your My Domain, e.g. orgfarm-xxxxx-dev-ed.develop.my.salesforce.com>

Falls back to the local synthetic CSV if these aren't set.
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


def get_crm_commitments() -> dict:
    """Coffee already promised to cafe customers. Pulls live from
    Salesforce's Cafe_Account__c object if credentials are configured;
    otherwise falls back to the local synthetic CSV."""
    token, instance_url = _get_sf_access_token()

    if token:
        query = (
            "SELECT Name, Contract_Priority__c, Committed_Bags__c, "
            "Monthly_Revenue_EUR__c FROM Cafe_Account__c"
        )
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/query",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query},
        )
        resp.raise_for_status()
        records = resp.json()["records"]
        accounts = [
            {
                "cafe_name": r["Name"],
                "contract_priority": r["Contract_Priority__c"],
                "committed_bags": int(r["Committed_Bags__c"] or 0),
                "monthly_revenue_eur": int(r["Monthly_Revenue_EUR__c"] or 0),
            }
            for r in records
        ]
        return {
            "total_committed_bags": sum(a["committed_bags"] for a in accounts),
            "accounts": accounts,
            "source": "salesforce_live",
        }

    df = pd.read_csv(f"{DATA_DIR}/crm_commitments.csv")
    accounts = [
        {
            "cafe_name": row["cafe_name"],
            "contract_priority": row["contract_priority"],
            "committed_bags": int(row["committed_bags"]),
            "monthly_revenue_eur": int(row["monthly_revenue_eur"]),
        }
        for _, row in df.iterrows()
    ]
    return {
        "total_committed_bags": int(df["committed_bags"].sum()),
        "accounts": accounts,
        "source": "local_fallback_csv",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_crm_commitments(), indent=2, default=str))
