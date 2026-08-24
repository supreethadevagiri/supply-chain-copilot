# Task 1 — Stock Position (real systems)

## Right now, without touching anything

This already runs and passes all 15 tests, using local fallback data —
so you have a working Task 1 tonight even before any of the three real
systems are set up.

```bash
pip install -r requirements.txt
python3 generate_data.py    # writes fallback CSVs into data/
cd .. && python3 -m pytest task1/test_task1.py -v
python3 tools_task1_stock_position.py    # see the actual answer
```

## Setup order (fastest to slowest — do them in this order)

1. **EasyPost** (5 min) — sign up, copy your Test API key, set
   `EASYPOST_API_KEY`. See `systems/delivery_system.py` for the exact
   steps.
2. **Salesforce** (15–20 min) — free Developer Edition signup, create
   one custom object, import your 50 accounts. See
   `systems/crm_system.py`.
3. **Outlook / Microsoft Graph** (20–40 min, start this first if
   working in parallel with someone else) — needs an Azure app
   registration. See `systems/email_system.py`.

Copy `.env.example` to `.env`, fill in whichever credentials you've
finished, and export them before running:

```bash
export $(cat .env | xargs)
python3 tools_task1_stock_position.py
```

Every response includes a `_source` field (`salesforce_live` vs.
`local_fallback_csv`, etc.) so you always know whether you're looking
at real or fallback data — useful for showing your professor the real
integration actually works, not just the fallback.

## What did NOT change from the original tools.py

- Warehouse stock (still `warehouse_stock.csv`) — not one of the three
  systems the brief asked to replace
- Order history and supplier contracts — same, used for reorder timing
- The reorder-timing and exposed-accounts math — identical logic

## Files

- `systems/crm_system.py` — Salesforce (CRM)
- `systems/delivery_system.py` — EasyPost (Guaranteed Delivery)
- `systems/email_system.py` — Outlook (Supplier Urgent Email)
- `tools_task1_stock_position.py` — combines everything into the final answer
- `test_task1.py` — 15 tests, all pass on fallback data right now
- `data/` — fallback CSVs (from `generate_data.py`)
