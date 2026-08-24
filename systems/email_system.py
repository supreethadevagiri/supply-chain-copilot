"""
Supplier Urgent Email System -- Outlook integration for Task 1.
Replaces supplier_emails.csv. Real system: Microsoft Outlook via Graph
API. THIS IS THE SLOWEST OF THE THREE SETUPS -- start it first.

SETUP:
1. Join the Microsoft 365 Developer Program (free, gives you a sandbox
   tenant + mailbox): https://developer.microsoft.com/microsoft-365/dev-program
2. In the Azure Portal (portal.azure.com) -> Azure Active Directory ->
   App registrations -> New registration. Name it anything.
3. Under API permissions, add Microsoft Graph -> Application permissions
   -> Mail.Read -> grant admin consent.
4. Under Certificates & secrets, create a new client secret -- copy its
   VALUE immediately (it's hidden after you leave the page).
5. Set environment variables:
     MS_CLIENT_ID=<Application (client) ID from the app overview page>
     MS_CLIENT_SECRET=<the secret value from step 4>
     MS_TENANT_ID=<Directory (tenant) ID from the app overview page>
6. Since there's no real supplier, send yourself 2-3 test emails from a
   second mailbox with subject lines matching generate_data.py's pattern
   (e.g. "Heads up on drying yard capacity" mentioning a delay).

Falls back to the local synthetic CSV if these aren't set, so Task 1
isn't blocked while Azure/Outlook setup is in progress.
"""

import os
import pandas as pd

DATA_DIR = "data"


def _get_graph_token():
    client_id = os.environ.get("MS_CLIENT_ID")
    client_secret = os.environ.get("MS_CLIENT_SECRET")
    tenant_id = os.environ.get("MS_TENANT_ID")
    if not (client_id and client_secret and tenant_id):
        return None
    import msal
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")


def check_supplier_emails() -> dict:
    """Any informal delay mentioned in recent supplier emails. Pulls
    live from the Outlook inbox via Microsoft Graph if configured;
    otherwise falls back to the local synthetic CSV. The delay_mentioned
    flag stays a simple, deterministic keyword check either way -- never
    an LLM judgment call."""
    token = _get_graph_token()

    if token:
        import requests
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/messages"
            "?$top=10&$orderby=receivedDateTime desc",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        messages = resp.json().get("value", [])
        flagged = [
            {
                "email_id": m["id"],
                "subject": m["subject"],
                "note": m.get("bodyPreview", ""),
                "date": m["receivedDateTime"],
            }
            for m in messages
            if "delay" in (m["subject"] + m.get("bodyPreview", "")).lower()
        ]
        return {
            "delay_mentioned": bool(flagged),
            "flagged_emails": flagged,
            "source": "outlook_live",
        }

    # Fallback: local synthetic CSV
    df = pd.read_csv(f"{DATA_DIR}/supplier_emails.csv")
    flagged = df[df["mentions_delay"] == True]
    return {
        "delay_mentioned": bool(len(flagged) > 0),
        "flagged_emails": flagged.to_dict(orient="records"),
        "source": "local_fallback_csv",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(check_supplier_emails(), indent=2, default=str))
