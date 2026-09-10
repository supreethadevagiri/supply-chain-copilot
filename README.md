# Elbhafen Supply Hafen -- Coffee Supply Risk Copilot

An AI copilot for Elbhafen Coffee Traders (a Hamburg coffee importer) that answers real questions about stock position, shipment risk, and sourcing decisions -- by checking real, live business systems directly, instead of a person manually checking each one.

## The business case

Running this business well means constantly answering three kinds of questions:

- **Do we have enough stock right now** to cover what we've promised our cafe customers?
- **Is an incoming shipment actually in trouble** -- price spikes, bad regional news, a supplier's own email mentioning a delay?
- **If something does go wrong, is switching to our backup supplier actually a smart move** -- or would it breach a contract, add environmental risk, or make us even more concentrated in one region?

This copilot answers all three, live, using real systems -- no manual cross-checking required.

## Architecture

Built with **LangGraph** as a state machine: every question is first classified by a dedicated router call into one of three tasks, then handled by a specialist agent with its own instructions and its own limited set of real tools. The underlying model is **Llama 3.1 8B**, run locally via **Ollama** -- private, free per query, and fully controllable, at the cost of being slower than a cloud model.

### Task 1 -- Stock Position
Checks Salesforce (cafe commitments + warehouse lots), Shippo (in-transit shipments), and Gmail (supplier delay emails) to answer whether there's enough stock, and which cafe accounts are exposed if not.

### Task 2 -- Risk Assessment
Checks six real, independent signals for an incoming shipment: Yahoo Finance (coffee futures price), Google News (regional news), Trase.earth (deforestation exposure), USDA FAS PSD Online (export volumes), Frankfurter/ECB (currency), and Gmail (supplier email). A disruption is only confirmed once at least 2 of the 6 agree.

### Task 3 -- Sourcing Decision
Checks Salesforce (contract terms) and Trase.earth (backup region's deforestation exposure) to decide whether switching to the backup supplier is actually advisable.

### Every answer, across all three tasks
- Names its real source for every fact
- Shows a live data-status badge (live vs. fallback, per system)
- Explains itself in plain business language -- no technical jargon
- Supports real "why did you decide that" follow-ups
- Supports real "what if" hypothetical questions (e.g. "what if we added 300 bags"), clearly labeled as hypothetical, never confused with real data

## Real data sources used, per task

### Task 1 -- Stock Position
- **Salesforce** -- cafe account commitments and warehouse lot records. https://www.salesforce.com/
- **Shippo** -- in-transit shipment tracking. https://goshippo.com/
- **Gmail** -- live search of the supplier's inbox for delay-related emails. https://developers.google.com/gmail/api

### Task 2 -- Risk Assessment (6 independent real signals)
- **Yahoo Finance** -- coffee futures price (ticker KC=F). https://finance.yahoo.com/quote/KC=F/
- **Google News** -- live regional news search. https://news.google.com/
- **Trase.earth** -- deforestation / land-use dataset. https://trase.earth/
- **USDA FAS PSD Online** -- export volume benchmarks. https://apps.fas.usda.gov/psdonline/
- **Frankfurter / ECB** -- currency exchange rates. https://www.frankfurter.app/ (data from the European Central Bank, https://www.ecb.europa.eu/)
- **Gmail** -- same live supplier inbox check as Task 1.

### Task 3 -- Sourcing Decision
- **Salesforce** -- real contract terms, including the minimum-order clause. https://www.salesforce.com/
- **Trase.earth** -- deforestation exposure for the backup supplier's region. https://trase.earth/

Every one of these is checked live wherever possible, with a local CSV fallback if the live system is unavailable -- see `data/` for the fallback files and `systems/` for each live integration.

## Setup -- what to install

**1. Clone the repo and install Python dependencies:**

    git clone https://github.com/supreethadevagiri/supply-chain-copilot.git
    cd supply-chain-copilot
    pip install -r requirements.txt

**2. Install Ollama and pull the model** (not a pip package -- a separate local service):

    brew install ollama
    ollama pull llama3.1:8b
    ollama serve

Leave `ollama serve` running in its own terminal window.

**3. Real credentials -- set these as environment variables (create a `.env` file, never commit it):**

    SF_CLIENT_ID=<your Salesforce Connected App Consumer Key>
    SF_CLIENT_SECRET=<your Salesforce Connected App Consumer Secret>
    SF_DOMAIN=<your Salesforce My Domain>
    SHIPPO_API_KEY=<your Shippo API key>

Gmail uses OAuth via a browser popup on first run (needs a `google_client_secret.json` file from your own Google Cloud project -- never commit this file either).

**Nothing above is required to get started** -- every real system has an automatic local-CSV fallback, so the project runs immediately with realistic sample data even with zero credentials configured. Add real credentials whenever you're ready; each answer's data-status badge tells you which parts are live vs. fallback.

## Running it

**Command-line chat:**

    export $(grep -v '^#' .env | xargs)
    python3 graph.py

**Web interface (Streamlit):**

    export $(grep -v '^#' .env | xargs)
    streamlit run app.py

**Running the tests** (52 tests, no credentials needed -- uses mocked data):

    export $(grep -v '^#' .env | xargs)
    python3 -m pytest test_task1.py test_task2_disruption_response.py test_tools_task2.py test_task3_sourcing_decision.py -v

## Try asking

- "Do we have enough stock?"
- "Is SHP-2201 at risk?"
- "What should I be worried about this week?"
- "Should we switch to our backup supplier?"
- "Why did you decide that?" (as a follow-up to any answer above)
- "What if we added 300 bags to the warehouse?"

## Project structure

    graph.py                           LangGraph orchestration, the 3 agents, the router
    tools_task1_stock_position.py      Task 1 logic
    tools_task2_risk_assessment.py     Task 2's 6-signal logic
    tools_task2_disruption_response.py Task 2's alert/backup-supplier logic
    tools_task3_sourcing_decision.py   Task 3 logic
    real_data_sources.py               shared real external API calls
    systems/                           Salesforce, Shippo, Gmail integrations
    app.py                             Streamlit web interface
    data/                              local fallback CSVs, used automatically
    test_*.py                          the 52-test automated suite
