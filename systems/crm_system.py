"""
CRM System -- Salesforce integration for Task 1.
Replaces crm_commitments.csv as the source of truth. Real system:
Salesforce (free Developer Edition org -- instant signup, no approval
wait).

SETUP:
1. Sign up: https://developer.salesforce.com/signup
2. In Setup -> Object Manager -> Create -> Custom Object, create
   "Cafe Account" (API name auto-fills to Cafe_Account__c) with fields:
     - Contract_Priority__c   (Picklist: High, Medium, Low)
     - Committed_Bags__c      (Number, 0 decimal places)
     - Monthly_Revenue_EUR__c (Number, 0 decimal places)
   Use the object's standard Name field for the cafe name.
3. Load your 50 cafe accounts in via Setup -> Data Import Wizard
   (you can export crm_commitments.csv from data/ and import it directly
   -- the column names won't match exactly, map them in the wizard).
4. Get your security token: Settings -> My Personal Information ->
   Reset My Security Token (emailed to you).
5. Set environment variables:
     SF_USERNAME=you@yourorg.com
     SF_PASSWORD=your_login_password
     SF_SECURITY_TOKEN=the_token_from_step_4

Falls back to the local synthetic CSV if credentials aren't set, so
Task 1 keeps working end-to-end while Salesforce setup is in progress.
Every response says which source it actually came from -- never silently
pretend fallback data is live.
"""

import os
import pandas as pd

DATA_DIR = "data"


def _get_sf_connection():
    """Returns an authenticated Salesforce connection, or None if
    credentials aren't configured yet."""
    username = os.environ.get("SF_USERNAME")
    password = os.environ.get("SF_PASSWORD")
    token = os.environ.get("SF_SECURITY_TOKEN")
    if not (username and password and token):
        return None
    from simple_salesforce import Salesforce
    return Salesforce(username=username, password=password, security_token=token)


def get_crm_commitments() -> dict:
    """Coffee already promised to cafe customers. Pulls live from
    Salesforce's Cafe_Account__c object if credentials are configured;
    otherwise falls back to the local synthetic CSV (same shape) so
    development isn't blocked on Salesforce setup."""
    sf = _get_sf_connection()

    if sf is not None:
        query = (
            "SELECT Name, Contract_Priority__c, Committed_Bags__c, "
            "Monthly_Revenue_EUR__c FROM Cafe_Account__c"
        )
        records = sf.query_all(query)["records"]
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

    # Fallback: local synthetic CSV, identical shape to the live response
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
