"""
Guaranteed Delivery System -- EasyPost integration for Task 1.
Replaces the in-transit portion of freight_tracker.csv. Real system:
EasyPost (free account, Test API key works immediately -- no approval
wait, fastest of the three systems to set up).

SETUP:
1. Sign up: https://www.easypost.com/ -> Account -> API Keys -> copy
   your Test API key (starts with "EZTK...").
2. Set environment variable: EASYPOST_API_KEY=EZTK...
3. EasyPost tracks generic packages, not "bags of coffee" -- so which
   shipment has how many bags still comes from our own freight_tracker.csv
   record. EasyPost supplies the real, live dispatch/arrival tracking
   status on top of that. Use EasyPost's test tracking codes (e.g.
   "EZ1000000001" = delivered, see their docs) as the
   easypost_tracker_id for each row in freight_tracker.csv to see this
   working end-to-end without a real shipment.

Falls back to freight_tracker.csv's own dates if the API key isn't set
or a specific shipment has no tracker id yet.
"""

import os
import pandas as pd

DATA_DIR = "data"


def _get_easypost_client():
    api_key = os.environ.get("EASYPOST_API_KEY")
    if not api_key:
        return None
    import easypost
    return easypost.EasyPostClient(api_key)


def get_intransit_stock() -> dict:
    """Coffee already shipped but not yet landed. Cross-references our
    own shipment records (bags, origin) with EasyPost's live tracking
    status for real dispatch/arrival timing, per shipment, if configured."""
    df = pd.read_csv(f"{DATA_DIR}/freight_tracker.csv")
    client = _get_easypost_client()

    shipments = []
    for _, row in df.iterrows():
        record = row.to_dict()
        tracker_id = row.get("easypost_tracker_id")
        if client is not None and pd.notna(tracker_id):
            try:
                tracker = client.tracker.retrieve(tracker_id)
                record["live_status"] = tracker.status
                record["source"] = "easypost_live"
            except Exception as e:
                record["source"] = "local_fallback"
                record["fetch_error"] = str(e)
        else:
            record["source"] = "local_fallback"
        shipments.append(record)

    return {
        "total_intransit_bags": int(df["bags_in_transit"].sum()),
        "shipments": shipments,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_intransit_stock(), indent=2, default=str))
