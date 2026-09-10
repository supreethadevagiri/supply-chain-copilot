"""
Guaranteed Delivery System -- Shippo integration for Task 1.
Real system: Shippo (free, Test token available immediately, no
payment method or bank account required).

SETUP:
1. Sign up: https://goshippo.com/
2. Settings -> API -> copy your Test Token (starts with "shippo_test_")
3. Set environment variable: SHIPPO_API_KEY=shippo_test_...
4. For a live demo without a real shipment, use Shippo's official test
   tracking number "SHIPPO_TRANSIT" with carrier "shippo" -- set these
   as shippo_tracking_number / shippo_carrier on a row in
   freight_tracker.csv.

Falls back to freight_tracker.csv's own dates if the API key isn't set
or a specific shipment has no tracking number yet.
"""

import os
import pandas as pd

DATA_DIR = "data"


def _get_shippo_client():
    api_key = os.environ.get("SHIPPO_API_KEY")
    if not api_key:
        return None
    import shippo
    return shippo.Shippo(api_key_header=api_key)


def get_intransit_stock() -> dict:
    df = pd.read_csv(f"{DATA_DIR}/freight_tracker.csv")
    client = _get_shippo_client()

    shipments = []
    for _, row in df.iterrows():
        record = row.to_dict()
        tracking_number = row.get("shippo_tracking_number")
        carrier = row.get("shippo_carrier", "shippo")
        if client is not None and pd.notna(tracking_number):
            try:
                tracker = client.tracking_status.get(tracking_number, carrier)
                record["live_status"] = tracker.tracking_status.status if tracker.tracking_status else "UNKNOWN"
                record["source"] = "shippo_live"
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
