"""
Supplier Urgent Email System -- Gmail integration for Task 1 and Task 2.
Replaces supplier_emails.csv. Switched from Outlook/Microsoft Graph to
Gmail API after a persistent Azure Portal session error blocked the
Outlook route -- Gmail's OAuth "testing mode" works instantly against
a personal account with no tenant/sandbox restrictions.

This is genuinely shared infrastructure (like real_data_sources.py),
not task-specific business logic -- both Task 1 and Task 2 use the
same "supplier warnings" signal from the same inbox, per the original
project spec.

SETUP (already done for this project):
1. Google Cloud Console -> new project -> enable Gmail API
2. OAuth consent screen -> External -> add yourself as a test user
3. Credentials -> Create OAuth client -> Desktop app -> download JSON
   as google_client_secret.json in the project root
4. First run opens a browser once for you to log in and approve access
   -- after that, a cached gmail_token.json means no repeated logins.
5. Since there's no real supplier, send yourself 2-3 test emails with
   "delay" somewhere in the subject or body (e.g. "Heads up on drying
   yard capacity -- delay expected").

Falls back to the local synthetic CSV if the credentials file isn't
present, so Task 1 and Task 2 aren't blocked if Gmail isn't set up.
"""

import os
import pandas as pd

DATA_DIR = "data"
CREDS_PATH = "google_client_secret.json"
TOKEN_PATH = "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service():
    if not os.path.exists(CREDS_PATH):
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def check_supplier_emails() -> dict:
    """Any informal delay mentioned in recent inbox messages. Pulls
    live from Gmail if configured; otherwise falls back to the local
    synthetic CSV. The delay_mentioned flag stays a simple,
    deterministic keyword check either way -- never an LLM judgment
    call."""
    service = _get_gmail_service()

    if service:
        results = service.users().messages().list(
            userId="me", maxResults=10, q="delay newer_than:30d"
        ).execute()
        messages = results.get("messages", [])
        flagged = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject"]
            ).execute()
            headers = msg.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            snippet = msg.get("snippet", "")
            if "delay" in (subject + " " + snippet).lower():
                flagged.append({
                    "email_id": m["id"],
                    "subject": subject,
                    "note": snippet,
                })
        return {
            "delay_mentioned": bool(flagged),
            "flagged_emails": flagged,
            "source": "gmail_live",
        }

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
